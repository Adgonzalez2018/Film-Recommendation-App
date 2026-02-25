import re
from functools import lru_cache

from django.db.models import Q

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import (
    Movie,
    FilmBank,
    Genre,
    Person,
)
from ..services.tmdb import search_movie, tmdb_get, upsert_tmdb_movie  # <-- uses your existing file
from ..serializer import ChatRequestSerializer  # must exist

@lru_cache(maxsize=1)
def _genre_vocab():
    # normalized set of genre names in DB
    return set(
        Genre.objects.values_list("name", flat=True)
    )


def _clarify(msg: str) -> str | None:
    m = (msg or "").strip()
    if len(m) < 4:
        return "What are you in the mood for — a genre, an actor/director, or a movie you liked?"
    if re.fullmatch(r"(?i)\s*like\s*\??\s*", m):
        return "What movie do you want it to feel like? Give me one title."
    return None


def _parse_intent(msg: str) -> dict:
    text = (msg or "").strip()
    m = text.lower()

    want_terrible = any(k in m for k in ["terrible", "bad", "worst", "so bad"])
    vocab = {g.lower(): g for g in _genre_vocab()}
    genre = next((g for g in vocab if re.search(rf"\b{re.escape(g)}\b", m)), None)

    # like <title>
    like_title = None
    match_like = re.search(r"\blike\s+(.+)$", text, re.IGNORECASE)
    if match_like:
        like_title = match_like.group(1).strip()

    # actor: "with Tom Cruise" / "starring Tom Cruise"
    actor = None
    match_actor = re.search(r"(with|starring)\s+([a-z]+(?:\s+[a-z]+){0,2})", m)
    if match_actor:
        actor = match_actor.group(2).strip()

    # director: "directed by Christopher Nolan"
    director = None
    match_dir = re.search(r"(directed by|director)\s+([a-z]+(?:\s+[a-z]+){0,2})", m)
    if match_dir:
        director = match_dir.group(2).strip()

    return {
        "want_terrible": want_terrible,
        "genre": genre,
        "actor": actor,
        "director": director,
        "like_title": like_title,
    }


def _exclude_already_recommended(user):
    return set(FilmBank.objects.filter(user=user).values_list("movie_id", flat=True))


def _seed_from_like_title(title: str, limit: int = 18) -> list[Movie]:
    """
    1) TMDB search for the title
    2) upsert the seed movie
    3) hit TMDB recommendations
    4) upsert recommended movies
    returns list of Movie objects that were seeded
    """
    results = (search_movie(title) or {}).get("results", [])
    if not results:
        return []

    seed_tmdb_id = results[0]["id"]
    upsert_tmdb_movie(seed_tmdb_id)

    rec = tmdb_get(f"/movie/{seed_tmdb_id}/recommendations")
    rec_results = (rec or {}).get("results", [])[:limit]

    seeded = []
    for r in rec_results:
        try:
            seeded.append(upsert_tmdb_movie(r["id"]))
        except Exception:
            # don't fail the whole request on one bad movie
            continue

    return seeded


def _pick_movies(user, qs, n=3) -> list[Movie]:
    """
    Picks top N by avg_rating (fallback to id desc if rating missing).
    Excludes already recommended.
    """
    excluded = _exclude_already_recommended(user)
    qs = qs.exclude(id__in=excluded)

    # prioritize rated movies if present
    qs = qs.order_by("-avg_rating", "-id")
    return list(qs[:n])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_recommend(request):
    ser = ChatRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    msg = ser.validated_data["message"]

    clarify = _clarify(msg)
    if clarify:
        return Response({"type": "clarify", "assistant": clarify}, status=status.HTTP_200_OK)

    user = request.user
    intent = _parse_intent(msg)

    # --- base pool: everything in our Movie table ---
    pool = Movie.objects.all()

    # --- intent filters (DB-based) ---
    if intent["genre"]:
        pool = pool.filter(moviegenre__genre__name__iexact=intent["genre"]).distinct()

    if intent["actor"]:
        pool = pool.filter(moviecast__person__name__icontains=intent["actor"]).distinct()

    if intent["director"]:
        pool = pool.filter(moviecrew__job="Director", moviecrew__person__name__icontains=intent["director"]).distinct()

    # --- if "like X", seed from TMDB recommendations first ---
    if intent["like_title"]:
        seeded = _seed_from_like_title(intent["like_title"])
        if not seeded:
            return Response(
                {"type": "clarify", "assistant": "I couldn’t find that title on TMDB. Try another movie title."},
                status=status.HTTP_200_OK,
            )
        # narrow pool to seeded IDs to keep results relevant
        seeded_ids = [m.id for m in seeded]
        pool = Movie.objects.filter(id__in=seeded_ids)

    # --- terrible request (lowest rated) ---
    if intent["want_terrible"]:
        picks = _pick_movies(user, pool.order_by("avg_rating", "id"), n=3)
        assistant = "Alright… you asked for terrible. Here are a few that might be spectacularly bad."
        reason = "Picked lowest-rated options from available pool (after intent filters)."
    else:
        picks = _pick_movies(user, pool, n=3)
        if not picks:
            # fallback: if pool empty, just pick from all movies (excluding recommended)
            picks = _pick_movies(user, Movie.objects.all(), n=3)

        assistant = "Here are a few picks based on what you asked for:"
        reason = f"Intent={intent}. Filtered in DB; ranked by avg_rating."

    if not picks:
        return Response(
            {"type": "clarify", "assistant": "I don’t have enough movies indexed yet. Try a 'like <movie>' request to seed recommendations."},
            status=status.HTTP_200_OK,
        )

    # --- save to FilmBank + build response cards ---
    movies_payload = []
    for mv in picks:
        FilmBank.objects.get_or_create(
            user=user,
            movie=mv,
            defaults={"query_text": msg, "reason": reason},
        )
        movies_payload.append(
            {
                "id": mv.id,
                "title": mv.title,
                "tmdb_id": mv.tmdb_id,
                "poster_url": mv.poster_url,
                "description": mv.description,
                "avg_rating": mv.avg_rating,
                "year": mv.year,
            }
        )

    return Response(
        {"type": "recommendations", "assistant": assistant, "movies": movies_payload},
        status=status.HTTP_200_OK,
    )