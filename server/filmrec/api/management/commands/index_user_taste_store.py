# Vector store per Movie
from pathlib import Path
from openai import OpenAI

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()

class Command(BaseCommand):
    help = "Create/Update a user's taste vector store from taste_user_id.txt"
    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--file", type=str, required=True, help="Path to taste_user_id.txt")
        parser.add_argument("--name-prefix", type=str, default="FilmRec Taste Store")

    def handle(self, *args, **opts):
        client = OpenAI()

        user = User.objects.get(id=opts["user-id"])
        file_path = Path(opts["file"])
        if not file_path.exists():
            raise FileNotFoundError(f"Missing File: {file_path}")
        
        store_id = getattr(user, "taste_vector_store_id", None)

        # Create store if missing
        if not store_id:
            vs = client.vector_stores.create(name=f"{opts['name-prefix']} (user={user.id})")
            store_id = vs.id
            user.taste_vector_store_id = store_id
            user.save(update_fields=["taste_vector_store_id"])
            self.stdout.write(self.style.SUCCESS(f"Created taste vector store: {store_id}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Using taste vector store: {store_id}"))

        # upload + poll until indexed
        with file_path.open("rb") as f:
            client.vector_stores.files.upload_and_poll(
                vector_store_id = store_id,
                file=f,
            )
        self.stdout.write(self.style.SUCCESS(f"Uploaded and indexed: {file_path}"))
        self.stdout.write(self.style.SUCCESS(f"user.taste.vector_store_id={store_id}"))