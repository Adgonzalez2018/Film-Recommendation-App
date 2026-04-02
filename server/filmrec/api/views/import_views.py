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
from django.utils import timezone
from datetime import timedelta

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from ..utils.unifiedImportHelper import (
    extract_letterboxd_username,
    build_letterboxd_rss_url,
    reset_RSS_userState
)
from ..services.csvImport import run_letterboxd_import
from ..services.rss_sync import sync_user_rss_watches
from ..tasks.tmdb_tasks import enqueue_tmdb_enrichment_for_movies
from ..tasks.import_tasks import build_and_index_taste, _should_rebuild_taste

from ..models import ImportBatch, WatchEvent


RSS_SWITCH_COOLDOWN_HOURS = 24

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def manual_import(request):
    watched_file = request.FILES.get("watched")
    reviews_file = request.FILES.get("reviews")
    watchlist_file = request.FILES.get("watchlist")
    films_upload = request.FILES.get("films")
    likes_upload = request.FILES.get("likes")
    films_file = films_upload or likes_upload

    uploads = [watched_file, reviews_file, watchlist_file, films_file]

    if not any(uploads):
        return Response(
            {"error": "No files provided. Upload at least one of: watched, reviews, watchlist, films."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # guard rails for spam importing
    existing = ImportBatch.objects.filter(
        user=request.user,
        source="csv",
        status__in=["queued", "running"],
    ).order_by("-created_at").first()

    if existing:
        return Response(
            {
                "status": existing.status,
                "batch_id":existing.id,
                "source": existing.source,
                "message": "A CSV import is already in progress.",
            },
            status=status.HTTP_409_CONFLICT,
        )
    
    # Additional guard rails
    for f in uploads:
        # if incorrect file type
        if f and not f.name.lower().endswith(".csv"):
            return Response(
                {"error": f"Invalid file type for {f.name}. Please upload CSV files only."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # if file is empty
        if f and f.size == 0:
            return Response(
                {"error": f"{f.name} is empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # guard rail for large size files
    total_size = sum(f.size for f in uploads if f)
    if total_size > 2 * 1024 * 1024: #2 MB
        return Response(
            {
                "error": "This import is too large for direct processing right now."
            },
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    
    # log batch
    batch = ImportBatch.objects.create(
        user=request.user,
        source="csv",
        status="running",
        had_watched_file=bool(watched_file),
        had_reviews=bool(reviews_file),
        had_watchlist=bool(watchlist_file),
        had_films=bool(films_file),
    )
    try:
        counters = run_letterboxd_import(
            user=request.user,
            watched_file=watched_file,
            reviews_file=reviews_file,
            watchlist_file=watchlist_file,
            films_file=films_file,
        )
        
        movie_ids = counters.get("movies_to_enrich", [])
        tmdb_queued = len(set(movie_ids))

        if movie_ids:
            enqueue_tmdb_enrichment_for_movies(movie_ids, batch_id=batch.id)

        batch.status = "completed"
        batch.movies_created = counters.get("movies_created", 0)
        batch.movies_matched = counters.get("movies_matched", 0)
        batch.rel_created = counters.get("rel_created", 0)
        batch.rel_updated = counters.get("rel_updated", 0)
        batch.events_created = counters.get("events_created", 0)
        batch.tmdb_queued = tmdb_queued
        batch.finished_at = timezone.now()
        batch.save(
            update_fields=[
                "status",
                "movies_created",
                "movies_matched",
                "rel_created",
                "rel_updated",
                "events_created",
                "tmdb_queued",
                "finished_at",
            ]
        )
        request.user.manual_import_count = (request.user.manual_import_count or 0) + 1
        request.user.last_sync = timezone.now()
        request.user.last_manual_sync = timezone.now()
        request.user.save(update_fields=[
            "manual_import_count", 
            "last_sync", 
            "last_manual_sync",
        ])

        print("TASTE GATE", {
            "user_id": request.user.id,
            "events_created": counters.get("events_created", 0),
            "rel_created": counters.get("rel_created", 0),
            "rel_updated": counters.get("rel_updated", 0),
            "should_rebuild": _should_rebuild_taste(request.user.id),
        })
        # build taste summary if events are made
        if (
            counters.get("events_created", 0) > 0
            or counters.get("rel_created", 0) > 0
            or counters.get("rel_updated", 0) > 0
        ):
            if _should_rebuild_taste(request.user.id):
                build_and_index_taste.delay(request.user.id)
        return Response(
            {
                "status": "completed",
                "batch_id": batch.id,
                "source": batch.source,
                "movies_created": batch.movies_created,
                "movies_matched": batch.movies_matched,
                "rel_created": batch.rel_created,
                "rel_updated": batch.rel_updated,
                "events_created": batch.events_created,
                "tmdb_queued": batch.tmdb_queued,
                "tmdb_done": batch.tmdb_done,
                "tmdb_failed": batch.tmdb_failed,
            },
            status=status.HTTP_202_ACCEPTED,
        )
    except Exception as e:
        batch.status = "failed"
        batch.error_message = str(e)
        batch.finished_at = timezone.now()
        batch.save(update_fields=["status","error_message","finished_at"])

        return Response(
            {"error": str(e), "batch_id":batch.id},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
    
    existing = ImportBatch.objects.filter(
        user=request.user,
        source="rss",
        status="running",
    ).exists()

    if existing:
        return Response({"error": "A sync is already in progress."}, status=status.HTTP_409_CONFLICT)
        
    now = timezone.now()
    last_switch = request.user.last_rss_account_switch
    username = extract_letterboxd_username(rss_input) or extract_letterboxd_username(rss_url)

    old_username = (request.user.letterboxd_username or "").strip().lower()
    new_username = (username or "").strip().lower()
    if old_username and new_username and old_username != new_username:
        if last_switch and now - last_switch < timedelta(hours=RSS_SWITCH_COOLDOWN_HOURS):
            remaining = timedelta(hours = RSS_SWITCH_COOLDOWN_HOURS) - (now - last_switch)
            totalSeconds = int(remaining.total_seconds())
            return Response(
                {
                    "error": "cooldown_active",
                    "cooldown_seconds": totalSeconds,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        reset_RSS_userState(request.user)
        request.user.letterboxd_username = new_username
        request.user.last_rss_account_switch = now
        request.user.save(update_fields=["letterboxd_username", "last_rss_account_switch"])
    elif not old_username and new_username:
        request.user.letterboxd_username = new_username
        request.user.save(update_fields=["letterboxd_username"])

    batch = ImportBatch.objects.create(
        user=request.user,
        source="rss",
        status="queued",
        rss_input=rss_input,
    )

    try:
        res = sync_user_rss_watches(request.user, rss_input=rss_input)
        print(
            "RSS RESULT",
            {
                "user_id": request.user.id,
                "error": res.error,
                "entries_seen": res.entries_seen,
                "movies_created": res.movies_created,
                "events_created": res.events_created,
                "rel_created": res.rel_created,
                "rel_updated": res.rel_updated,
                "stopped_early": res.stopped_early,
                "movie_ids_to_enrich": len(res.movie_ids_to_enrich or []),
            },
        )
        if res.error:
            return Response(
                {"error": res.error, "batch_id": batch.id},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        movie_ids = getattr(res, "movie_ids_to_enrich", []) or []
        tmdb_queued = len(set(movie_ids))

        if movie_ids:
            enqueue_tmdb_enrichment_for_movies(movie_ids, batch_id=batch.id)

        batch.status = "completed"
        batch.finished_at = timezone.now()
        batch.movies_created = res.movies_created or 0
        batch.rel_created = res.rel_created or 0
        batch.rel_updated = res.rel_updated or 0
        batch.events_created = res.events_created or 0
        batch.tmdb_queued = tmdb_queued
        batch.save(
            update_fields=[
                "status",
                "finished_at",
                "movies_created",
                "rel_created",
                "rel_updated",
                "events_created",
                "tmdb_queued",
            ]
        )

        request.user.rss_import_count = (request.user.rss_import_count or 0) + 1
        request.user.last_sync = timezone.now()
        request.user.last_rss_sync = timezone.now()
        request.user.save(update_fields=[
            "rss_import_count",
            "last_sync",
            "last_rss_sync",
        ])

        print("TASTE GATE RSS", {
            "user_id": request.user.id,
            "events_created": res.events_created or 0,
            "rel_created": res.rel_created or 0,
            "rel_updated": res.rel_updated or 0,
            "should_rebuild": _should_rebuild_taste(request.user.id),
        })
        # build taste summary if events are made
        if (
            (res.events_created or 0) > 0
            or (res.rel_created or 0) > 0
            or (res.rel_updated or 0) > 0
        ):
            if _should_rebuild_taste(request.user.id):
                result = build_and_index_taste.delay(request.user.id)
                print("TASTE TASK ENQUEUED", {"task_id": result.id, "user_id": request.user.id})
        message = None
        if (res.entries_seen or 0) == 0:
            message = (
                "RSS linked successfully, but this feed has no public diary/review entries yet."
            )
        return Response(
                    {
                        "status": "completed",
                        "batch_id": batch.id,
                        "source": batch.source,
                        "rss_url": rss_url,
                        "movies_created": batch.movies_created,
                        "rel_created": batch.rel_created,
                        "rel_updated": batch.rel_updated,
                        "events_created": batch.events_created,
                        "tmdb_queued": batch.tmdb_queued,
                        "tmdb_done": batch.tmdb_done,
                        "tmdb_failed": batch.tmdb_failed,
                        "entries_seen": res.entries_seen,
                        "message": message,
                    },
                    status=status.HTTP_200_OK,
                )

    except Exception as e:
        batch.status = "failed"
        batch.error_message = str(e)
        batch.finished_at = timezone.now()
        batch.save(update_fields=[
            "status",
            "error_message",
            "finished_at",
        ])

        return Response(
            {"error": str(e), "batch_id": batch.id},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
            has_watch_data or 
            has_manual_import
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

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rebuild_taste(request):
    # Manual Trigger for taste building (debug)
    try:
        build_and_index_taste.delay(request.user.id)
        return Response(
            {"statuts": "queued", "message": "taste rebuild queued. Check Celery logs."},
            status=status.HTTP_202_ACCEPTED,
        )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

"""
For asnyc RSS job
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
"""
