from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from api.models import (
    Movie,
    MovieUser,
    WatchEvent,
    MovieGenre,
    MovieCast,
    MovieCrew,
    FilmBank,
)


def is_canonical_letterboxd_uri(uri: str | None) -> bool:
    return bool(uri and "/film/" in uri)


def movie_score(movie: Movie) -> tuple:
    """
    Higher is better.
    Prefer:
    1) tmdb_id present
    2) canonical letterboxd film uri present
    3) richer metadata
    4) lower id as stable tie-breaker
    """
    metadata_score = sum(
        1
        for v in [
            movie.runtime,
            movie.overview,
            movie.poster_url,
            movie.language,
            movie.country,
            movie.avg_rating,
            movie.budget,
            movie.revenue,
        ]
        if v not in (None, "", 0, 0.0)
    )

    return (
        1 if movie.tmdb_id else 0,
        1 if is_canonical_letterboxd_uri(movie.letterboxd_uri) else 0,
        metadata_score,
        -movie.id,  # lower id wins tie
    )


def merge_movie_fields(target: Movie, source: Movie) -> bool:
    changed = False

    if target.tmdb_id is None and source.tmdb_id is not None:
        target.tmdb_id = source.tmdb_id
        changed = True

    if not target.letterboxd_uri and is_canonical_letterboxd_uri(source.letterboxd_uri):
        target.letterboxd_uri = source.letterboxd_uri
        changed = True

    if (not target.title or target.title == "Unknown") and source.title:
        target.title = source.title
        changed = True

    if target.year is None and source.year is not None:
        target.year = source.year
        changed = True

    for field in [
        "overview",
        "avg_rating",
        "budget",
        "revenue",
        "runtime",
        "language",
        "country",
        "poster_url",
        "movie_vector_store_id",
        "enrichment_status",
        "enrichment_attempts",
        "last_enriched_at",
        "enrichment_error",
    ]:
        if getattr(target, field) in (None, "", 0, 0.0) and getattr(source, field) not in (None, "", 0, 0.0):
            setattr(target, field, getattr(source, field))
            changed = True

    return changed


def merge_movieuser(target_mu: MovieUser, source_mu: MovieUser) -> bool:
    changed = False

    if target_mu.rating is None and source_mu.rating is not None:
        target_mu.rating = source_mu.rating
        changed = True

    if not target_mu.review and source_mu.review:
        target_mu.review = source_mu.review
        changed = True

    # Prefer Watched over anything else
    if target_mu.watch_status != "Watched" and source_mu.watch_status == "Watched":
        target_mu.watch_status = "Watched"
        changed = True

    # Keep the most recent watched date
    if source_mu.watched_date and (
        not target_mu.watched_date or source_mu.watched_date > target_mu.watched_date
    ):
        target_mu.watched_date = source_mu.watched_date
        changed = True

    if source_mu.liked and not target_mu.liked:
        target_mu.liked = True
        changed = True

    # If already watched, watchlist should usually be false
    desired_watchlist = target_mu.in_watchlist or source_mu.in_watchlist
    if target_mu.watch_status == "Watched":
        desired_watchlist = False
    if target_mu.in_watchlist != desired_watchlist:
        target_mu.in_watchlist = desired_watchlist
        changed = True

    if source_mu.rewatch and not target_mu.rewatch:
        target_mu.rewatch = True
        changed = True

    return changed


