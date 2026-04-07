#api/services/feedback_profile.py
from __future__ import annotations
from collections import Counter, defaultdict
from typing import Iterable

from django.utils import timezone

from api.models import FilmBank

# ---------------------------------------------------------------------------
# Feedback weighting rules
# ---------------------------------------------------------------------------
GOOD_WEIGHT = 2.0
NEUTRAL_WEIGHT = .35
BAD_WEIGHT = -2.0

WATCHED_BONUS_MULTIPLIER = 1.25
TEXT_BONUS_MULTIPLIER = 1.10

CAP_FEEDBACK_ROWS = 200

# ---------------------------------------------------------------------------
# Feedback weighting rules
# ---------------------------------------------------------------------------

def load_feedback_rows(user_id: int) -> list[FilmBank]:
    # Load recent FilmBank rows that have actual submitted feedback.
    return list(
        FilmBank.objects
        .filter(
            user_id=user_id,
            feedback_submitted_at__isnull=False,
            feedback_rating__isnull=False,
        )
        .select_related("movie")
        .prefetch_related(
            "movie__moviegenre_set__genre",
            "movie__moviecrew_set__person",
            "movie_moviecast_person__person",
        )
        .order_by("-feedback_submitted_at")[:CAP_FEEDBACK_ROWS]
    )

# ---------------------------------------------------------------------------
# Row scoring
# ---------------------------------------------------------------------------

def feedback_weight(fb: FilmBank) -> float:
    """
    Convert a FilmBank feedback row into one scalar weight.
    Positive means reinforcement.
    Negative means avoid / correction
    """
    rating = fb.feedback_rating
    watched = fb.feedback_watched
    text = (fb.feedback_text or "").strip()

    if rating == "good":
        weight = GOOD_WEIGHT
    elif rating == "neutral":
        weight = NEUTRAL_WEIGHT
    elif rating == "bad":
        weight = BAD_WEIGHT
    else:
        weight = 0.0

    if watched is True:
        weight *= WATCHED_BONUS_MULTIPLIER
    
    if text:
        weight *= TEXT_BONUS_MULTIPLIER

    return round(weight, 4)

# api/services/feedback_profile.py
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from django.utils import timezone

from api.models import FilmBank


# ---------------------------------------------------------------------------
# Feedback weighting rules
# ---------------------------------------------------------------------------

GOOD_WEIGHT = 2.0
NEUTRAL_WEIGHT = 0.35
BAD_WEIGHT = -2.0

WATCHED_BONUS_MULTIPLIER = 1.25
TEXT_BONUS_MULTIPLIER = 1.10

CAP_FEEDBACK_ROWS = 200


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def load_feedback_rows(user_id: int) -> list[FilmBank]:
    """
    Load recent FilmBank rows that have actual submitted feedback.
    """
    return list(
        FilmBank.objects
        .filter(
            user_id=user_id,
            feedback_submitted_at__isnull=False,
            feedback_rating__isnull=False,
        )
        .select_related("movie")
        .prefetch_related(
            "movie__moviegenre_set__genre",
            "movie__moviecrew_set__person",
            "movie__moviecast_set__person",
        )
        .order_by("-feedback_submitted_at")[:CAP_FEEDBACK_ROWS]
    )


# ---------------------------------------------------------------------------
# Row scoring
# ---------------------------------------------------------------------------

def feedback_weight(fb: FilmBank) -> float:
    """
    Convert a FilmBank feedback row into one scalar weight.
    Positive means reinforcement.
    Negative means avoid / correction.
    """
    rating = fb.feedback_rating
    watched = fb.feedback_watched
    text = (fb.feedback_text or "").strip()

    if rating == "good":
        weight = GOOD_WEIGHT
    elif rating == "neutral":
        weight = NEUTRAL_WEIGHT
    elif rating == "bad":
        weight = BAD_WEIGHT
    else:
        weight = 0.0

    if watched is True:
        weight *= WATCHED_BONUS_MULTIPLIER

    if text:
        weight *= TEXT_BONUS_MULTIPLIER

    return round(weight, 4)


# ---------------------------------------------------------------------------
# Feature extractors
# ---------------------------------------------------------------------------

def fb_to_doc(fb: FilmBank) -> dict:
    mv = fb.movie
    title = mv.title or "Unknown"
    year = getattr(mv, "year", None)
    year_str = f" ({year})" if year else ""
    weight = feedback_weight(fb)
    genres = [mg.genre.name for mg in mv.moviegenre_set.all() if mg.genre_id]

    directors = [
        mc.person.name
        for mc in mv.moviecrew_set.all()
        if mc.job == "Director" and mc.person_id
    ]

    actors = [
        mc.person.name
        for mc in sorted(
            mv.moveiecast_set.all(),
            key=lambda x: x.order if x.order is not None else 999999,
        )[:3]
        if mc.person_id
    ]

    text_lines = [
        "USER_RECOMMENDATION_FEEDBACK",
        f"Movie: {title}{year_str}",
        f"Recommendation rating: {fb.feedback_rating or 'unknown'}",
        f"Watched: {fb.feedback_watched}",
        f"Genres: {', '.join(genres)} if genres else Genres: (unknown)",
    ]

    if directors:
        text_lines.append(f"Director: {', '.join(directors)}")
    if actors:
        text_lines.append(f"Actors: {', '.join(directors)}")
    if fb.reason:
        text_lines.append(f"Recommendation reason: {fb.reason}")
    if fb.feedback_text:
        text_lines.append(f"Feedback weight: {weight:.2f}")

    return {
        "id": f"taste:feedback:filmbank:{fb.id}",
        "type": "feedback",
        "movie_id": mv.id,
        "movie_id": getattr(mv, "tmdb_id", None),
        "title": title,
        "year": year,
        "genres": genres,
        "directors": directors,
        "actors": actors,
        "feedback_rating": fb.feedback_rating,
        "feedback_watched": fb.feedback_watched,
        "feedback_text": fb.feedback_text,
        "feedback_weight": weight,
        "submitted_at": fb.feedback_submitted_at.isoformat() if fb.feedback_submitted_at else None,
        "text": "\n".join(text_lines),
    }

