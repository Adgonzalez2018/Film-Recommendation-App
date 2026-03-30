import json
from pathlib import Path
from collections import Counter

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
    genres = list(
        mv.moviegenre_set
        .select_related("genre")
        .values_list("genre__name", flat=True)
    )

    # directors
    directors = list(
        mv.director.name if hasattr(mv, 'director') and mv.director else []
    )

    # actors - top 3
    actors = list(
        mv.actors.order_by('movieactor__cast_order')[:3]
        .values_list('name', flat=True)
    ) if hasattr(mv, 'actors') else []

    text_lines = [
        "USER_TASTE_EVIDENCE",
        f"Type: {doc_type}",
        f"Movie: {title}{year_str}",
        f"Rating: {rating}" if rating is not None else "Rating: (unknown)",
        f"Genres: {', '.join(genres)}" if genres else "Genres: (unknown)",
    ]

    if directors:
        text_lines.append(f"Director: {','.join(directors)}")
    if actors:
        text_lines.append(f"Actor: {','.join(actors)}")

    # add review text if exists
    if hasattr(mu, 'review') and mu.review:
        # truncate long reviews
        review_text = mu.review[:200] + "..." if len(mu.review) > 200 else mu.review 
        text_lines.append(f"Review: {review_text}")
    
    text = "\n".join(text_lines)

    return {
        "id": f"taste:{doc_type}:movieuser:{mu.id}",
        "type": doc_type,
        "movie_id": mv.id,
        "tmdb_id": getattr(mv, "tmdb_id", None),
        "rating": rating,
        "watched_date": mu.watched_date.isoformat() if mu.watched_date else None,
        "genres": genres,
        "directors": directors,
        "actors": actors,
        "title": title,
        "year": year,
        "text": text,
    }

def build_summary(loved_docs, disliked_docs, recent_docs) -> dict:
    #v1 deterministic: just list top genres by freq if present in text
    # Later we should compute from real relations, directors, keywords
    def top_items(docs, field, k=6):
        c = Counter()
        for d in docs:
            for item in (d.get(field) or []):
                if item:
                    c[item] += 1
        return [item for item, _ in c.most_common(k)]
        
    # calc multiple dims
    top_loved_genres = top_items(loved_docs, "genres", k=6)
    top_disliked_genres = top_items(disliked_docs, "genres", k=4)
    top_recent_genres = top_items(recent_docs, "genres", k=4)

    top_loved_directors = top_items(loved_docs, "directors", k=5)
    top_loved_actors = top_items(loved_docs, "actors", k = 5)

    avg_loved_rating = (
        sum(d.get("rating",0) for d in loved_docs if d.get("rating")) / len(loved_docs)
        if loved_docs else 0
    )

    avg_disliked_rating = (
        sum(d.get("rating",0) for d in disliked_docs if d.get("rating")) / len(disliked_docs)
        if disliked_docs else 0
    )

    text = "\n".join([
        "USER_TASTE_SUMMARY",
        f"Total loved movies: {len(loved_docs)}",
        f"Total disliked movies: {len(disliked_docs)}",
        f"Recent Activity: {len(recent_docs)}",
        "",
        f"Average Rating (loved): {avg_loved_rating:.2f}",
        f"Average Rating (disliked): {avg_disliked_rating:.2f}",
        "",
        f"Favorite genres: {','.join(top_loved_genres) if top_loved_genres else '(unknown)'}",
        f"Avoid genres: {','.join(top_disliked_genres) if top_disliked_genres else '(unknown)'}",
        f"Recent mood genres: {','.join(top_recent_genres) if top_recent_genres else '(unknown)'}",
        '',
        f"Favorite Directors: {','.join(top_loved_directors) if top_loved_directors else '(unknown)'}",
        f"Favorite Actors: {','.join(top_loved_actors) if top_loved_actors else '(unknown)'}",
    ])

    return {
        "id": "taste:summary",
        "type": "summary",
        "stats":{
            "total loved": len(loved_docs),
            "total_disliked": len(disliked_docs),
            "total_recent": len(recent_docs),
            "avg_loved_rating": round(avg_loved_rating, 2),
            "avg_disliked_rating": round(avg_disliked_rating, 2),
        },
        "top_genres_loved": top_loved_genres,
        "top_genres_disliked": top_disliked_genres,
        "top_genres_recent": top_recent_genres,
        "top_directors_loved": top_loved_directors,
        "top_actors_loved": top_loved_actors,
        "text": text,
        "generated_at": timezone.now().isoformat(),
    }

class Command(BaseCommand):
    help = "Build a capped taste TXT file for a user."

    def add_arguments(self,parser):
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument("--out", type=str, default="taste_out")

    def handle(self, *args, **opts):
        user_id = opts["user_id"]
        out_dir = Path(opts["out"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"taste_user_{user_id}.txt"

        try:
            base = (
                MovieUser.objects
                .filter(user_id=user_id)
                .select_related("movie")
                .prefetch_related(
                    "movie__moviegenre_set__genre",
                    "movie__director",
                    "movie__actors",
                )
                )

            if not base.exists():
                self.stdout.write(
                    self.style.WARNING(f"User {user_id} has no rated movies.")
                )
                return
            
            loved = base.filter(rating__gte=LOVED_MIN).order_by("-rating", "-watched_date")[:CAP_LOVED]
            disliked = base.filter(rating__lte=DISLIKED_MAX).order_by("-rating", "-watched_date")[:CAP_DISLIKED]
            recent = base.filter(watched_date__isnull=False).order_by("-watched_date")[:CAP_RECENT]

            loved_docs = [mu_to_doc(mu, "loved") for mu in loved]
            disliked_docs = [mu_to_doc(mu, "disliked") for mu in disliked]
            recent_docs = [mu_to_doc(mu, "recent") for mu in recent]

            summary_doc = build_summary(loved_docs, disliked_docs, recent_docs)

            with out_path.open("w", encoding="utf-8") as f:
                f.write(json.dumps(summary_doc, ensure_ascii=False) + "\n")
                for d in loved_docs + disliked_docs + recent_docs:
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")

            self.stdout.write(self.style.SUCCESS(f"Wrote {out_path}"))
            self.stdout.write(self.style.SUCCESS(
                f"Counts: loved={len(loved_docs)} disliked={len(disliked_docs)} recent={len(recent_docs)}"
                ))
            self.stdout.write(self.style.SUCCESS(f"File size: {out_path.stat().st_size / 1024:.1f} KB"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
            raise