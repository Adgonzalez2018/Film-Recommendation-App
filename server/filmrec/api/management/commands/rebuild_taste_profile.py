#api/management/commands/rebuild_taste_profile.py
from django.core.management.base import BaseCommand

from api.services.taste_index import ensure_taste_indexed
from api.services.taste_profile import build_initial_taste_artifacts
from api.services.feedback_profile import build_feedback_taste_artifacts
from api.services.taste_store import write_taste_file
from api.services.taste_merge import merge_taste_artifacts

class Command(BaseCommand):
    help = "Rebuild user;s taste profile TXT File."

    def add_arguments(self,parser):
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--out", type=str, default="taste_out")
        parser.add_argument(
            "--reason",
            type=str,
            default="manual",
            help="Why the rebuild is being run (manual, rss, csv, feedback, etc)."
        )
    def handle(self, *args, **opts):
        user_id = opts["user_id"]
        out = opts["out"]
        reason = opts["reason"]

        try:
            baseline_artifacts = build_initial_taste_artifacts(user_id=user_id)
            if not baseline_artifacts.get("summary_doc"):
                self.stdout.write(
                    self.style.WARNING(f"User {user_id} has no baseline taste data.")
                )
                return
            
            feedback_artifacts = build_feedback_taste_artifacts(user_id=user_id)

            merged = merge_taste_artifacts(
                baseline_artifacts=baseline_artifacts,
                feedback_artifacts=feedback_artifacts
            )
            summary_doc = {
                **merged["summary_doc"],
                "rebuild_reason": reason,
            }

            merged_docs = [
                d for d in merged["merged_docs"]
                if d.get("type") != "merged_summary"
            ]

            out_path = write_taste_file(
                user_id=user_id,
                summary_doc=summary_doc,
                docs=merged_docs,
                out=out,
            )

            index_result = ensure_taste_indexed(
                user_id=user_id,
                file_path=out_path,
            )
            base_counts = baseline_artifacts.get("counts", {})
            fb_counts = (feedback_artifacts or {}).get("counts", {})

            self.stdout.write(self.style.SUCCESS(f"Rebuilt {out_path}"))
            self.stdout.write(
                self.style.SUCCESS(
                    " | ".join(
                        [
                            f"reason={reason}",
                            f"loved={base_counts.get('loved', 0)}",
                            f"disliked={base_counts.get('disliked', 0)}",
                            f"recent={base_counts.get('recent', 0)}",
                            f"feedback={fb_counts.get('total_feedback_rows', 0)}",
                            f"Indexed store={index_result['store_id']} deleted={index_result['deleted_count']}"
                        ]
                    )
                )
            )
            self.stdout.write(
                self.style.SUCCESS(f"File size: {out_path.stat().st_size / 1024:.1f} KB")
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
            raise