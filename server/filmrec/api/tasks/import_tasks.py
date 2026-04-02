"""
Import Tasks runs 
    - CSV/RSS import jobs synchronously
    - Build User Taste Summaries Asynchronously ONLY if user actually made new events

"""

import os
import tempfile
import logging

from celery import shared_task

from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command

from ..models import ImportBatch
from ..services.csvImport import run_letterboxd_import
from ..services.rss_sync import sync_user_rss_watches
from ..tasks.tmdb_tasks import enqueue_tmdb_enrichment_for_movies

logger = logging.getLogger(__name__)
User = get_user_model()

# Optimization: Raised from 5s to 30s
# tasks (e.g. onboarding RSS + CSV) could both slip through if the scheduler
# queues them more than 5 s apart. 30 s gives real protection.
_TASTE_REBUILD_COOLDOWN = 30

def _cleanup_file(path: str):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            logger.warning("Could not delete temp import file: %s", path)

def should_rebuild_taste(user_id: int) -> bool:
    key = f"taste_rebuild_lock:{user_id}"
    # add_* is atomic in all Django cache backends; returns True only when
    # the key was absent (i.e. this is the first caller within the window)
    return cache.add(key, True, timeout=_TASTE_REBUILD_COOLDOWN)

def has_new_data(counters_or_res, *, is_res=False) -> bool:
    # return true if the import produced anything worht re-indexing
    if is_res:
        return (
        (counters_or_res.events_created or 0) > 0
        or (counters_or_res.rel_created or 0) > 0
        or (counters_or_res.rel_updated or 0) > 0
        )
    return (
        counters_or_res.get("events_created", 0) > 0
        or counters_or_res.get("rel_created", 0) > 0
        or counters_or_res.get("rel_updated", 0) > 0
    )

def enqueue_taste_rebuild(user_id: int, result, *, is_res=False) -> bool:
    # rebuild if needed
    if not has_new_data(result, is_res=is_res):
        logger.info("taste rebuild skipped (no new data) user=%s", user_id)
        return False, "no_new_data"
    if not should_rebuild_taste(user_id):
        logger.info("taste rebuild skipped (cooldown) user=%s", user_id)
        return False, "cooldown"
    
    build_and_index_taste.delay(user_id)
    logger.info("taste rebuild queued user=%s", user_id)
    return True, "queued"

        
@shared_task(queue="taste")
def build_and_index_taste(user_id):
    logger.warning(f"[taste task] starting for user_id={user_id}")
    try:
        user = User.objects.get(id=user_id)
        logger.info(f"[taste task] found user: {user.username}")
    except User.DoesNotExist:
        logger.error(f"[taste task] User {user_id} not found")
        return
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        filename = f"taste_user_{user_id}.txt"
        file_path = os.path.join(tmp_dir, filename)

        try:
            logger.info(f"[taste task] building file for user_id={user_id} -> {file_path}")
            call_command("build_taste_file", user_id=user_id, out=tmp_dir)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Taste file was not created: {file_path}")
            
            file_size = os.path.getsize(file_path)
            logger.info(f"[taste task] File created successfully. Size:{file_size} bytes")

            logger.info(f"[taste task] Indexing vector store for user_id={user_id}")
            call_command(
                "index_user_taste_store",
                user_id=user_id,
                file=file_path,
            )
            logger.info(f"[taste task] Complete for user_id={user_id}")
            print(f"[taste task] done user_id={user_id}")
        except Exception as e:
            logger.exception(f"[taste task] failed for user_id={user_id}: {str(e)}")
            raise

# only used if async?
def enqueue_csv_import(batch_id: int):
    run_csv_import_job.delay(batch_id)

def enqueue_rss_import(batch_id: int):
    run_rss_import_job.delay(batch_id)


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

            # Asynchronously enrich movies if they don't have any TMDB Data
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


        # If any of new stuff has been created we build and index the user's taste summary
        # this mitigates any overlap between running the inital onboarding rss and csv import
        if has_new_data(counters):
            enqueue_taste_rebuild(batch.user.id)
        user = batch.user
        user.manual_import_count = (user.manual_import_count or 0) + 1
        user.last_sync = timezone.now()
        user.last_manual_sync = timezone.now()
        user.save(update_fields=["manual_import_count", "last_sync", "last_manual_sync"])

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
        
        # Asynchronously enrich movies if they don't have any TMDB Data
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
            user.last_rss_sync = timezone.now()
            user.save(update_fields=["rss_import_count", "last_sync","last_rss_sync"])

        # If any of new stuff has been created we build and index the user's taste summary
        # this mitigates any overlap between running the inital onboarding rss and csv import
        if has_new_data(res):
            enqueue_taste_rebuild(batch.user.id)

    except Exception as e:
        logger.exception("RSS import failed batch_id=%s", batch_id)
        batch.status = "failed"
        batch.finished_at = timezone.now()
        batch.error_message = str(e)
        batch.save(update_fields=["status", "finished_at", "error_message"])

