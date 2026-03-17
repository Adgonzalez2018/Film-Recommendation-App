# For movie enrichment
from django.utils import timezone
from django_rq import enqueue
from django.db import models
from django.db.models import F

from celery import shared_task

from ..models import Movie, ImportBatch
from ..services.tmdb import upsert_tmdb_movie, attach_tmdb_to_movie, find_best_tmdb_movie_match

@shared_task
def enrich_movie_from_tmdb(movie_id: int, batch_id=None):
    movie = Movie.objects.get(id=movie_id)

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
                letterboxd_uri=movie.letterboxd_uri,
            )

        if not tmdb_id:
            movie.enrichment_status = "not_found"
            movie.last_enriched_at = timezone.now()
            movie.save(update_fields=["enrichment_status","last_enriched_at"])
            return
        
        # let your existing tmdb service do the real population
        if movie.tmdb_id and movie.tmdb_id == tmdb_id:
            enriched = upsert_tmdb_movie(tmdb_id)
            if enriched.id != movie.id:
                attach_tmdb_to_movie(movie_id=movie.id, tmdb_id=tmdb_id)
        else:
            attach_tmdb_to_movie(movie_id=movie.id, tmdb_id=tmdb_id)
        
        movie.refresh_from_db()
        movie.enrichment_status = "done"
        movie.last_enriched_at = timezone.now()
        movie.enrichment_error = ""
        movie.save(update_fields=["enrichment_status","last_enriched_at", "enrichment_error"])
        
        if batch_id:
            ImportBatch.objects.filter(id=batch_id).update(tmdb_done=F("tmdb_done") + 1)

    except Exception as e:
        movie.enrichment_status = "failed"
        movie.last_enriched_at = timezone.now()
        movie.enrichment_error = str(e)
        movie.save(update_fields=["enrichment_status","last_enriched_at", "enrichment_error"])

        if batch_id:
            ImportBatch.objects.filter(id=batch_id).update(tmdb_failed=F('tmdb_failed') + 1)
        raise

@shared_task
def enrich_movie_chunk(movie_ids, batch_id=None):
    for movie_id in movie_ids:
        enrich_movie_from_tmdb(movie_id, batch_id=batch_id)

def enqueue_tmdb_enrichment_for_movies(movie_ids, batch_id=None, chunk_size=25):
    unique_ids = sorted(set(movie_ids))
    for i in range(0, len(unique_ids), chunk_size):
        chunk = unique_ids[i: i + chunk_size]
        enrich_movie_chunk.delay(chunk, batch_id=batch_id)


        