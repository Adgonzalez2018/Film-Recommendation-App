# Vector store per Movie
import os
from pathlib import Path
from openai import OpenAI

from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Create (if needed) and upload movies.jsonl to the global OpenAI vector store."

    def add_arguments(self, parser):
        parser.add_argument("--jsonl", type=str, required=True, help="Path to movies.jsonl")
        parser.add_argument("--store-id", type=str, default="", help="Existing vector_store_id (optional)")
        parser.add_argument("--name", type=str, default="FilmRec Movies Store")
    
    def handle(self, *args, **opts):
        client = OpenAI()

        jsonl_path = Path(opts["jsonl"])
        if not jsonl_path.exists():
            raise FileNotFoundError(f"Missing File: {jsonl_path}")
        
        store_id = opts["store-id"] or os.getenv("OPENAI_MOVIES_VECTOR_STORE_ID")

        # Create store if missing
        if not store_id:
            vs = client.vector_stores.create(name=opts["name"])
            store_id = vs.id
            self.stdout.write(self.style.SUCCESS(f"Created movies vector store: {store_id}"))
            self.stdout.write(self.style.WARNING(
                "Set OPENAI_MOVIES_CECTOR_STORE_ID to this valuse so you reuse it."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f"Using movies vector store: {store_id}"))

        # upload + poll until indexed
        with jsonl_path.open("rb") as f:
            client.vector_stores.files.upload_and_poll(
                vector_store_id=store_id,
                file=f,
            )

        self.stdout.write(self.style.SUCCESS(f"Uploaded and indexed: {jsonl_path}"))
        self.stdout.write(self.style.SUCCESS(f"movies_Store_id =  {store_id}"))
