"""
TMDB Tasks
    - Runs asynchronously 
    - Only used for any ingested movies that DO NOT have any TMDB data
    - Any movies marked for enrichment call this job
    
"""
import time
import logging

from django.utils import timezone
from django.db.models import F
from django.core.exceptions import ValidationError

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

from ..models import Movie, ImportBatch
from ..services.tmdb import upsert_tmdb_movie, attach_tmdb_to_movie, find_best_tmdb_movie_match

logger = logging.getLogger(__name__)

# seconds to sleep between movies inside a chunk = keeps us well under
# TMDB's 40-request/10s limit even at high worker concurrency
_INTER_MOVIE_DELAY = .3

@shared_task(
        bind=True,
        queue="tmdb",
        max_retries=4,
        default_retry_delay=30, # first retry after 30s; celery doubles with backoff
        autoretry_for=(Exception,),
        retry_backoff=True,
        retry_jitter=True,
        # Don't autoretry on Validation Error - those are perma failures
        dont_autoretry_for=(ValidationError,),
)
def enrich_movie_from_tmdb(movie_id: int, batch_id=None):
    try:
        movie = Movie.objects.get(id=movie_id)
    except Movie.DoesNotExist:
        logger.warning("enrich_movie_from_tmdb: movie_id=%s not found, skipping", movie_id)
        return

    if movie.enrichment_status == "done" and movie.tmdb_id:
        return
    
    movie.enrichment_status = "enriching"
    movie.enrichment_attempts = (movie.enrichment_attempts or 0) + 1
    movie.enrichment_error = ""
    movie.save(update_fields=["enrichment_status","enrichment_attempts", "enrichment_error"])

    try:
        tmdb_id = movie.tmdb_id
        if not tmdb_id:
            tmdb_id = find_best_tmdb_movie_match(
                title = movie.title,
                year=movie.year,
            )

        if not tmdb_id:
            movie.enrichment_status = "not_found"
            movie.last_enriched_at = timezone.now()
            movie.save(update_fields=["enrichment_status","last_enriched_at"])
            return
        
        try:
            # bug fix: the original logic called upsert tmdb movie when
            # movie.tmdb was alr set, then called attach_tmdb_to_movie
            # always does update or create on tmdb_id, so it returns
            # the canonical row for that tmdb_id which may not be movie.id
            # let your existing tmdb service do the real population
            attach_tmdb_to_movie(movie_id=movie.id,tmdb_id=tmdb_id)
        except ValidationError as e:
            msg = str(e)
            if "already attached to another movie" in msg:
                movie.enrichment_status = "done"
                movie.last_enriched_at = timezone.now()
                movie.enrichment_error = "Skipped: tmdb_id owned by another row"
                movie.save(update_fields=["enrichment_status", "last_enriched_at", "enrichment_error"])

                _inc_batch(batch_id, done=True)
                return
            raise
        
        movie.refresh_from_db()
        movie.enrichment_status = "done"
        movie.last_enriched_at = timezone.now()
        movie.enrichment_error = ""
        movie.save(update_fields=["enrichment_status","last_enriched_at", "enrichment_error"])
        _inc_batch(batch_id, done=True)
    except MaxRetriesExceededError:
        _mark_failed(movie, batch_id, "Max retries exceeeded")
        
    except Exception as e:
        logger.exception("enrich_movie_from_tmdb failed movie_id=%s", movie_id)
        _mark_failed(movie, batch_id, str(e))
        raise # let celery autoretry handle it

@shared_task(queue="tmdb")
def enrich_movie_chunk(movie_ids: list, batch_id=None):
    """
    Process a chunk of movie IDs sequentially on one worker
    with a small inter-request delay to respect TMDB rate limits.
    # bug fix: original used .run() which is a direct sync call
    """
    for movie_id in movie_ids:
        try:    
            enrich_movie_from_tmdb.run(movie_id, batch_id=batch_id)
        except Exception:
            # log and continue - one bad movie doesn't abort chunk
            # mark it's failure
            logger.exception("Chunk: movie_id=%s failed, continuing", movie_id)
        time.sleep(_INTER_MOVIE_DELAY)


def enqueue_tmdb_enrichment_for_movies(movie_ids, batch_id=None, chunk_size: int = 25):
    unique_ids = sorted(set(movie_ids))

    pending_ids = list(
        Movie.objects
        .filter(
            id__in=unique_ids,
            tmdb_id__isnull=True,
            enrichment_status__in=("pending", "failed", "") # skip "enriching/done"
        )
        .values_list("id", flat=True)
    )
    if not pending_ids:
        return
    
    # BUG FIX: original chunked from unique ids after filtering to pending ids
    # # so alr enriched movies re entered the queue. 
    for i in range(0, len(pending_ids), chunk_size):
        chunk = pending_ids[i: i + chunk_size]
        enrich_movie_chunk.apply_async(args=[chunk], kwargs={"batch_id": batch_id}, queue="tmdb")

# --- internal helpers ---
def _mark_failed(movie: Movie, batch_id, error: str):
    movie.enrichment_status = "failed"
    movie.last_enriched_at = timezone.now()
    movie.enrichment_error = error
    movie.save(update_fields=["enrichment_status", "last_enriched_at", "enrichment_error"])
    _inc_batch(batch_id, done=False)

def _inc_batch(batch_id, *, done: bool):
    if not batch_id:
        return
    if done:
        ImportBatch.objects.filter(id=batch_id).update(tmdb_done=F("tmdb_done")+1)
    else:
        ImportBatch.objects.filter(id=batch_id).update(tmdb_failed=F("tmdb_failed")+1)