def feedback_rows_to_docs(rows: Iterable[FilmBank]) -> list[dict]:
    return [fb_to_doc(row) for row in rows]

# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _score_items(docs: list[dict], field: str) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)

    for doc in docs:
        weight = float(doc.get("feedback_weight") or 0.0)
        for item in (doc.get(field) or []):
            if item:
                scores[item] += weight

    return dict(scores)

def _top_positive(score_map: dict[str, float], k: int) -> list[str]:
    return [
        key for key, value in
        sorted(score_map.items(), key=lambda x: (-x[1], x[0]))
        if value > 0
    ][:k]

def _top_negative(score_map: dict[str, float], k: int) -> list[str]:
    return [
        key for key, value in
        sorted(score_map.items(), key=lambda x: (x[1], x[0]))
        if value < 0
    ]

def build_feedback_summary(feedback_docs: list[dict]) -> dict:
    genre_scores = _score_items(feedback_docs, "genres")
    director_scores = _score_items(feedback_docs, "directors")
    actor_scores = _score_items(feedback_docs, "actors")

    positive_genres = _top_positive(genre_scores, k=6)
    negative_genres = _top_negative(genre_scores, k=4)

    positive_directors = _top_positive(director_scores, k=5)
    negative_directors = _top_negative(director_scores, k=3)

    positive_actors = _top_positive(actor_scores, k=5)
    negative_actors = _top_negative(actor_scores, k=3)

    rating_counter = Counter(doc.get("feedback_rating") for doc in feedback_docs if doc.get("feedback_rating"))
    watched_yes = sum(1 for doc in feedback_docs if doc.get("feedback_watched") is True)
    watched_no = sum(1 for doc in feedback_docs if doc.get("feedback_watched") is False)

    notable_text = [
        doc.get("feedback_text", "").strip()
        for doc in feedback_docs
        if doc.get("feedback_text","").strip()
    ][:10]

    text = "\n".join([
        "USER_FEEDBACK_SUMMARY",
        f"Total feedback rows: {len(feedback_docs)}",
        f"Good feedback count: {rating_counter.get('good', 0)}",
        f"Neutral feedback count: {rating_counter.get('neutral', 0)}",
        f"Bad feedback count: {rating_counter.get('bad', 0)}",
        f"Watched after recommendation: {watched_yes}",
        f"Did not watch after recommendation: {watched_no}",
        "",
        f"Positive feedback genres: {', '.join(positive_genres) if positive_genres else '(none)'}",
        f"Negative feedback genres: {', '.join(negative_genres) if negative_genres else '(none)'}",
        f"Positive feedback directors: {', '.join(positive_directors) if positive_directors else '(none)'}",
        f"Negative feedback directors: {', '.join(negative_directors) if negative_directors else '(none)'}",
        f"Positive feedback actors: {', '.join(positive_actors) if positive_actors else '(none)'}",
        f"Negative feedback actors: {', '.join(negative_actors) if negative_actors else '(none)'}",
    ])

    return {
        "id": "taste:feedback:summary",
        "type": "feedback_summary",
        "stats": {
            "total_feedback": len(feedback_docs),
            "good_count": rating_counter.get("good", 0),
            "neutral_count": rating_counter.get("neutral", 0),
            "bad_count": rating_counter.get("bad", 0),
            "watched_yes": watched_yes,
            "watched_no": watched_no,
        },
        "genre_scores": genre_scores,
        "director_scores": director_scores,
        "actor_scores": actor_scores,
        "positive_genres": positive_genres,
        "negative_genres": negative_genres,
        "positive_directors": positive_directors,
        "negative_directors": negative_directors,
        "positive_actors": positive_actors,
        "negative_actors": negative_actors,
        "notable_feedback_text": notable_text,
        "text": text,
        "generated_at": timezone.now().isoformat(),
    }

# ---------------------------------------------------------------------------
# Public service entry point
# ---------------------------------------------------------------------------

def build_feedback_taste_artifacts(user_id: int) -> dict:
    rows = load_feedback_rows(user_id=user_id)
    if not rows:
        return {
            "summary_doc": None,
            "feedback_docs": [],
            "counts": {
                "total_feedback_rows": 0,
            },
        }
    
    feedback_docs = feedback_rows_to_docs(rows)
    summary_doc = build_feedback_summary(feedback_docs)

    return {
        "summary_doc": summary_doc,
        "feedback_docs": feedback_docs,
        "counts": {
            "total_feedback_rows": len(feedback_docs),
        },
    }