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
        delete_count = result["deleted_count"]

        # Create store if missing
        if not store_id:
            name_prefix = opts.get("name_prefix", "FilmRec Taste Store")
            vs = client.vector_stores.create(name=f"{name_prefix} (user={user.id})")
            store_id = vs.id
            user.taste_vector_store_id = store_id
            user.save(update_fields=["taste_vector_store_id"])
            self.stdout.write(self.style.SUCCESS(f"Created taste vector store: {store_id}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Using taste vector store: {store_id}"))

        # delete ALL existing files in parallel instead of serially
        # with 10 works and ~50 old files this goes from ~50s -> 50s
        try:
            existing = client.vector_stores.files.list(vector_store_id=store_id)
            file_ids = [vf.id for vf in existing.data]
            if file_ids:
                failed = []
                with ThreadPoolExecutor(max_workers=DELETE_WORKERS) as pool:
                    futures = {
                        pool.submit(_delete_file, client, store_id, fid): fid
                        for fid in file_ids
                    }
                    for future in as_completed(futures):
                        fid = futures[future]
                        try:
                            future.result()
                        except Exception as exc:
                            failed.append((fid, str(exc)))

                    if failed:
                        raise RuntimeError(
                            f"Failed to delete {len(failed)} file(s): {failed}"
                        )
                    self.stdout.write(
                        self.style.SUCCESS(f"Delete {len(file_ids)} old file(s) in parallel")
                    )
            else:
                self.stdout.write(self.style.SUCCESS("No existing files to clear."))
        except Exception as e:
            raise RuntimeError(f"Failed clearing existing taste store files: {e}")
        
        try: 
            # upload + poll until indexed
            with file_path.open("rb") as f:
                client.vector_stores.files.upload_and_poll(
                    vector_store_id = store_id,
                    file=f,
                )
        except Exception as e:
            raise RuntimeError(f"Upload failed: {e}")
        
        self.stdout.write(self.style.SUCCESS(f"Uploaded and indexed: {file_path}"))
        self.stdout.write(self.style.SUCCESS(f"user.taste_vector_store_id={store_id}"))
