import os
import logging

from celery import shared_task

from django.utils import timezone
from django.contrib.auth import get_user_model

from ..models import ImportBatch
from ..services.letterboxd_import import run_letterboxd_import
from ..services.rss_sync import sync_user_rss_watches
from ..tasks.tmdb_tasks import enqueue_tmdb_enrichment_for_movies

logger = logging.getLogger(__name__)
User = get_user_model()

def _cleanup_file(path: str):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            logger.warning("Could not delete temp import file: %s", path)

@shared_task
def run_csv_import_job(batch_id: int):
    batch = ImportBatch.objects.select_related("user").get(id=batch_id)
    batch.status = "running"
    batch.started_at = timezone.now()
    batch.error_message = ""
    batch.save(update_fields=["status", "started_at", "error_message"])

    try:
        def open_if_present(path):
            return open(path, "rb") if path else None
        
        watched_f = open_if_present(batch.watched_path)
        reviews_f = open_if_present(batch.reviews_path)
        watchlist_f = open_if_present(batch.watchlist_path)
        films_f = open_if_present(batch.films_path)

        try:
            counters = run_letterboxd_import(
                user=batch.user,
                watched_file=watched_f,
                reviews_file=reviews_f,
                watchlist_file=watchlist_f,
                films_file=films_f,
            )
            movie_ids = counters.get("movies_to_enrich", [])
            if movie_ids:
                enqueue_tmdb_enrichment_for_movies(movie_ids, batch_id=batch.id)
                batch.tmdb_queued = len(set(movie_ids))
        finally:
            for f in [watched_f, reviews_f, watchlist_f, films_f]:
                if f:
                    f.close()
        
        batch.status = "completed"
        batch.finished_at = timezone.now()
        batch.movies_created = counters.get("movies_created", 0)
        batch.movies_matched = counters.get("movies_matched", 0)
        batch.rel_created = counters.get("rel_created", 0)
        batch.rel_updated = counters.get("rel_updated", 0)
        batch.events_created = counters.get("events_created", 0)
        batch.save(
            update_fields=[
                "status", "finished_at", "tmdb_queued",
                "movies_created", "movies_matched",
                "rel_created", "rel_updated", "events_created",
            ]
        )
        user = batch.user
        user.manual_import_count = (user.manual_import_count or 0) + 1
        user.last_sync = timezone.now()
        user.save(update_fields=["manual_import_count", "last_sync"])

    except Exception as e:
        logger.exception("CSV import failed batch_id=%s", batch_id)
        batch.status = "failed"
        batch.finished_at = timezone.now()
        batch.error_message = str(e)
        batch.save(update_fields=["status", "finished_at", "error_message"])
    
    finally:
        _cleanup_file(batch.watched_path)
        _cleanup_file(batch.reviews_path)
        _cleanup_file(batch.watchlist_path)
        _cleanup_file(batch.films_path)

@shared_task
def run_rss_import_job(batch_id: int):
    batch = ImportBatch.objects.select_related("user").get(id=batch_id)
    batch.status = "running"
    batch.started_at = timezone.now()
    batch.error_message = ""
    batch.save(update_fields=["status", "started_at", "error_message"])

    try:
        res = sync_user_rss_watches(batch.user, rss_input=batch.rss_input)
        if res.error:
            raise ValueError("Could not read that RSS feed. Make sure the profile is public and the input is correct.")
        
        movie_ids = getattr(res, "movie_ids_to_enrich", []) or []
        if movie_ids:
            enqueue_tmdb_enrichment_for_movies(movie_ids, batch_id=batch.id)
            batch.tmdb_queued = len(set(movie_ids))
        else:
            batch.tmdb_queued = 0
        
        batch.status = "completed"
        batch.finished_at = timezone.now()
        batch.movies_created = res.movies_created or 0
        batch.rel_created = res.rel_created or 0
        batch.rel_updated = res.rel_updated or 0
        batch.events_created = res.events_created or 0
        batch.save(
            update_fields=[
                "status", "finished_at", "tmdb_queued",
                "movies_created", "rel_created", "rel_updated", "events_created",
            ]
        )

        if (res.events_created or 0) > 0:
            user = batch.user
            user.rss_import_count = (user.rss_import_count or 0) + 1
            user.last_sync = timezone.now()
            user.save(update_fields=["rss_import_count", "last_sync"])

    except Exception as e:
        logger.exception("RSS import failed batch_id=%s", batch_id)
        batch.status = "failed"
        batch.finished_at = timezone.now()
        batch.error_message = str(e)
        batch.save(update_fields=["status", "finished_at", "error_message"])

def enqueue_csv_import(batch_id: int):
    run_csv_import_job.delay(batch_id)

def enqueue_rss_import(batch_id: int):
    run_rss_import_job.delay(batch_id)