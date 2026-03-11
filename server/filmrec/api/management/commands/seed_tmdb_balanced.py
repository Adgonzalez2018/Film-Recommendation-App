from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run a balanced TMDB corpus seed plan"

    def handle(self, *args, **options):
        plan = [
            {"source": "popular", "pages": 10, "skip_existing": True},
            {"source": "top_rated", "pages": 10, "skip_existing": True},
            {"source": "now_playing", "pages": 5, "skip_existing": True},
            {"source": "upcoming", "pages": 5, "skip_existing": True},

            {"source": "discover", "min_year": 1950, "max_year": 1979, "pages": 8, "skip_existing": True},
            {"source": "discover", "min_year": 1980, "max_year": 1999, "pages": 8, "skip_existing": True},
            {"source": "discover", "min_year": 2000, "max_year": 2009, "pages": 8, "skip_existing": True},
            {"source": "discover", "min_year": 2010, "max_year": 2019, "pages": 8, "skip_existing": True},
            {"source": "discover", "min_year": 2020, "max_year": 2026, "pages": 8, "skip_existing": True},

            {"source": "discover", "genre": 27, "pages": 4, "skip_existing": True},    # horror
            {"source": "discover", "genre": 16, "pages": 4, "skip_existing": True},    # animation
            {"source": "discover", "genre": 99, "pages": 4, "skip_existing": True},    # documentary
            {"source": "discover", "genre": 878, "pages": 4, "skip_existing": True},   # sci-fi
            {"source": "discover", "genre": 9648, "pages": 4, "skip_existing": True},  # mystery
            {"source": "discover", "genre": 80, "pages": 4, "skip_existing": True},     # crime
            {"source": "discover", "genre": 14, "pages": 4, "skip_existing": True},     # fantasy
        ]

        for i, kwargs in enumerate(plan, start=1):
            self.stdout.write(self.style.NOTICE(f"\n[{i}/{len(plan)}] Running {kwargs}"))
            call_command("seed_tmdb_corpus", **kwargs)

        self.stdout.write(self.style.SUCCESS("\nBalanced TMDB seed complete."))