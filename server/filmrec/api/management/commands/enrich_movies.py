from django.core.management.base import BaseCommand
from api.models import Movie
from api.services.tmdb import upsert_tmdb_movie

import re

def _title_to_slug(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[''']", "", s)
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s

class Command(BaseCommand):
    help = "Backfill tagline, keywords, collection_name for existing movies"

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

        ok, failed = 0, 0
        for i, mv in enumerate(qs, 1):
            try:
                upsert_tmdb_movie(mv.tmdb_id)
                mv.refresh_from_db()
                if not mv.letterboxd_uri and mv.title:
                    slug = _title_to_slug(mv.title)
                    if slug:
                        Movie.objects.filter(pk=mv.pk).update(
                            letterboxd_uri=f"https://letterboxd.com/film/{slug}/"
                        )
                ok += 1
            except Exception as e:
                failed += 1
                self.stderr.write(f"Failed tmdb_id={mv.tmdb_id}: {e}")

            if i % 100 == 0:
                self.stdout.write(f"  {i}/{total} (ok={ok} failed={failed})")

        self.stdout.write(self.style.SUCCESS(f"Done. ok={ok} failed={failed}"))