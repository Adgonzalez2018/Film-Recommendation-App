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
import logging

from django.db import IntegrityError

from api.models import User, WatchEvent
from api.utils.unifiedImportHelper import (
    normalize_letterboxd_uri,
    build_letterboxd_rss_url,
    needToEnrich,
    upsert_movieuser_snapshot,
    upsert_watch_event,
    resolve_movie_one,
    makeWatchKey,
)

logger = logging.getLogger(__name__)
_TITLE_RE = re.compile(r"^(?P<title>.+?)(?:,\s*(?P<year>\d{4}))?(?:\s*-\s*.+)?$")


def _parse_published_date(entry) -> date | None:
    tp = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if tp:
        try:
            return date(tp.tm_year, tp.tm_mon, tp.tm_mday)
        except Exception:
            return None

    s = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if not s:
        return None

    try:
        return parsedate_to_datetime(s).date()
    except Exception:
        pass

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
    cutoff_buffer_days: int = 7,
    has_manual_history: bool = False,
) -> RSSSyncResult:
    """
    RSS should behave as a lightweight incremental sync.

    Rules:
      - Canonicalize RSS links before resolution.
      - Deduplicate on canonical movie URI + posted_date.
      - If user already has CSV/manual import history, RSS should only consider
        a tight recent window.
      - Only touch MovieUser when a NEW WatchEvent is actually created.
      - Never overwrite an existing MovieUser.watched_date from CSV/reviews.
    """
    movies_to_enrich = set()
    raw = (rss_input if rss_input is not None else user.letterboxd_username) or ""
    raw = raw.strip()
    rss_url = build_letterboxd_rss_url(raw)

    logger.info(
        "RSS sync start user_id=%s raw=%r rss_url=%r last_rss_sync=%r",
        user.id,
        raw,
        rss_url,
        getattr(user, "last_rss_sync", None),
    )

    if not rss_url:
        logger.warning("RSS sync invalid input user_id=%s raw=%r", user.id, raw)
        return RSSSyncResult(
            user_id=user.id,
            rss_url="",
            error="No valid letterboxd username/RSS input.",
        )

    feed = feedparser.parse(rss_url)
    status_code = getattr(feed, "status", None)
    bozo = getattr(feed, "bozo", False)
    bozo_exc = getattr(feed, "bozo_exception", None)
    entries = getattr(feed, "entries", []) or []

    logger.info(
        "RSS parsed user_id=%s status=%r bozo=%r entries=%s bozo_ex=%r",
        user.id,
        status_code,
        bozo,
        len(entries),
        bozo_exc,
    )

    if status_code and status_code != 200:
        return RSSSyncResult(
            user_id=user.id,
            rss_url=rss_url,
            error=f"RSS returned HTTP {status_code}.",
        )

    if not entries:
        return RSSSyncResult(
            user_id=user.id,
            rss_url=rss_url,
            entries_seen=0,
            error=None,
            movie_ids_to_enrich=[],
        )

    res = RSSSyncResult(user_id=user.id, rss_url=rss_url)

    existing_event_keys = set(
        WatchEvent.objects.filter(user=user).values_list("event_key", flat=True)
    )

    # Tighten RSS behavior after CSV/manual import exists.
    last_rss = getattr(user, "last_rss_sync", None)
    cutoff_date = None

    if last_rss:
        # Normal incremental behavior after first RSS sync.
        cutoff_date = last_rss.date() - timedelta(days=cutoff_buffer_days)
    elif has_manual_history:
        # If user already imported CSV, RSS should only look at a recent window.
        # Prevent RSS from acting like a second historical importer.
        cutoff_date = datetime.utcnow().date() - timedelta(days=30)

    logger.info(
        "RSS cutoff user_id=%s cutoff_date=%r buffer_days=%s has_manual_history=%r",
        user.id,
        cutoff_date,
        cutoff_buffer_days,
        has_manual_history,
    )

    for idx, entry in enumerate(entries, start=1):
        raw_link = (getattr(entry, "link", "") or "").strip()
        title = (getattr(entry, "title", "") or "").strip()
        entry_ref = (getattr(entry, "id", "") or getattr(entry, "link", "") or "").strip()

        if not raw_link:
            continue

        link = normalize_letterboxd_uri(raw_link)
        if not link:
            continue

        posted_date = _parse_published_date(entry)

        # Count only parseable candidate entries
        res.entries_seen += 1

        if cutoff_date and posted_date and posted_date <= cutoff_date:
            res.stopped_early = True
            logger.info(
                "RSS stop cutoff user_id=%s idx=%s posted_date=%r cutoff_date=%r",
                user.id,
                idx,
                posted_date,
                cutoff_date,
            )
            break

        parsed_title, parsed_year = _parse_entry_title(title)

        try:
            movie, was_created, _ = resolve_movie_one(parsed_title, parsed_year, link)
        except Exception:
            logger.exception(
                "RSS resolve_movie_one failed user_id=%s idx=%s parsed_title=%r parsed_year=%s norm_link=%r",
                user.id,
                idx,
                parsed_title,
                parsed_year,
                link,
            )
            continue

        if not movie or not movie.id or not movie.letterboxd_uri or not posted_date:
            continue

        event_key = makeWatchKey(user.id, movie.letterboxd_uri, posted_date)

        if event_key in existing_event_keys:
            logger.info(
                "RSS skip existing event_key user_id=%s idx=%s event_key=%r",
                user.id,
                idx,
                event_key,
            )
            continue

        duplicate_same_day = WatchEvent.objects.filter(
            user=user,
            movie=movie,
            posted_date=posted_date,
        ).exists()
        if duplicate_same_day:
            logger.info(
                "RSS skip same movie/day user_id=%s idx=%s movie_id=%s posted_date=%r",
                user.id,
                idx,
                movie.id,
                posted_date,
            )
            existing_event_keys.add(event_key)
            continue

        if was_created:
            res.movies_created += 1

        try:
            _, we_created = upsert_watch_event(
                user=user,
                movie=movie,
                posted_date=posted_date,
                watched_date=posted_date,  # fallback only for RSS-created event rows
                rewatch=False,
                source="rss",
                entry_url=entry_ref or raw_link,
            )
        except IntegrityError:
            we_created = False
            logger.exception(
                "RSS upsert_watch_event integrity error user_id=%s idx=%s movie_id=%s",
                user.id,
                idx,
                movie.id,
            )

        if not we_created:
            # Critical tightening: do not touch MovieUser unless a new event was created.
            continue

        res.events_created += 1
        existing_event_keys.add(event_key)

        if needToEnrich(movie):
            movies_to_enrich.add(movie.id)

        try:
            mu, created_mu, changed_mu = upsert_movieuser_snapshot(
                user,
                movie,
                {"watch_status": "Watched"},
            )

            # Only fill missing watched_date; never overwrite CSV/review truth.
            if mu.watched_date is None:
                mu.watched_date = posted_date
                mu.save(update_fields=["watched_date"])
                if not created_mu:
                    changed_mu = True

        except IntegrityError:
            created_mu = False
            changed_mu = False

        if created_mu:
            res.rel_created += 1
        elif changed_mu:
            res.rel_updated += 1

    res.movie_ids_to_enrich = list(movies_to_enrich)
    return res