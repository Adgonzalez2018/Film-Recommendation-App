# api/views/letterboxd_views.py
"""
Endpoints for Profile.js, LetterboxdConnect.js
Allows:
- User to manually import letterboxd data
    - 3 files: reviews, films, watchlist (.csv)
- User to connect their RSS 
    - (letterboxd/username)
    - for weekly stat reports
    - Also saves their username to model

Dependencies: letterboxd_import.py
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from ..models import ImportBatch
from ..utils.letterboxd import extract_letterboxd_username

from django.utils import timezone

from ..services.letterboxd_import import (
    run_letterboxd_import, 
    _build_letterboxd_rss_url,
    _parse_published_date)

from ..models import Movie, MovieUser

import feedparser

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def letterboxd_import(request):
    reviews_file = request.FILES.get("reviews")
    watchlist_file = request.FILES.get("watchlist")
    films_file = request.FILES.get("films") or request.FILES.get("likes")

    if not reviews_file and not watchlist_file and not films_file:
        return Response(
            {"error": "No files provided. Upload at least one of: reviews, watchlist, films."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    counters = run_letterboxd_import(
        user=request.user,
        reviews_file=reviews_file,
        watchlist_file=watchlist_file,
        films_file=films_file,
    )
    
    # log batch
    ImportBatch.objects.create(
        user=request.user,
        source="csv",
        movies_created=counters.get("movies_created", 0),
        movies_matched=counters.get("movies_matched", 0),
        rel_created=counters.get("rel_created", 0),
        rel_updated=counters.get("rel_updated", 0),
        had_reviews=bool(reviews_file),
        had_watchlist=bool(watchlist_file),
        had_films=bool(films_file),
    )

    # update profile summary (fast reads for profile page)
    prof = request.user
    prof.manual_import_count = prof.manual_import_count + 1
    prof.last_sync = timezone.now()
    prof.save(update_fields=["manual_import_count", "last_sync"])


    return Response({"status": "ok", **counters}, status=status.HTTP_200_OK)

# --- RSS Import Endpoint ---
@api_view(['POST', 'PATCH'])
@permission_classes([IsAuthenticated])
def letterboxd_rss(request):
    """
    POST {rss : "<username OR profile url OR rss url>"}
    syncs recent watches from public Letterboxd RSS.
    
    """
    rss_input = (request.data.get("rss") or "").strip()
    rss_url = _build_letterboxd_rss_url(rss_input)
    if not rss_url:
        return Response(
            {"error": "Invalid RSS input"}, 
            status=status.HTTP_400_BAD_REQUEST,
            )
    
    # save username when they link RSS
    username = extract_letterboxd_username(rss_input) or extract_letterboxd_username(rss_url)
    if username:
        prof = request.user
        if prof.letterboxd_username != username:
            prof.letterboxd_username = username
            prof.save(update_fields=["letterboxd_username"])
    
    feed = feedparser.parse(rss_url)
    # feed.bozo indicates a parsing error
    if getattr(feed, "bozo", False):
        return Response(
            {"error": "Could not read that RSS feed. Make sure the profile is public and the input is correct."}, 
            status=status.HTTP_400_BAD_REQUEST,
            )
    user = request.user
    synced, created_movies, created_links, updated_links = 0, 0, 0, 0
    # Typical entries ~20
    for entry in feed.entries:
        link = (getattr(entry, "link", "") or "").strip()
        title = (getattr(entry, "title", "") or "").strip()
        if not link:
            continue
        # use the entry link as our letterboxd_uri key
        movie, movie_created = Movie.objects.get_or_create(
            letterboxd_uri=link,
            defaults={"title": title[:255] if title else None}
        )
        if movie_created:
            created_movies += 1

        # Create or update relationship for this user and movie
        mu, created = MovieUser.objects.get_or_create(
            user=user,
            movie=movie,
        )
        if created:
            created_links += 1
        
        # Mark watched + set watched_date from RSS publish date if present
        pub_dt = _parse_published_date(entry)
        watched_date = pub_dt if pub_dt else None
        
        changed = False
        if mu.watch_status != "Watched":
            mu.watch_status = "Watched"
            changed = True

        if watched_date and mu.watched_date != watched_date:
            mu.watched_date = watched_date
            changed = True
        
        if changed:
            mu.save()
            if not created:
                updated_links += 1

        synced += 1

    # log batch
    ImportBatch.objects.create(
        user=user,
        source="rss",
        movies_created=created_movies,
        rel_created=created_links,
        rel_updated=updated_links,
    )

    prof = user
    prof.rss_import_count = prof.rss_import_count + 1
    prof.last_sync = timezone.now()
    prof.save(update_fields=["rss_import_count", "last_sync"])


    return Response({
        "status": "ok",
        "rss_url": rss_url,
        "entries_processed": synced,
        "movies_created": created_movies,
        "movieuser_created": created_links,
        "movieuser_updated": updated_links,
    })
        