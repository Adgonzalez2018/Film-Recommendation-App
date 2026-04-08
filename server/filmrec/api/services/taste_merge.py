#api/services/taste_merge.py
from __future__ import annotations
from collections import defaultdict
from django.utils import timezone

# ---------------------------------------------------------------------------
# Merge weights
# ---------------------------------------------------------------------------

BASELINE_WEIGHT = 1.0
FEEDBACK_WEIGHT = 0.35

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _weighted_list_to_score_map(items: list[str], weight: float) -> dict[str, float]:
    """
    Turn an ordered preference list into a simple descending score map.
    Earlier items get slightly higher weight.
    """
    out: dict[str, float] = {}
    for idx, item in enumerate(items or []):
        if not item:
            continue
        factor = max(weight * (1.0 - idx * .08), 0.05)
        score = weight * factor
        out[item] = round(score, 4)
    return out

def _merge_score_maps(
        base_map: dict[str, float] | None,
        feedback_map: dict[str, float] | None,
        feedback_scale: float = FEEDBACK_WEIGHT,
) -> dict[str, float]:
    merged: dict[str, float] = defaultdict(float)

    for key, value in (base_map or {}).items():
        merged[key] += float(value)

    for key, value in (feedback_map or {}).items():
        merged[key] += float(value) * feedback_scale

    return dict(merged)

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
    ][:k]

# ---------------------------------------------------------------------------
# Normalize baseline summary into score maps
# ---------------------------------------------------------------------------

def baseline_summary_to_score_maps(summary_doc: dict | None) -> dict:
    if not summary_doc:
        return {
            "genre_scores": {},
            "director_scores": {},
            "actor_scores": {},
        }

    loved_genres = summary_doc.get("top_genres_loved", []) or []
    disliked_genres = summary_doc.get("top_genres_disliked", []) or []
    recent_genres = summary_doc.get("top_genres_recent", []) or []
    loved_directors = summary_doc.get("top_directors_loved", []) or []
    loved_actors = summary_doc.get("top_actors_loved", []) or []

    genre_scores = _weighted_list_to_score_map(loved_genres, BASELINE_WEIGHT)
    recent_boost = _weighted_list_to_score_map(recent_genres, BASELINE_WEIGHT * 0.45)
    avoid_penalty = _weighted_list_to_score_map(disliked_genres, -BASELINE_WEIGHT * 0.9)

    for key, value in recent_boost.items():
        genre_scores[key] = genre_scores.get(key, 0.0) + value

    for key, value in avoid_penalty.items():
        genre_scores[key] = genre_scores.get(key, 0.0) + value

    director_scores = _weighted_list_to_score_map(loved_directors, BASELINE_WEIGHT * 1.1)
    actor_scores = _weighted_list_to_score_map(loved_actors, BASELINE_WEIGHT * 0.8)

    return {
        "genre_scores": genre_scores,
        "director_scores": director_scores,
        "actor_scores": actor_scores,
    }

# ---------------------------------------------------------------------------
# Merge summaries
# ---------------------------------------------------------------------------

