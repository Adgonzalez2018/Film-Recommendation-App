from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import feedparser

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from api.models import (
    User, Movie, MovieUser, ImportBatch
)
from api.services.letterboxd_import import _build_letterboxd_rss_url, _parse_published_date

@dataclass
class SyncResult:
    user_id: int
    rss_url:str
    entries_seen: int = 0
    movies_created: int = 0
    links_created: int = 0
    links_updated: int = 0
    stopped_early: bool = False
    error: Optional[str] = None

def _sync_user_rss_watches(user: User) -> SyncResult:
    """
    RSS = watches-only incremental sync
    stops early if it hits a movieuser alr linked
    """
    rss_input = (user.letterboxd_username or "").strip()
    rss_url = _build_letterboxd_rss_url(rss_input)

    if not rss_url:
        return SyncResult(user_id = user.id, rss_url = "", error="User has no valid letterboxd username")

    feed = feedparser.parse(rss_url)
    if getattr(feed, "bozo", False):
        return SyncResult(user_id=user.id, rss_url = rss_url, error="feedparser bozo=True (cannot parse feed)")
    
    res = SyncResult(user_id = user.id, rss_url = rss_url)

    # entries are newest first
    for entry in getattr(feed, "entries", []) or []:
        link = (getattr(entry, "link","") or "").strip()
        title = (getattr(entry, "title","") or "").strip()

        if not link:
            continue

        res.entries_seen += 1

        # if we've imported this letterboxd uri for this user stop
        if MovieUser.objects.filter(user=user, movie__letterboxd_uri=link).exists():
            res.stopped_early = True
            break

        movie, movie_created = Movie.objects.get_or_create(
            letterboxd_uri=link,
            defaults={"title":title[:255] if title else "Untitled"},
        )

        if movie_created:
            res.movies_created += 1


        mu, created = MovieUser.objects.get_or_create(
            user=user,
            movie=movie,
        )
        if created:
            res.links_created += 1

        pub_dt = _parse_published_date(entry)
        watched_date = pub_dt if pub_dt else None

        # Log a batch even if nothing new (helpful for audit)
        ImportBatch.objects.create(
            user=user,
            source="rss",
            movies_created=res.movies_created,
            rel_created=res.links_created,
            rel_updated=res.links_updated,
        )

        user.rss_import_count = (user.rss_import_count or 0 ) + 1
        user.last_sync = timezone.now()
        user.save(update_fields=["rss_import_count", "last_sync"])

    return res