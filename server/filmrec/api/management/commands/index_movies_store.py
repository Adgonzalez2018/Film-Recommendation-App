#api/management/commands/index_movies_store.py
import os
from pathlib import Path
from openai import OpenAI

from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Create (if needed) and upload movies.jsonl to the global OpenAI vector store."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, required=True, help="Path to movies.txt")
        parser.add_argument("--store-id", type=str, default="", help="Existing vector_store_id (optional)")
        parser.add_argument("--name", type=str, default="FilmRec Movies Store")
    
    def handle(self, *args, **opts):
        client = OpenAI()

        file_path = Path(opts["file"])
        if not file_path.exists():
            raise FileNotFoundError(f"Missing file: {file_path}")

        # CLI flag takes priority, then env
        store_id = opts.get("store_id") or os.getenv("OPENAI_MOVIES_VECTOR_STORE_ID")

        if not store_id:
            vs = client.vector_stores.create(name=opts["name"])
            store_id = vs.id
            self.stdout.write(self.style.SUCCESS(f"Created vector store: {store_id}"))
            self.stdout.write(self.style.WARNING(
                f"Add to your env: OPENAI_MOVIES_VECTOR_STORE_ID={store_id}"
            ))
        else:
            self.stdout.write(f"Using existing store: {store_id}")
            # Delete old files so you're not paying for stale embeddings
            existing = client.vector_stores.files.list(vector_store_id=store_id)
            for vf in existing.data:
                client.vector_stores.files.delete(
                    vector_store_id=store_id, file_id=vf.id
                )
                self.stdout.write(f"  Deleted old file: {vf.id}")

        with file_path.open("rb") as f:
            batch = client.vector_stores.files.upload_and_poll(
                vector_store_id=store_id,
                file=f,
            )

        self.stdout.write(self.style.SUCCESS(
            f"Uploaded and indexed: {file_path} | status: {batch.status}"
        ))
        self.stdout.write(self.style.SUCCESS(f"Store ID: {store_id}"))