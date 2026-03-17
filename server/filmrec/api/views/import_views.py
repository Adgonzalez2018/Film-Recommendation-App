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

from ..utils.letterboxd import extract_letterboxd_username, build_letterboxd_rss_url
from ..services.import_uploads import save_temp_upload
from ..tasks.import_tasks import enqueue_csv_import, enqueue_rss_import

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
            {"error": "No files provided. Upload at least one of: watched, reviews, watchlist, films."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # log batch
    batch = ImportBatch.objects.create(
        user=request.user,
        source="csv",
        status="queued",
        had_reviews=bool(reviews_file),
        had_watchlist=bool(watchlist_file),
        had_films=bool(films_file),
        watched_path=save_temp_upload(watched_file, "watched") if watched_file else "",
        reviews_path=save_temp_upload(reviews_file, "reviews") if reviews_file else "",
        watchlist_path=save_temp_upload(watchlist_file, "watchlist") if watchlist_file else "",
        films_path=save_temp_upload(films_file, "films") if films_file else "",
    )

    enqueue_csv_import(batch.id)

    return Response(
        {
            "status": "queued",
            "batch_id": batch.id,
            "source": batch.source,
            "tmdb_queued": batch.tmdb_queued,
            "tmdb_done": batch.tmdb_done,
            "tmdb_failed": batch.tmdb_failed,
        },
        status=status.HTTP_202_ACCEPTED,
    )

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
    
    # guard: don't start a 2nd RSS sync while one is active 
    existing = ImportBatch.objects.filter(
        user=request.user,
        source="rss",
        status__in=["queued", "running"],
    ).order_by("-created_at").first()

    if existing:
        return Response(
            {
                "status": existing.status,
                "batch_id":existing.id,
                "source": existing.source,
                "rss_url": rss_url,
                "tmdb_queued": existing.tmdb_queued,
                "tmdb_done": existing.tmdb_done,
                "tmdb_failed": existing.tmdb_failed,
            },
            status=status.HTTP_202_ACCEPTED
        )
    
    # save username when they link RSS
    username = extract_letterboxd_username(rss_input) or extract_letterboxd_username(rss_url)
    if username:
        prof = request.user
        if prof.letterboxd_username != username:
            prof.letterboxd_username = username
            prof.save(update_fields=["letterboxd_username"])
    
    batch = ImportBatch.objects.create(
        user=request.user,
        source="rss",
        status="queued",
        rss_input=rss_input,
    )

    enqueue_rss_import(batch.id)

    return Response(
        {
            "status": "queued",
            "batch_id":batch.id,
            "source": batch.source,
            "rss_url": rss_url,
            "tmdb_queued": batch.tmdb_queued,
            "tmdb_done": batch.tmdb_done,
            "tmdb_failed": batch.tmdb_failed,
        },
        status=status.HTTP_202_ACCEPTED,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def import_batch_detail(request, batch_id: int):
    batch = ImportBatch.objects.filter(user=request.user, id=batch_id).first()
    if not batch:
        return Response({"error": "Import batch not found."}, status=status.HTTP_404_NOT_FOUND)
    
    return Response(
        {
            "id": batch.id,
            "source": batch.source,
            "status": batch.status,
            "error_message": batch.error_message,
            "created_at": batch.created_at,
            "started_at": batch.started_at,
            "finished_at": batch.finished_at,
            "movies_created": batch.movies_created,
            "movies_matched": batch.movies_matched,
            "rel_created": batch.rel_created,
            "rel_updated": batch.rel_updated,
            "events_created": batch.events_created,
            "had_reviews": batch.had_reviews,
            "had_watchlist": batch.had_watchlist,
            "had_films": batch.had_films,
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
        "has_skipped_onboarding": bool(user.has_skipped_onboarding),
        "is_onboarded": (
            has_watch_data 
            or has_manual_import
            or has_rss_import 
            or user.has_skipped_onboarding)
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def skip_onboarding(request):
    user = request.user
    
    if not user.has_skipped_onboarding:
        user.has_skipped_onboarding = True
        user.save(update_fields=["has_skipped_onboarding"])

    return Response(
        {
            "status": "ok",
            "has_skipped_onboarding": True,
            "is_onboarded": True,
        },
        status=status.HTTP_200_OK
    )