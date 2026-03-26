# api/services/rss_sync.py
"""
Dependent on Unified Import Helper Service File
    - has many functions that are utilized here and for CSV Imports

RSS Import
    - used in RSS_Import api endpoint
    - takes users RSS username if they don't have it alr
    - Only does ~50 movies (Or last known watch date)
    - Used for Weekly Syncs
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, date, datetime
from email.utils import parsedate_to_datetime
from typing import Optional, Tuple
import re
import feedparser

from django.db import IntegrityError

from api.models import User, WatchEvent

from api.utils.unifiedImportHelper import (
    normalize_letterboxd_uri,
    build_letterboxd_rss_url,
    needToEnrich,
    upsert_movieuser_snapshot,
    upsert_watch_event,
    resolve_movie_one,
    makeEventKey,
    )

_TITLE_RE = re.compile(r"^(?P<title>.+?)(?:,\s*(?P<year>\d{4}))?(?:\s*-\s*.+)?$")


def _parse_published_date(entry) -> date | None:
    """
    Returns a *date* for when the RSS entry was published/updated.
    prefer parsed structs if available; fall back to parsing string
    """

    tp = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if tp:
        try:
            return date(tp.tm_year, tp.tm_mon, tp.tm_mday)
        except Exception:
            return None

    # fallback: try published string
    s = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if not s:
        return None

    # RSS commonly uses RFC822
    try:
        return parsedate_to_datetime(s).date()
    except Exception:
        pass

    # last-ditch: iso like str
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None
    
def _parse_entry_title(entry_title: str) -> Tuple[str, Optional[int]]:
    s = (entry_title or "").strip()
    if not s:
        return "Untitled", None
    m = _TITLE_RE.match(s)
    if not m:
        return s[:255], None
    
    title = (m.group("title") or "").strip()[:255] or "Untitled"
    year_str = m.group("year")
    try:
        year = int(year_str) if year_str else None
    except Exception:
        year = None

    return title, year

@dataclass
class RSSSyncResult:
    user_id: int
    rss_url: str
    entries_seen: int = 0
    movies_created: int = 0
    events_created: int = 0
    rel_created: int = 0
    rel_updated: int = 0
    stopped_early: bool = False
    error: Optional[str] = None
    movie_ids_to_enrich: list[int] | None = None


def sync_user_rss_watches(
    user: User,
    *,
    rss_input: Optional[str] = None,
    cutoff_buffer_days: int = 1,
) -> RSSSyncResult:
    """
    Incremental RSS sync (newest first).
    Stop when:
      - entry date <= (user.last_sync.date - buffer_days), OR
      - exact WatchEvent already exists (event_key)
    """
    movies_to_enrich = set()
    raw = (rss_input if rss_input is not None else user.letterboxd_username) or ""
    raw = raw.strip()
    rss_url = build_letterboxd_rss_url(raw)

    if not rss_url:
        return RSSSyncResult(user_id=user.id, rss_url="", error="No valid letterboxd username/RSS input.")

    feed = feedparser.parse(rss_url)
    status_code = getattr(feed, "status", None)
    if status_code and status_code != 200:
        return RSSSyncResult(
            user_id = user.id,
            rss_url = rss_url,
            error =f"RSS returned HTTP {status_code}.",
        )
    
    if getattr(feed, "bozo", False):
        return RSSSyncResult(
            user_id=user.id, 
            rss_url=rss_url,
            error="Could not parse RSS feed (bozo=True)."
        )

    res = RSSSyncResult(user_id=user.id, rss_url=rss_url)

    # unique set of event keys alr in user's watchevent table
    existing_event_keys = set(
        WatchEvent.objects.filter(user=user, source="rss")
        .values_list("event_key", flat=True)
    )

    cutoff_date = None
    if user.last_sync:
        cutoff_date = user.last_sync.date() - timedelta(days=cutoff_buffer_days)

    for entry in getattr(feed, "entries", []) or []:
        link = (getattr(entry, "link", "") or "").strip()
        title = (getattr(entry, "title", "") or "").strip()
        entry_ref = (getattr(entry, "id", "") or getattr(entry, "link","") or "").strip()
        if not link:
            continue

        link = normalize_letterboxd_uri(link)
        if not link:
            continue
        
        res.entries_seen += 1

        posted_date = _parse_published_date(entry)  # date | None

        # stop on cutoff (entries are newest first)
        if cutoff_date and posted_date and posted_date <= cutoff_date:
            res.stopped_early = True
            break

        parsed_title, parsed_year = _parse_entry_title(title)
        if posted_date and link:
            event_key = makeEventKey(user.id, link, posted_date, entry_ref)
            if event_key in existing_event_keys:
                res.stopped_early = True
                break

        movie, was_created, _ = resolve_movie_one(parsed_title, parsed_year, link)

        if was_created:
            res.movies_created += 1
        # event key + stop if already imported
        if posted_date:
            try:
                _, we_created = upsert_watch_event(
                    user=user,
                    movie=movie,
                    posted_date=posted_date,
                    watched_date=posted_date,
                    rewatch=False,
                    source="rss",
                    entry_url=entry_ref or link,
                )
            except IntegrityError:
                we_created = False

            if we_created:
                res.events_created += 1
                existing_event_keys.add(event_key)

        if needToEnrich(movie):
            movies_to_enrich.add(movie.id)

        defaults = {"watch_status": "Watched"}
        if posted_date:
            defaults["watched_date"] = posted_date
        try:
            _, created_mu, changed_mu = upsert_movieuser_snapshot(user, movie, defaults)
        except IntegrityError:
            created_mu = False
            changed_mu = False

        if created_mu:
            res.rel_created += 1
        elif changed_mu:
            res.rel_updated += 1 

    res.movie_ids_to_enrich = list(movies_to_enrich)
    return res