"""
Endpoints for Chat.js
RAG-based recommender using OpenAI API + File search
"""
import os
import json

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from openai import OpenAI

from ..models import (
    FilmBank,
    MovieUser,
)
from ..services.tmdb import upsert_tmdb_movie  # <-- uses your existing file
from ..serializer import ChatRequestSerializer  # must exist


def _get_excluded_tmdb_ids(user) -> list[int]:
    """
    Exclude:
        - alr recommended (filmbank)
        - alr watched/imported (movieuser)
    """

    # Filmbank -> Movie
    bank_ids = (
        FilmBank.objects.filter(user=user, movie__tmdb_id__isnull=False)
        .values_list("movie__tmdb_id", flat=True)
    )

    # MovieUser -> Movie
    watched_ids = (
        MovieUser.objects.filter(user=user, movie__tmdb_id__isnull=False)
        .values_list("movie__tmdb_id", flat=True)
    )

    # unique + ints
    s = set()
    for x in list(bank_ids) + list(watched_ids):
        try:
            s.add(int(x))
        except Exception:
            continue
    return sorted(s)

def _movie_payload(mv) -> dict:
    # model uses overview in tmdb.py; keep safe fallback
    return {
        "id": mv.id,
        "title": mv.title,
        "tmdb_id": mv.tmdb_id,
        "poster_url": getattr(mv, "poster_url", None),
        # change description
        "description": getattr(mv,"overview", None),
        "avg_rating": getattr(mv, "avg_rating", None),
        "year": getattr(mv, "year", None),
    }

# MAIN ENDPOINT:
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_recommend(request):
    ser = ChatRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    msg = ser.validated_data["message"].strip()

    if len(msg) < 3:
        return Response(
            {"type": "clarify", "assistant": "Tell me what you're in the mood for - genre, vibe, or a movie you liked."},
            status=status.HTTP_200_OK
        )
    
    # Tentative where the movie store id is located
    movies_store_id = os.getenv("OPENAI_MOVIES_VECTOR_STORE_ID")
    if not movies_store_id:
        return Response(
            {"error": "Missing OPENAI_MOVIES_VECTOR_STORE_ID env var (global movies vector store not configured)."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    # taste store may not exist yet (new user)
    taste_store_id = getattr(request.user, "taste_vector_store_id", None)
    
    excluded_tmdb_ids = _get_excluded_tmdb_ids(request.user)
    excluded_set = set(excluded_tmdb_ids)
    excluded_str = ", ".join(map(str, excluded_tmdb_ids[:400])) # cap prompt size

    # pick cheap model by default (override via env)
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    tools = [{
        "type": "file_search",
        "vector_store_ids": [movies_store_id] + ([taste_store_id] if taste_store_id else []),
        "max_num_results": 20,
    }]

    # Prompt
    # tentative
    system = f"""
You are the Film Recommender, a movie recommender.

You MUST follow these rules:
- Recommend exactly 3 movies.
- ONLY recommend movies that appear in the retrieved file_search context (movie docs).
- Do NOT recommend any movie with a TMDB id in this excluded list:
  [{excluded_str}]
- If you cannot find 3 valid movies from retrieved context, respond with:
  {{"type":"clarify","assistant":"...","recommendations":[]}}

Output MUST be valid JSON ONLY (no markdown, no extra text), in this exact shape:
{{
  "type": "recommendations" | "clarify",
  "assistant": "string",
  "recommendations": [
    {{
      "tmdb_id": 123,
      "title": "Movie Title",
      "year": 1999,
      "why": "1-2 sentences tied to user taste + prompt"
    }}
  ]
}}

Be concise. Ground reasons in the user's taste (if present) and the user's prompt.
""".strip()
    
    client = OpenAI()
    
    try:
        resp = client.responses.create(
            model = model,
            input=[
                # give prompt
                {"role":"system","content":[{"type": "text","text": system}]},
                # message from user
                {"role":"user","content":[{"type": "text","text": msg}]},
            ],
            tools=tools,
        )

        out_text = resp.output_text # SDK convenience
        data = json.loads(out_text)

    except json.JSONDecodeError:
        return Response(
            {"type":"clarify","assistant": "I had trouble formatting the response. Try rephrasing your request."},
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error":f"OpenAI call failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    
    if data.get("type") not in ("recommendations","clarify"):
        return Response({
                        "type": "clarify",
            "assistant": "Tell me a bit more about what you want."
        },
        status=status.HTTP_200_OK,
        )
    
    if data.get("type") == "clarify":
        return Response(
            {"type":"clarify","assistant": data.get("assistant","Tell me a bit more about what you want.")},
            status=status.HTTP_200_OK,
        )
    
    recs = data.get("recommendations")
    if not isinstance(recs, list) or not recs:
        return Response(
            {
            "type": "clarify",
            "assistant": "Tell me a bit more about what you want."
            },
            status=status.HTTP_200_OK,
        )
    
    # Persist + Build Response
    # now we create the payload 
    movies_payload = []
    for r in recs[:3]:
        tmdb_id = r.get("tmdb_id")
        if not tmdb_id:
            continue

        # hard exclude safety check
        try:
            tmdb_id_int = int(tmdb_id)
        except Exception:
            continue
        # ensure movie exists in DB
        if tmdb_id_int in excluded_set:
            continue
        try:
            mv = upsert_tmdb_movie(tmdb_id_int)
        except Exception:
            continue

        # persist recommendation in filmbank
        FilmBank.objects.update_or_create(
            user = request.user,
            movie=mv,
            defaults={
                "query_text":msg,
                "reason": r.get("why", ""),
            },
        )

        movies_payload.append(_movie_payload(mv))

    if not movies_payload:
        return Response(
            {"type":"clarify","assistant": "I couldn't lock in 3 good picks. Try a 'like <movie title>' request."},
            status=status.HTTP_200_OK,
        )
    
    return Response(
        {
            "type": "recommendations",
            "assistant": data.get("assistant", "Here are a few picks:"),
            "recommendations": movies_payload,
        },
        status=status.HTTP_200_OK,
    )