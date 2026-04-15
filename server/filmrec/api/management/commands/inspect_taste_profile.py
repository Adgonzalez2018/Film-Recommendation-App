from pathlib import Path
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

User = get_user_model()


class Command(BaseCommand):
    help = "Inspect a user's taste profile DB state and local generated taste file."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument(
            "--out-dir",
            type=str,
            default="taste_out",
            help="Directory where taste files are written",
        )
        parser.add_argument(
            "--show-full",
            action="store_true",
            help="Print the full file contents instead of a preview",
        )

    def handle(self, *args, **opts):
        user_id = opts["user_id"]
        out_dir = opts["out_dir"]
        show_full = opts["show_full"]

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise CommandError(f"User {user_id} does not exist.")

        self.stdout.write(self.style.SUCCESS("=== USER DB STATE ==="))
        self.stdout.write(f"id: {user.id}")
        self.stdout.write(f"email/username: {user.username}")
        self.stdout.write(f"letterboxd_username: {user.letterboxd_username}")
        self.stdout.write(f"manual_import_count: {user.manual_import_count}")
        self.stdout.write(f"rss_import_count: {user.rss_import_count}")
        self.stdout.write(f"last_sync: {user.last_sync}")
        self.stdout.write(f"last_manual_sync: {user.last_manual_sync}")
        self.stdout.write(f"last_rss_sync: {user.last_rss_sync}")
        self.stdout.write(f"taste_vector_store_id: {user.taste_vector_store_id}")
        self.stdout.write(f"last_taste_rebuild_at: {user.last_taste_rebuild_at}")
        self.stdout.write("")

        # common filename pattern
        candidate_paths = [
            Path(out_dir) / f"user_taste_{user.id}.txt",
            Path(out_dir) / f"taste_user_{user.id}.txt",
            Path(settings.BASE_DIR) / out_dir / f"user_taste_{user.id}.txt",
            Path(settings.BASE_DIR) / out_dir / f"taste_user_{user.id}.txt",
        ]

        taste_path = next((p for p in candidate_paths if p.exists()), None)

        self.stdout.write(self.style.SUCCESS("=== LOCAL TASTE FILE ==="))
        if not taste_path:
            self.stdout.write("No local taste file found.")
            self.stdout.write("Checked:")
            for p in candidate_paths:
                self.stdout.write(f"  - {p}")
            return

        self.stdout.write(f"path: {taste_path}")
        raw = taste_path.read_text(encoding="utf-8").strip()

        if not raw:
            self.stdout.write("File exists but is empty.")
            return

        lines = raw.splitlines()
        self.stdout.write(f"line_count: {len(lines)}")
        self.stdout.write("")

        # first line is often summary doc in your flow
        first_line = lines[0]
        self.stdout.write(self.style.SUCCESS("=== SUMMARY DOC (FIRST LINE) ==="))
        try:
            parsed = json.loads(first_line)
            self.stdout.write(json.dumps(parsed, indent=2, ensure_ascii=False))
        except Exception:
            self.stdout.write(first_line[:3000])

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== EVIDENCE DOC PREVIEW ==="))

        if show_full:
            self.stdout.write(raw)
        else:
            preview = "\n".join(lines[:30])
            self.stdout.write(preview)
            if len(lines) > 30:
                self.stdout.write("")
                self.stdout.write(f"... truncated ({len(lines) - 30} more lines)")