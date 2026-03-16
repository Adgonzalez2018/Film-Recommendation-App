# api/services/rss_sync.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Tuple
import re
import feedparser

from django.utils import timezone

from api.models import User, Movie, MovieUser, WatchEvent, ImportBatch
from api.services.letterboxd_import import (
    _parse_published_date
)
from api.services.tmdb import find_best_tmdb_movie_match, upsert_tmdb_movie
from api.utils.letterboxd import (
    normalize_letterboxd_uri,
    build_letterboxd_rss_url,
    )

from api.utils.rss import make_eventkey

_TITLE_RE = re.compile(r"^(?P<title>.+?)(?:,\s*(?P<year>\d{4}))?(?:\s*-\s*.+)?$")

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

def _find_existing_movie(*, link: str, entry_title: str) -> Optional[Movie]:
    movie = Movie.objects.filter(letterboxd_uri=link).first()
    if movie:
        return movie
    
    parsed_title, parsed_year = _parse_entry_title(entry_title)

    if parsed_title and parsed_year is not None:
        movie = Movie.objects.filter(title=parsed_title, year=parsed_year)
        if movie:
            if not movie.letterboxd_uri:
                movie.letterboxd_uri = link
                movie.save(update_fileds=["letterboxd_uri"])
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

    cutoff_date = None
    if user.last_sync:
        cutoff_date = user.last_sync.date() - timedelta(days=cutoff_buffer_days)

    for entry in getattr(feed, "entries", []) or []:
        link = (getattr(entry, "link", "") or "").strip()
        title = (getattr(entry, "title", "") or "").strip()
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
            event_key = make_eventkey(user.id, link, posted_date)
        else:
            # consistent fallback if date is missing
            event_key = make_eventkey(user.id, link, timezone.now().date())

        if WatchEvent.objects.filter(user=user, event_key=event_key).exists():
            res.stopped_early = True
            break

        # upsert movie by letterboxd_uri
        movie = _find_existing_movie(link=link, entry_title=title)
        if not movie:
            parsed_title, parsed_year = _parse_entry_title(title)
            tmdb_id = find_best_tmdb_movie_match(parsed_title, parsed_year)

            if tmdb_id:
                movie = upsert_tmdb_movie(tmdb_id)
                if movie.letterboxd_uri != link:
                    movie.letterboxd_uri = link
                    movie.save(update_fields=["letterboxd_uri"])
                else:
                    continue


        # create WatchEvent
        we, we_created = WatchEvent.objects.get_or_create(
            user=user,
            event_key=event_key,
            defaults={
                "movie": movie,
                "posted_date": posted_date or timezone.now().date(),
                "watched_date": posted_date,
                "source": "rss",
                "entry_url": link,
            },
        )
        if we_created:
            res.events_created += 1

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

    # log once
    ImportBatch.objects.create(
        user=user,
        source="rss",
        movies_created=res.movies_created,
        rel_created=res.rel_created,
        rel_updated=res.rel_updated,
        events_created=res.events_created,
    )

    return res