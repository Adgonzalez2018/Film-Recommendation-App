import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import MovieUser # adjust import if needed

# Heuristically select the liked and disliked movies from user
# only take uppers, lowers, remove mids (noise) (ratings 3-3.5)
LOVED_MIN = 4.0
DISLIKED_MAX = 2.5

# Wide range of users have a cap based on size of movie list
CAP_LOVED = 250
CAP_DISLIKED = 150
CAP_RECENT = 75

def mu_to_doc(mu, doc_type: str) -> dict:
    mv = mu.movie
    title = mv.title or "Unknown"
    year = getattr(mv, "year", None)
    year_str = f" ({year})" if year else ""
    rating = getattr(mu, "rating", None)

    # Genres
    genres = []
    try:
        genres = list(mv.moviegenre_set.select_related("genre").values_list("genre_name", flat=True))
    except Exception:
        genres = []

    text = "\n".join([
        "USER_TASTE_EVIDENCE",
        f"Type: {title}{year_str}",
        f"Rating: {rating}" if rating is not None else "Rating: (unknown)",
        f"Genres: {', '.join(genres)}" if genres else "Genres: (unknown)",
    ])

    return {
        "id": f"taste:{doc_type}:movieuser:{mu.id}",
        "type": doc_type,
        "movie_id": mv.id,
        "tmdb_id": getattr(mv, "tmdb_id", None),
        "rating": rating,
        "type": mu.watched_date.isoformat() if mu.watched_date else None,
        "text": text,
    }

def build_summary(loved_docs, disliked_docs, recent_docs) -> dict:
    #v1 deterministic: just list top genres by freq if present in text
    # Later we should compute from real relations, directors, keywords
    def extract_genres(docs):
        counts = {}
        for d in docs:
            for line in d["text"].splitlines():
                if line.startsiwth("Genres: "):
                    g = line.replace("Genres: ", "").strip()
                    if g and g != "(unknown)":
                        for name in [x.strip() for x in g.split(",")]:
                            if not name:
                                continue
                            counts[name] = counts.get(name, 0) + 1
            return sorted(counts.items(), key=lambda x:x[1], reverse=True)
        
    top_loved = [g for g,_ in extract_genres(loved_docs)[:6]]
    top_disliked = [g for g,_ in extract_genres(disliked_docs)[:6]]
    top_recent = [g for g,_ in extract_genres(recent_docs)[:6]]

    text = "\n".join([
        "USER_TASTE_SUMMARY",
        f"Favorite genres (loved): {', '.join(top_loved) if top_loved else '(unknown'}",
        f"Avoid genres (disliked): {', '.join(top_disliked) if top_disliked else '(unknown'}",
        f"Recent mood genres: {', '.join(top_recent) if top_recent else '(unknown'}",

    ])

    return {
        "id": "taste:summary",
        "type": "summary",
        "text": text,
        "generated_at": timezone.now().isoformat(),
    }

class Command(BaseCommand):
    help = "Build a capped taste JSONL file for a user."

    def add_arguments(self,parser):
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--out", type=str, default="taste_out")

    def handle(self, *args, **opts):
        user_id = opts["user_id"]
        out_dir = Path(opts["out"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"taste_user_{user_id}.jsonl"

        base = MovieUser.objects.filter(user_id=user_id).select_related("movie")

        loved = base.filter(rating__gte=LOVED_MIN).order_by("-rating", "-watched_date")[:CAP_LOVED]
        disliked = base.filter(rating__lte=DISLIKED_MAX).order_by("-rating", "-watched_date")[:CAP_DISLIKED]
        recent = base.filter(watched_date__isnull=False).order_by("-watched_date")[:CAP_RECENT]

        loved_docs = [mu_to_doc(mu, "loved") for mu in loved]
        disliked_docs = [mu_to_doc(mu, "disliked") for mu in disliked]
        recent_docs = [mu_to_doc(mu, "recent") for mu in recent]

        summary_doc = build_summary(loved_docs, disliked_docs, recent_docs)

        with out_path.open("w", encoding="utf-8") as f:
            for d in loved_docs + disliked_docs + recent_docs:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
            f.write(json.dumps(summary_doc, ensure_ascii=False) + "\n")

        self.stdout.write(self.style.SUCCESS(f"Wrote {out_path}"))
        self.stdout.write(self.style.SUCCESS(
            f"Counts: loved={len(loved_docs)} disliked={len(disliked_docs)} recent={len(recent_docs)}"
            ))
