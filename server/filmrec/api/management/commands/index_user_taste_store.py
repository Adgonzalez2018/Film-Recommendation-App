# Vector store per Movie

import os
from pathlib import Path
from openai import OpenAI

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()

class Command(BaseCommand):
    help = "Create/Update a user's taste vector store from taste_user_id.jsonl"
    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--jsonl", type=str, required=True, help="Path to taste_user_id,jsonl")
        parser.add_argument("--name-prefix", type=str, default="FilmRec Taste Store")
    
    def handle(self, *args, **opts):
        client = OpenAI()

        user = User.objects.get(id=opts["user-id"])
        jsonl_path = Path(opts["jsonl"])
        if not jsonl_path.exists():
            raise FileNotFoundError(f"Missing File: {jsonl_path}")
        
        store_id = getattr(user, "taste_vectore_store_id", None)

        # Create store if missing
        if not store_id:
            vs = client.vector_stores.create(name=f"{opts['name-prefix']} (user={user.id})")
            store_id = vs.id
            user.taste_vector_store_id = store_id
            user.save(update_fields=["taste_vectore_store_id"])
            self.stdout.write(self.style.SUCCESS(f"Created taste vector store: {store_id}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Using taste vector store: {store_id}"))

        # upload + poll until indexed
        with jsonl_path.open("rb") as f:
            client.vector_stores.files.upload_and_poll(
                vector_store_id = store_id,
                file=f,
            )
        self.stdout.write(self.style.SUCCESS(f"Uploaded and indexed: {jsonl_path}"))
        self.stdout.write(self.style.SUCCESS(f"user.taste.vector_store_id={store_id}"))