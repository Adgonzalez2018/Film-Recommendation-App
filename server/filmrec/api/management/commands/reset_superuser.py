from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from openai import OpenAI

from api.models import WatchEvent, MovieUser, FilmBank, ImportBatch
from api.services.taste_store import get_taste_file_path

User = get_user_model()


class Command(BaseCommand):
    help = "Reset all app data for a user, including taste profile artifacts."

    def add_arguments(self, parser):
        parser.add_argument("--username", type=str, required=True)
        parser.add_argument(
            "--out",
            type=str,
            default="taste_out",
            help="Base output directory for canonical taste files.",
        )
        parser.add_argument(
            "--skip-openai",
            action="store_true",
            help="Skip deleting files from the user's OpenAI taste vector store.",
        )

    def handle(self, *args, **opts):
        user = User.objects.get(username=opts["username"])
        out = opts["out"]
        skip_openai = opts["skip_openai"]

        # --- delete user app data ---
        WatchEvent.objects.filter(user=user).delete()
        MovieUser.objects.filter(user=user).delete()
        FilmBank.objects.filter(user=user).delete()
        ImportBatch.objects.filter(user=user).delete()

        # --- delete local taste file ---
        taste_file_path = get_taste_file_path(user_id=user.id, out=out)
        if taste_file_path.exists():
            taste_file_path.unlink()
            self.stdout.write(self.style.SUCCESS(f"Deleted local taste file: {taste_file_path}"))
        else:
            self.stdout.write(f"No local taste file found at: {taste_file_path}")

        # --- clear OpenAI vector store files if present ---
        store_id = user.taste_vector_store_id
        if store_id and not skip_openai:
            try:
                client = OpenAI()
                existing = client.vector_stores.files.list(vector_store_id=store_id)
                for vf in existing.data:
                    client.vector_stores.files.delete(vector_store_id=store_id, file_id=vf.id)
                self.stdout.write(self.style.SUCCESS(f"Cleared OpenAI taste store files for {store_id}"))
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f"Could not clear OpenAI taste store files for {store_id}: {e}"
                ))

        # --- reset user fields ---
        user.manual_import_count = 0
        user.rss_import_count = 0
        user.last_sync = None
        user.last_manual_sync = None
        user.last_rss_sync = None
        user.last_rss_account_switch = None
        user.last_taste_rebuild_at = None
        user.letterboxd_username = ""
        user.taste_vector_store_id = None
        user.has_skipped_onboarding = False
        user.save(update_fields=[
            "manual_import_count",
            "rss_import_count",
            "last_sync",
            "last_manual_sync",
            "last_rss_sync",
            "last_rss_account_switch",
            "last_taste_rebuild_at",
            "letterboxd_username",
            "taste_vector_store_id",
            "has_skipped_onboarding",
        ])

        self.stdout.write(self.style.SUCCESS(f"Reset data for {user.username}"))