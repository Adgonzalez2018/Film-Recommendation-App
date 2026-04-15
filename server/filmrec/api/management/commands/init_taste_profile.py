#api/management/commands/rebuild_taste_profile.py

from django.core.management.base import BaseCommand

from api.services.taste_profile import build_initial_taste_artifacts
from api.services.taste_store import write_taste_file, flatten_taste_docs
from api.services.taste_index import ensure_taste_indexed

class Command(BaseCommand):
    help = "Initialize the baseline taste profile TXT file for a user."

    def add_arguments(self,parser):
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--out", type=str, default="taste_out")

    def handle(self, *args, **opts):
        user_id = opts["user_id"]
        out = opts["out"]

        # optimizeation: single queryset with all prefetches - evaluated once,
        # then sliced in Python. Eliminates the 3 separate DB round-trips.
        try:
            artifacts = build_initial_taste_artifacts(user_id=user_id)

            summary_doc = artifacts["summary_doc"]
            loved_docs = artifacts["loved_docs"]
            disliked_docs = artifacts["disliked_docs"]
            recent_docs = artifacts["recent_docs"]
            counts = artifacts["counts"]
            
            if not summary_doc:
                self.stdout.write(self.style.WARNING(f"User {user_id} has no rated movies."))
                return
            
            all_docs = flatten_taste_docs(
                loved_docs=loved_docs,
                disliked_docs=disliked_docs,
                recent_docs=recent_docs,
            )
            out_path = write_taste_file(
                user_id=user_id,
                summary_doc=summary_doc,
                docs=all_docs,
                out=out,
            )

            index_result = ensure_taste_indexed(
                user_id=user_id,
                file_path=out_path,
            )

            self.stdout.write(self.style.SUCCESS(f"Wrote {out_path}"))
            self.stdout.write(self.style.SUCCESS(
                f"Counts: loved={counts['loved']} disliked={counts['disliked']} recent={counts['recent']}"
                ))
            self.stdout.write(
                self.style.SUCCESS(
                    f"Indexed store={index_result['store_id']} deleted={index_result['deleted_count']}"
                )
            )
            self.stdout.write(self.style.SUCCESS(f"File size: {out_path.stat().st_size / 1024:.1f} KB"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
            raise