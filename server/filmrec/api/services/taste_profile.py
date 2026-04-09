# api/services/taste_profile.py
from __future__ import annotations

from collections import Counter
from typing import Iterable

from django.utils import timezone

from api.models import MovieUser

# ---------------------------------------------------------------------------
# Baseline taste rules
# ---------------------------------------------------------------------------

LOVED_MIN = 4.0
DISLIKED_MAX = 2.5

CAP_LOVED = 100
CAP_DISLIKED = 60
CAP_RECENT = 20

QUERY_HEADROOM = 50


def load_taste_movieusers(user_id: int):
    base = (
        MovieUser.objects
        .filter(user_id=user_id, rating__isnull=False)
        .select_related("movie")
        .prefetch_related(
            "movie__moviegenre_set__genre",
            "movie__moviecrew_set__person",
            "movie__moviecast_set__person",
        )
    )

    loved = list(
        base.filter(rating__gte=LOVED_MIN)
        .order_by("-rating", "-watched_date")[:CAP_LOVED]
    )

    disliked = list(
        base.filter(rating__lte=DISLIKED_MAX)
        .order_by("rating", "-watched_date")[:CAP_DISLIKED]
    )

    excluded_ids = {mu.movie_id for mu in loved} | {mu.movie_id for mu in disliked}

    recent = list(
        base.exclude(movie_id__in=excluded_ids)
        .filter(watched_date__isnull=False)
        .order_by("-watched_date")[:CAP_RECENT]
    )

    return loved, disliked, recent

def split_movieusers(
    all_rated: list[MovieUser],
) -> tuple[list[MovieUser], list[MovieUser], list[MovieUser]]:
    """
    Split MovieUser rows into loved / disliked / recent buckets.
    """
    loved_mus = [mu for mu in all_rated if mu.rating is not None and mu.rating >= LOVED_MIN][:CAP_LOVED]
    disliked_mus = [mu for mu in all_rated if mu.rating is not None and mu.rating <= DISLIKED_MAX][:CAP_DISLIKED]
    
    loved_ids = {mu.movie_id for mu in loved_mus}
    disliked_ids = {mu.movie_id for mu in disliked_mus}
    excluded = loved_ids | disliked_ids

    recent_mus = sorted(
        [mu for mu in all_rated if mu.watched_date and mu.movie_id not in excluded],
        key=lambda mu: mu.watched_date,
        reverse=True,
    )[:CAP_RECENT]

    return loved_mus, disliked_mus, recent_mus


def mu_to_doc(mu: MovieUser, doc_type: str) -> dict:
    mv = mu.movie
    title = mv.title or "Unknown"
    year = getattr(mv, "year", None)
    year_str = f" ({year})" if year else ""
    rating = getattr(mu, "rating", None)

    genres = [mg.genre.name for mg in mv.moviegenre_set.all() if mg.genre_id]

    directors = [
        mc.person.name
        for mc in mv.moviecrew_set.all()
        if mc.job == "Director" and mc.person_id
    ]

    actors = [
        mc.person.name
        for mc in sorted(
            mv.moviecast_set.all(),
            key=lambda x: x.order if x.order is not None else 999999,
        )[:3]
        if mc.person_id
    ]

    text_lines = [
        "USER_TASTE_EVIDENCE",
        f"Type: {doc_type}",
        f"Movie: {title}{year_str}",
        f"Rating: {rating}" if rating is not None else "Rating: (unknown)",
        f"Genres: {', '.join(genres)}" if genres else "Genres: (unknown)",
    ]

    if directors:
        text_lines.append(f"Director: {', '.join(directors)}")
    if actors:
        text_lines.append(f"Actors: {', '.join(actors)}")

    if getattr(mu, "review", None):
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


def movieusers_to_docs(movieusers: Iterable[MovieUser], doc_type: str) -> list[dict]:
    return [mu_to_doc(mu, doc_type) for mu in movieusers]


def _top_items(docs: list[dict], field: str, k: int) -> list[str]:
    counter = Counter()
    for doc in docs:
        for item in (doc.get(field) or []):
            if item:
                counter[item] += 1
    return [item for item, _ in counter.most_common(k)]


def build_summary(loved_docs: list[dict], disliked_docs: list[dict], recent_docs: list[dict]) -> dict:
    top_loved_genres = _top_items(loved_docs, "genres", k=6)
    top_disliked_genres = _top_items(disliked_docs, "genres", k=4)
    top_recent_genres = _top_items(recent_docs, "genres", k=4)

    top_loved_directors = _top_items(loved_docs, "directors", k=5)
    top_loved_actors = _top_items(loved_docs, "actors", k=5)

    avg_loved_rating = (
        sum(d.get("rating", 0) for d in loved_docs if d.get("rating") is not None) / len(loved_docs)
        if loved_docs else 0
    )

    avg_disliked_rating = (
        sum(d.get("rating", 0) for d in disliked_docs if d.get("rating") is not None) / len(disliked_docs)
        if disliked_docs else 0
    )

    text = "\n".join([
        "USER_TASTE_SUMMARY",
        f"Total loved movies: {len(loved_docs)}",
        f"Total disliked movies: {len(disliked_docs)}",
        f"Recent activity: {len(recent_docs)}",
        "",
        f"Average rating (loved): {avg_loved_rating:.2f}",
        f"Average rating (disliked): {avg_disliked_rating:.2f}",
        "",
        f"Favorite genres: {', '.join(top_loved_genres) if top_loved_genres else '(unknown)'}",
        f"Avoid genres: {', '.join(top_disliked_genres) if top_disliked_genres else '(unknown)'}",
        f"Recent mood genres: {', '.join(top_recent_genres) if top_recent_genres else '(unknown)'}",
        "",
        f"Favorite directors: {', '.join(top_loved_directors) if top_loved_directors else '(unknown)'}",
        f"Favorite actors: {', '.join(top_loved_actors) if top_loved_actors else '(unknown)'}",
    ])

    return {
        "id": "taste:summary",
        "type": "summary",
        "stats": {
            "total_loved": len(loved_docs),
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


def build_initial_taste_artifacts(user_id: int) -> dict:
    """
    Main baseline taste-profile service.
    """
    loved_mus, disliked_mus, recent_mus = load_taste_movieusers(user_id=user_id)

    if not loved_mus and not disliked_mus and not recent_mus:
        return {
            "summary_doc": None,
            "loved_docs": [],
            "disliked_docs": [],
            "recent_docs": [],
            "counts": {
                "total_source_rows": 0,
                "loved": 0,
                "disliked": 0,
                "recent": 0,
            },
        }

    loved_docs = movieusers_to_docs(loved_mus, "loved")
    disliked_docs = movieusers_to_docs(disliked_mus, "disliked")
    recent_docs = movieusers_to_docs(recent_mus, "recent")

    summary_doc = build_summary(loved_docs, disliked_docs, recent_docs)

    return {
        "summary_doc": summary_doc,
        "loved_docs": loved_docs,
        "disliked_docs": disliked_docs,
        "recent_docs": recent_docs,
        "counts": {
            "total_source_rows": len(loved_mus) + len(disliked_mus) + len(recent_mus),
            "loved": len(loved_docs),
            "disliked": len(disliked_docs),
            "recent": len(recent_docs),
        },
    }