# api/services/rss_sync.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Tuple
import re
import feedparser

from django.utils import timezone

from api.models import User, Movie, MovieUser, WatchEvent
from api.services.letterboxd_import import (
    _parse_published_date
)
from api.utils.letterboxd import (
    normalize_letterboxd_uri,
    build_letterboxd_rss_url,
    )

from api.utils.rss import make_eventkey

_TITLE_RE = re.compile(r"^(?P<title>.+?)(?:,\s*(?P<year>\d{4}))?(?:\s*-\s*.+)?$")
MUST_ENRICH_STATUS = ["pending", "queued", "failed", "not_found"]

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

def _find_existing_movie(*, link: str, entry_title: str) -> Optional[Movie]:
    movie = Movie.objects.filter(letterboxd_uri=link).first()
    if movie:
        return movie
    
    parsed_title, parsed_year = _parse_entry_title(entry_title)

    if parsed_title and parsed_year is not None:
        movie = Movie.objects.filter(title=parsed_title, year=parsed_year).first()
        if movie:
            if not movie.letterboxd_uri:
                movie.letterboxd_uri = link
                movie.save(update_fields=["letterboxd_uri"])
            return movie
        
    return None
    

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

        link = normalize_letterboxd_uri(link) or link
        res.entries_seen += 1

        posted_date = _parse_published_date(entry)  # date | None

        # stop on cutoff (entries are newest first)
        if cutoff_date and posted_date and posted_date <= cutoff_date:
            res.stopped_early = True
            break

        # event key + stop if already imported
        if posted_date:
            event_key = make_eventkey(
                user.id, 
                getattr(entry, "id", link), 
                posted_date
            )
        else:
            # consistent fallback if date is missing
            event_key = make_eventkey(user.id,entry_ref or link, timezone.now().date())

        if event_key in existing_event_keys:
            continue

        # upsert movie by letterboxd_uri
        movie = _find_existing_movie(link=link, entry_title=title)
        if not movie:
            parsed_title, parsed_year = _parse_entry_title(title)
            movie = Movie.objects.create(
                title = parsed_title,
                year=parsed_year,
                letterboxd_uri=link,
                enrichment_status="pending",
            )
            movies_to_enrich.add(movie.id)
            res.movies_created+= 1
        if not movie:
            continue

        if not movie.tmdb_id or getattr(movie, "enrichment_status", None) in MUST_ENRICH_STATUS:
            movies_to_enrich.add(movie.id)
        # create WatchEvent
        we, we_created = WatchEvent.objects.get_or_create(
            user=user,
            event_key=event_key,
            defaults={
                "movie": movie,
                "posted_date": posted_date or timezone.now().date(),
                "watched_date": posted_date,
                "source": "rss",
                "entry_url": entry_ref or link,
            },
        )
        if we_created:
            res.events_created += 1
            # add to set of event keys
            existing_event_keys.add(event_key)
            
        # MovieUser snapshot
        mu, created = MovieUser.objects.get_or_create(user=user, movie=movie)
        if created:
            res.rel_created += 1

        changed = False
        if mu.watch_status != "Watched":
            mu.watch_status = "Watched"
            changed = True

        if posted_date and mu.watched_date != posted_date:
            mu.watched_date = posted_date
            changed = True

        if changed:
            mu.save()
            if not created:
                res.rel_updated += 1

    res.movie_ids_to_enrich = list(movies_to_enrich)
    return res