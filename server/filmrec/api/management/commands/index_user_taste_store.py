# Vector store per Movie
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from api.services.taste_store import get_taste_file_path
from api.services.taste_index import ensure_taste_indexed

class Command(BaseCommand):
    help = "Create/Update a user's taste vector store from taste_user_id.txt"
    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--file", type=str, required=True, help="Path to taste_user_id.txt")
        parser.add_argument("--out", type=str, default="taste_out", help="base output director for canonical taste files.")
        parser.add_argument("--name-prefix", type=str, default="FilmRec Taste Store")

    def handle(self, *args, **opts):
        user_id = opts["user_id"]
        out = opts["out"]
        explicit_file = opts.get("file")
        name_prefix = opts["name_prefix"]
        file_path = Path(explicit_file) if explicit_file else get_taste_file_path(user_id=user_id, out=out)
        if not file_path.exists():
            raise FileNotFoundError(f"Missing File: {file_path}")
        
        result = ensure_taste_indexed(
            user_id=user_id,
            file_path=file_path,
            name_prefix=name_prefix,
            clear_existing=True,
        )
        deleted_count = result["deleted_count"]
        store_id = result["store_id"]

        if deleted_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f"Deleted {deleted_count} old file(s) from {store_id}")
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"No existing files to clear in store {store_id}"))
        
        self.stdout.write(self.style.SUCCESS(f"Uploaded and indexed: {file_path}"))
        self.stdout.write(self.style.SUCCESS(f"user.taste_vector_store_id={store_id}"))