def build_merged_taste_summary(
        *,
        baseline_summary_doc: dict | None,
        feedback_summary_doc: dict | None,
) -> dict:
    base_maps = baseline_summary_to_score_maps(baseline_summary_doc)

    feedback_genre_scores = (feedback_summary_doc or {}).get("genre_scores", {}) or {}
    feedback_director_scores = (feedback_summary_doc or {}).get("director_scores", {}) or {}
    feedback_actor_scores = (feedback_summary_doc or {}).get("actor_scores", {}) or {}

    merged_genre_scores = _merge_score_maps(
        base_maps["genre_scores"],
        feedback_genre_scores,
    )
    merged_director_scores = _merge_score_maps(
        base_maps["director_scores"],
        feedback_director_scores,
    )
    merged_actor_scores = _merge_score_maps(
        base_maps["actor_scores"],
        feedback_actor_scores,
    )

    favorite_genres = _top_positive(merged_genre_scores, k=6)
    avoid_genres = _top_negative(merged_genre_scores, k=4)

    favorite_directors = _top_positive(merged_director_scores, k=5)
    avoid_directors = _top_negative(merged_director_scores, k=3)

    favorite_actors = _top_positive(merged_actor_scores, k=5)
    avoid_actors = _top_negative(merged_actor_scores, k=3)

    feedback_text_notes = (feedback_summary_doc or {}).get("notable_feedback_text", []) or []

    baseline_stats = (baseline_summary_doc or {}).get("stats", {})
    feedback_stats = (feedback_summary_doc or {}).get("stats", {})

    text_lines = [
        "USER_MERGED_TASTE_SUMMARY",
        f"Baseline loved movies: {baseline_stats.get('total_loved', 0)}",
        f"Baseline disliked movies: {baseline_stats.get('total_disliked', 0)}",
        f"Recent baseline activity: {baseline_stats.get('total_recent', 0)}",
        f"Feedback rows used: {feedback_stats.get('total_feedback', 0)}",
        "",
        f"Favorite genres: {', '.join(favorite_genres) if favorite_genres else '(unknown)'}",
        f"Avoid genres: {', '.join(avoid_genres) if avoid_genres else '(unknown)'}",
        f"Favorite directors: {', '.join(favorite_directors) if favorite_directors else '(unknown)'}",
        f"Avoid directors: {', '.join(avoid_directors) if avoid_directors else '(none)'}",
        f"Favorite actors: {', '.join(favorite_actors) if favorite_actors else '(unknown)'}",
        f"Avoid actors: {', '.join(avoid_actors) if avoid_actors else '(none)'}",
    ]

    if feedback_text_notes:
        text_lines.append("")
        text_lines.append("User recommendation feedback notes:")
        for note in feedback_text_notes[:8]:
            text_lines.append(f"- {note}")
    
    return {
        "id": "taste:merged:summary",
        "type": "merged_summary",
        "baseline_summary_id": (baseline_summary_doc or {}).get("id"),
        "feedback_summary_id": (feedback_summary_doc or {}).get("id"),
        "stats": {
            "total_loved": baseline_stats.get("total_loved", 0),
            "total_disliked": baseline_stats.get("total_disliked", 0),
            "total_recent": baseline_stats.get("total_recent", 0),
            "total_feedback": feedback_stats.get("total_feedback", 0),
        },
        "genre_scores": merged_genre_scores,
        "director_scores": merged_director_scores,
        "actor_scores": merged_actor_scores,
        "favorite_genres": favorite_genres,
        "avoid_genres": avoid_genres,
        "favorite_directors": favorite_directors,
        "avoid_directors": avoid_directors,
        "favorite_actors": favorite_actors,
        "avoid_actors": avoid_actors,
        "feedback_text_notes": feedback_text_notes,
        "text": "\n".join(text_lines),
        "generated_at": timezone.now().isoformat(),
    }

def merge_taste_artifacts(
        *,
        baseline_artifacts: dict,
        feedback_artifacts: dict | None = None,
) -> dict:
    # Merge baseline + feedback into one final artifact bundle
    baseline_summary_doc = baseline_artifacts.get("summary_doc")
    feedback_summary_doc = (feedback_artifacts or {}).get("summary_doc")

    merged_summary_doc = build_merged_taste_summary(
        baseline_summary_doc=baseline_summary_doc,
        feedback_summary_doc=feedback_summary_doc,
    )

    merged_docs = []
    merged_docs.extend(baseline_artifacts.get("loved_docs", []))
    merged_docs.extend(baseline_artifacts.get("disliked_docs", []))
    merged_docs.extend(baseline_artifacts.get("recent_docs", []))
    merged_docs.extend((feedback_artifacts or {}).get("feedback_docs", []))

    return {
        "summary_doc": merged_summary_doc,
        "merged_docs": merged_docs,
        "baseline_summary_doc": baseline_summary_doc,
        "feedback_summary_doc": feedback_summary_doc,
    }