import os
import time
import requests

from django.core.management.base import BaseCommand, CommandError

from api.models import Movie
from api.services.tmdb import upsert_tmdb_movie


TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"


class Command(BaseCommand):
    help = "Seed the DB with TMDB movies from list/discover endpoints"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=str,
            default="popular",
            choices=["popular", "top_rated", "now_playing", "upcoming", "discover"],
            help="TMDB source endpoint",
        )
        parser.add_argument(
            "--pages",
            type=int,
            default=5,
            help="Number of TMDB pages to fetch",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.15,
            help="Delay between movie upserts",
        )
        parser.add_argument(
            "--min-year",
            type=int,
            default=None,
            help="Minimum primary release year (discover only)",
        )
        parser.add_argument(
            "--max-year",
            type=int,
            default=None,
            help="Maximum primary release year (discover only)",
        )
        parser.add_argument(
            "--genre",
            type=int,
            default=None,
            help="TMDB genre id (discover only)",
        )
        parser.add_argument(
            "--vote-count-gte",
            type=int,
            default=50,
            help="Minimum vote count (discover only)",
        )
        parser.add_argument(
            "--vote-average-gte",
            type=float,
            default=None,
            help="Minimum vote average (discover only)",
        )
        parser.add_argument(
            "--language",
            type=str,
            default="en-US",
            help="TMDB language",
        )
        parser.add_argument(
            "--region",
            type=str,
            default=None,
            help="Optional TMDB region, e.g. US",
        )
        parser.add_argument(
            "--sort-by",
            type=str,
            default="popularity.desc",
            help="Discover sort order, e.g. popularity.desc or vote_average.desc",
        )
        parser.add_argument(
            "--cast-limit",
            type=int,
            default=12,
            help="How many cast members to store per movie",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip movies whose tmdb_id already exists locally",
        )
        parser.add_argument(
            "--stop-after",
            type=int,
            default=None,
            help="Stop after N successful upserts",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch ids only, do not write movies to DB",
        )

    def handle(self, *args, **options):
        if not TMDB_API_KEY:
            raise CommandError("TMDB_API_KEY is not set")

        source = options["source"]
        pages = max(1, options["pages"])
        delay = max(0.0, options["delay"])
        min_year = options["min_year"]
        max_year = options["max_year"]
        genre = options["genre"]
        vote_count_gte = options["vote_count_gte"]
        vote_average_gte = options["vote_average_gte"]
        language = options["language"]
        region = options["region"]
        sort_by = options["sort_by"]
        cast_limit = options["cast_limit"]
        skip_existing = options["skip_existing"]
        stop_after = options["stop_after"]
        dry_run = options["dry_run"]

        upserted = 0
        skipped = 0
        failed = 0
        fetched_ids = 0

        self.stdout.write(
            self.style.NOTICE(
                f"Starting TMDB seed: source={source}, pages={pages}, language={language}"
            )
        )

        for page in range(1, pages + 1):
            endpoint, params = self._build_request(
                source=source,
                page=page,
                language=language,
                region=region,
                sort_by=sort_by,
                min_year=min_year,
                max_year=max_year,
                genre=genre,
                vote_count_gte=vote_count_gte,
                vote_average_gte=vote_average_gte,
            )

            payload = self._tmdb_get(endpoint, params=params)
            results = payload.get("results", []) or []

            self.stdout.write(f"Page {page}: {len(results)} results")

            for row in results:
                tmdb_id = row.get("id")
                if not tmdb_id:
                    continue

                fetched_ids += 1

                if skip_existing and Movie.objects.filter(tmdb_id=tmdb_id).exists():
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(f"[dry-run] tmdb_id={tmdb_id}")
                    continue

                try:
                    movie = upsert_tmdb_movie(tmdb_id=tmdb_id, cast_limit=cast_limit)
                    upserted += 1

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[{upserted}] {movie.title} (tmdb_id={tmdb_id})"
                        )
                    )

                    if stop_after and upserted >= stop_after:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Done early. fetched_ids={fetched_ids}, upserted={upserted}, "
                                f"skipped={skipped}, failed={failed}"
                            )
                        )
                        return

                except Exception as e:
                    failed += 1
                    self.stderr.write(
                        self.style.WARNING(f"Failed tmdb_id={tmdb_id}: {e}")
                    )

                if delay:
                    time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"Finished seed. fetched_ids={fetched_ids}, upserted={upserted}, "
                f"skipped={skipped}, failed={failed}"
            )
        )

    def _build_request(
        self,
        *,
        source,
        page,
        language,
        region,
        sort_by,
        min_year,
        max_year,
        genre,
        vote_count_gte,
        vote_average_gte,
    ):
        if source == "discover":
            endpoint = "/discover/movie"
            params = {
                "api_key": TMDB_API_KEY,
                "language": language,
                "page": page,
                "sort_by": sort_by,
                "include_adult": "false",
                "include_video": "false",
                "vote_count.gte": vote_count_gte,
            }

            if region:
                params["region"] = region
            if min_year is not None:
                params["primary_release_date.gte"] = f"{min_year}-01-01"
            if max_year is not None:
                params["primary_release_date.lte"] = f"{max_year}-12-31"
            if genre is not None:
                params["with_genres"] = genre
            if vote_average_gte is not None:
                params["vote_average.gte"] = vote_average_gte
        else:
            endpoint = f"/movie/{source}"
            params = {
                "api_key": TMDB_API_KEY,
                "language": language,
                "page": page,
            }
            if region:
                params["region"] = region

        return endpoint, params

    def _tmdb_get(self, endpoint, params):
        url = f"{BASE_URL}{endpoint}"
        r = requests.get(url, params=params, timeout=20)
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            raise CommandError(f"TMDB request failed: {r.status_code} {url}") from e
        return r.json()