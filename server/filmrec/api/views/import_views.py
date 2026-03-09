# api/views/import_views.py
"""
Endpoints for Profile.js, Imports.js
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

from django.utils import timezone

from ..services.letterboxd_import import run_letterboxd_import
from ..utils.letterboxd import extract_letterboxd_username, build_letterboxd_rss_url
from api.services.rss_sync import sync_user_rss_watches

from ..models import WatchEvent, ImportBatch


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def manual_import(request):
    watched_file = request.FILES.get("watched")
    reviews_file = request.FILES.get("reviews")
    watchlist_file = request.FILES.get("watchlist")

    films_upload = request.FILES.get("films")
    likes_upload = request.FILES.get("likes")
    films_file = films_upload or likes_upload
    
    if not watched_file and not reviews_file and not watchlist_file and not films_file:
        return Response(
            {"error": "No files provided. Upload at least one of: reviews, watchlist, films."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    counters = run_letterboxd_import(
        user=request.user,
        watched_file=watched_file,
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
        events_created=counters.get("events_created",0),
        had_reviews=bool(reviews_file),
        had_watchlist=bool(watchlist_file),
        had_films=bool(films_file),
    )

    # update profile summary (fast reads for profile page)
    prof = request.user
    prof.manual_import_count = (prof.manual_import_count or 0) + 1
    prof.last_sync = timezone.now()
    prof.save(update_fields=["manual_import_count", "last_sync"])

    return Response({"status": "ok", **counters}, status=status.HTTP_200_OK)

# --- RSS Import Endpoint ---
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_rss(request):
    """
    POST {rss : "<username OR profile url OR rss url>"}
    syncs recent watches from public Letterboxd RSS.
    """
    rss_input = (request.data.get("rss") or "").strip()

    rss_url = build_letterboxd_rss_url(rss_input)
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
    
    # run sync using the shared service (single source of truth)
    res = sync_user_rss_watches(request.user, rss_input=rss_input)

    if res.error:
        # keep the endpoint error message user-friendly
        return Response(
            {"error": "Could not read that RSS feed. Make sure the profile is public and the input is correct."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # update profile
    prof = request.user
    prof.rss_import_count = (prof.rss_import_count or 0) + 1
    prof.last_sync = timezone.now()
    prof.save(update_fields=["rss_import_count", "last_sync"])
    
    return Response({
        "status": "ok",
        "rss_url": res.rss_url,
        "entries_processed": res.entries_seen,
        "movies_created": res.movies_created,
        "events_created": res.events_created,
        "rel_created": res.rel_created,
        "rel_updated": res.rel_updated,
        "stopped_early": res.stopped_early,
    },
    status=status.HTTP_200_OK,
    )
        

# Check if user has data
# if yes direct to Chat page
# else continue with Import page
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def onboarding_status(request):
    user = request.user
    has_watch_data = WatchEvent.objects.filter(user=user).exists()
    has_manual_import = (user.manual_import_count or 0) > 0
    has_rss_import = (user.rss_import_count or 0) >0

    return Response({
        "has_manual_import": has_manual_import,
        "has_rss_import": has_rss_import,
        "is_onboarded": has_watch_data or has_manual_import or has_rss_import
    })
