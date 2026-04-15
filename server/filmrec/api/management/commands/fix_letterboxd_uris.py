from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Movie, WatchEvent, MovieUser, FilmBank
from api.utils.unifiedImportHelper import normalize_letterboxd_uri


class Command(BaseCommand):
    help = "Fix Letterboxd URIs and merge duplicate Movie rows"

    def handle(self, *args, **options):
        update_count = 0
        merge_count = 0

        movies = Movie.objects.exclude(letterboxd_uri__isnull=True).exclude(letterboxd_uri="")

        for m in movies:
            old = m.letterboxd_uri
            new = normalize_letterboxd_uri(old)

            if not new or new == old:
                continue

            conflict = Movie.objects.filter(letterboxd_uri=new).exclude(id=m.id).first()

            if conflict:
                self.stdout.write(f"\nMERGING {m.id} -> {conflict.id} ({m.title})")
                self.merge_movies(m, conflict)
                merge_count += 1
            else:
                m.letterboxd_uri = new
                m.save(update_fields=["letterboxd_uri"])
                update_count += 1
                self.stdout.write(f"UPDATED {m.id}: {old} -> {new}")

        self.stdout.write(self.style.SUCCESS(f"\nDone. Updated: {update_count}, Merged: {merge_count}"))

    def merge_movies(self, bad, good):
        with transaction.atomic():

            # WatchEvents
            for we in WatchEvent.objects.filter(movie=bad):
                exists = WatchEvent.objects.filter(
                    user=we.user,
                    movie=good,
                    posted_date=we.posted_date
                ).exists()

                if exists:
                    we.delete()
                else:
                    we.movie = good
                    we.save(update_fields=["movie"])

            # MovieUsers
            for mu in MovieUser.objects.filter(movie=bad):
                existing = MovieUser.objects.filter(
                    user=mu.user,
                    movie=good
                ).first()

                if existing:
                    if existing.rating is None and mu.rating is not None:
                        existing.rating = mu.rating
                    if not existing.review and mu.review:
                        existing.review = mu.review
                    if existing.watched_date is None and mu.watched_date is not None:
                        existing.watched_date = mu.watched_date
                    if mu.watch_status == "Watched":
                        existing.watch_status = "Watched"
                    if mu.liked:
                        existing.liked = True
                    if mu.in_watchlist:
                        existing.in_watchlist = True
                    if mu.rewatch:
                        existing.rewatch = True

                    existing.save()
                    mu.delete()
                else:
                    mu.movie = good
                    mu.save(update_fields=["movie"])

            # FilmBank
            for fb in FilmBank.objects.filter(movie=bad):
                existing = FilmBank.objects.filter(user=fb.user, movie=good).first()
                if existing:
                    fb.delete()
                else:
                    fb.movie = good
                    fb.save(update_fields=["movie"])
            transfer_tmdb_id = None
            if good.tmdb_id is None and bad.tmdb_id is not None:
                transfer_tmdb_id = bad.tmdb_id
                bad.tmdb_id = None
                bad.save(update_fields=["tmdb_id"])
                
            # Patch fields
            if good.year is None and bad.year is not None:
                good.year = bad.year

            if not good.overview and bad.overview:
                good.overview = bad.overview
            if not good.poster_url and bad.poster_url:
                good.poster_url = bad.poster_url
            if not good.tagline and bad.tagline:
                good.tagline = bad.tagline

            if transfer_tmdb_id is not None:
                good.tmdb_id = transfer_tmdb_id
            good.save()

            self.stdout.write(f"Deleting bad movie {bad.id}")
            bad.delete()