class Command(BaseCommand):
    help = "Merge duplicate Movie rows by (title, year) and re-point related records safely."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--title", type=str, default=None, help="Only process one title")
        parser.add_argument("--year", type=int, default=None, help="Only process one year")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        only_title = options["title"]
        only_year = options["year"]

        dupes = (
            Movie.objects.values("title", "year")
            .annotate(c=Count("id"))
            .filter(c__gt=1)
            .order_by("-c", "title", "year")
        )

        if only_title is not None:
            dupes = dupes.filter(title=only_title)
        if only_year is not None:
            dupes = dupes.filter(year=only_year)
        if limit:
            dupes = dupes[:limit]

        groups = list(dupes)
        self.stdout.write(f"Found {len(groups)} duplicate title/year groups")

        total_movies_deleted = 0
        total_groups_merged = 0

        for g in groups:
            title = g["title"]
            year = g["year"]

            movies = list(Movie.objects.filter(title=title, year=year).order_by("id"))
            if len(movies) < 2:
                continue

            target = max(movies, key=movie_score)
            sources = [m for m in movies if m.id != target.id]

            self.stdout.write(
                f"\nMerging {len(sources)} duplicates into Movie<{target.id}>: {title} ({year})"
            )

            if dry_run:
                self.stdout.write(
                    f"  target={target.id} sources={[m.id for m in sources]}"
                )
                total_movies_deleted += len(sources)
                total_groups_merged += 1
                continue

            with transaction.atomic():
                changed = False

                for source in sources:
                    if merge_movie_fields(target, source):
                        changed = True

                if changed:
                    target.save()

                # MovieUser
                for source in sources:
                    source_mus = list(MovieUser.objects.filter(movie=source))
                    for smu in source_mus:
                        try:
                            tmu = MovieUser.objects.get(user=smu.user, movie=target)
                            if merge_movieuser(tmu, smu):
                                tmu.save()
                            smu.delete()
                        except MovieUser.DoesNotExist:
                            smu.movie = target
                            smu.save(update_fields=["movie"])

                # WatchEvent
                for source in sources:
                    source_events = list(WatchEvent.objects.filter(movie=source))
                    for se in source_events:
                        existing = (
                            WatchEvent.objects.filter(user=se.user, event_key=se.event_key)
                            .exclude(id=se.id)
                            .first()
                        )
                        if existing:
                            # Preserve missing info on the existing event if source has it
                            event_changed = False
                            if existing.movie_id != target.id:
                                existing.movie = target
                                event_changed = True
                            if not existing.watched_date and se.watched_date:
                                existing.watched_date = se.watched_date
                                event_changed = True
                            if not existing.entry_url and se.entry_url:
                                existing.entry_url = se.entry_url
                                event_changed = True
                            if se.rewatch and not existing.rewatch:
                                existing.rewatch = True
                                event_changed = True
                            if event_changed:
                                existing.save()
                            se.delete()
                        else:
                            se.movie = target
                            se.save(update_fields=["movie"])

                # MovieGenre
                for source in sources:
                    for rel in list(MovieGenre.objects.filter(movie=source)):
                        exists = MovieGenre.objects.filter(movie=target, genre=rel.genre).exists()
                        if exists:
                            rel.delete()
                        else:
                            rel.movie = target
                            rel.save(update_fields=["movie"])

                # MovieCast
                for source in sources:
                    for rel in list(MovieCast.objects.filter(movie=source)):
                        exists = MovieCast.objects.filter(movie=target, person=rel.person).exists()
                        if exists:
                            rel.delete()
                        else:
                            rel.movie = target
                            rel.save(update_fields=["movie"])

                # MovieCrew
                for source in sources:
                    for rel in list(MovieCrew.objects.filter(movie=source)):
                        exists = MovieCrew.objects.filter(
                            movie=target, person=rel.person, job=rel.job
                        ).exists()
                        if exists:
                            rel.delete()
                        else:
                            rel.movie = target
                            rel.save(update_fields=["movie"])

                # FilmBank
                for source in sources:
                    for rel in list(FilmBank.objects.filter(movie=source)):
                        exists = FilmBank.objects.filter(user=rel.user, movie=target).exists()
                        if exists:
                            rel.delete()
                        else:
                            rel.movie = target
                            rel.save(update_fields=["movie"])

                deleted_count = 0
                for source in sources:
                    source.delete()
                    deleted_count += 1

                total_movies_deleted += deleted_count
                total_groups_merged += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Groups merged: {total_groups_merged}, duplicate movies deleted: {total_movies_deleted}"
            )
        )