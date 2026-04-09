# management/commands/enrich_movies.py
from django.core.management.base import BaseCommand
from api.models import Movie
from api.services.tmdb import fetch_tmdb_details  # you'll extend this

class Command(BaseCommand):
    help = "Backfill tagline, keywords, collection for existing movies"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--overwrite", action="store_true")

    def handle(self, *args, **options):
        qs = Movie.objects.filter(tmdb_id__isnull=False)
        if not options["overwrite"]:
            qs = qs.filter(keywords__isnull=True)  # only unenriched
        if options["limit"]:
            qs = qs[:options["limit"]]

        total = qs.count()
        self.stdout.write(f"Enriching {total} movies...")

        for i, mv in enumerate(qs, 1):
            try:
                enrich_movie(mv)
                if i % 100 == 0:
                    self.stdout.write(f"  {i}/{total}")
            except Exception as e:
                self.stderr.write(f"Failed tmdb_id={mv.tmdb_id}: {e}")

        self.stdout.write(self.style.SUCCESS("Done."))