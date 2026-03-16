"""
Endpoints for Chat.js
RAG-based recommender using OpenAI API + File search
"""
import os
import json
import logging
import time

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from openai import OpenAI

from ..models import (
    FilmBank,
    MovieUser,
)
from ..services.tmdb import upsert_tmdb_movie  
from ..serializer import ChatRequestSerializer

logger = logging.getLogger(__name__)

def _clean_why(value: str) -> str:
    text = " ".join((value or "").split()).strip()
    if not text:
        return "Matches your taste and current prompt."
    return text[:280]

def _safe_parsed_response(resp):
    parsed = getattr(resp, "output_parsed", None)
    if isinstance(parsed, dict):
        return parsed
    raise ValueError("Structured out put was not parsed into a dict.")

def _is_valid_movie(mv) -> bool:
    return bool(
        mv
        and getattr(mv, "tmdb_id", None)
        and getattr(mv, "title", None)
    )

def _call_openai_with_retry(client, *, model, system, msg, tools, text_format, timeout=25, max_attempts=2):
    last_exc = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": msg}],
                    },
                ],
                tools=tools,
                text={"format": text_format},
                timeout=timeout,
            )
            return _safe_parsed_response(resp)
        
        except Exception as e:
            last_exc = e
            logger.warning(
                "OpenAi chat attempt %s/%s failed: %s",
                attempt,
                max_attempts,
                str(e),
            )

            if attempt < max_attempts:
                time.sleep(1.2)
    raise last_exc
        
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

def _movie_payload(mv, why: str = "") -> dict:
    # model uses overview in tmdb.py; keep safe fallback
    return {
        "id": mv.id,
        "title": mv.title,
        "tmdb_id": mv.tmdb_id,
        "poster_url": getattr(mv, "poster_url", None),
        "description": getattr(mv,"overview", None),
        "avg_rating": getattr(mv, "avg_rating", None),
        "year": getattr(mv, "year", None),
        "why": why,
    }

CHAT_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "name": "film_recommendation_response",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "type": {
                "type": "string",
                "enum": ["recommendations", "clarify"],
            },
            "assistant": {
                "type": "string",
                "minLength": 1,
                "maxLength": 200
            },
            "recommendations": {
                "type": "array",
                "minItems": 0,
                "maxItems": 6,  # 3 + 3 backups
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "tmdb_id": {
                            "type": "integer",
                            "minimum": 1
                        },
                        "why": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 280   # short explanation
                        },
                    },
                    "required": ["tmdb_id", "why"],
                },
            },
        },
        "required": ["type", "assistant", "recommendations"],
    },
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
            {
                "type": "clarify", 
                "assistant": "Tell me what you're in the mood for - genre, vibe, or a movie you liked.",
                "recommendations": [],
            },
            status=status.HTTP_200_OK
        )
    
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
    model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    vector_store_ids = [movies_store_id]
    if taste_store_id:
        vector_store_ids.append(taste_store_id)

    tools = [{
        "type": "file_search",
        "vector_store_ids": vector_store_ids,
        "max_num_results": 20,
    }]

    # Prompt
    # tentative
    system = f"""
You are the Film Recommender.

Your job is to recommend movies using retrieved context from:
1. a movie corpus vector store
2. an optional user taste-summary vector store

Important Grounding Rules:
- Use the taste-summary store only to understand the user's preferences.
- Use the movie corpus to choose actual movies.
- Do NOT invent movies.
- Do NOT invent TMDB ids.
- Recommend between 3 and 6 distinct movies. Prefer the strongest 3 first, then include up to 3 back ups.
- Do NOT recommend any movie whose tmdb id is in this excluded list: 
  [{excluded_str}]
- If you cannot identiy exactly 3 valid movie cnadidates from retrieved context, return a clarify response.

Output valid JSON ONLY, with no markdown and no extra text, in exactly this shape:
{{
  "type": "recommendations" | "clarify",
  "assistant": "string",
  "recommendations": [
    {{
      "tmdb_id": 123,
      "why": "1-2 concise sentences tied to the user's taste and prompt"
    }}
  ]
}}
""".strip()
    
    client = OpenAI()
    
    try:
        data = _call_openai_with_retry(
            client,
            model=model,
            system=system,
            msg=msg,
            tools=tools,
            text_format=CHAT_RESPONSE_SCHEMA,
            timeout=25,
            max_attempts=2,
        )

    except Exception as e:
        logger.exception(
            "chat_recommend OpenAI failure user=%s taste_store=%s",
            request.user.id,
            bool(taste_store_id),
        )
        return Response(
            {"error":"Recommendation service is temporarily unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    
    if not isinstance(data, dict):
        return Response(
            {
                "type": "clarify",
                "assistant": "Tell me a bit more about what you want.",
                "recommendations": [],
            },
        status=status.HTTP_200_OK,
        )
    
    if data.get("type") == "clarify":
        return Response(
            {
                "type":"clarify",
                "assistant": data.get("assistant","Tell me a bit more about what you want."),
                "recommendations": [],
            },
            status=status.HTTP_200_OK,
        )
    
    recs = data.get("recommendations", [])
    if not isinstance(recs, list) or len(recs) < 3:
        return Response(
            {
                "type": "clarify",
                "assistant": "Tell me a bit more about what you want.",
                "recommendations": [],
            },
            status=status.HTTP_200_OK,
        )
    
    # Persist + Build Response
    # now we create the payload 
    movies_payload = []
    seen_tmdb_ids = set()

    for r in recs:
        tmdb_id = r.get("tmdb_id")
        why = _clean_why(r.get("why"))
        # hard exclude safety check
        try:
            tmdb_id_int = int(tmdb_id)
        except Exception:
            continue

        # ensure movie exists in DB
        if tmdb_id_int in excluded_set:
            continue

        if tmdb_id_int in seen_tmdb_ids:
            continue

        try:
            mv = upsert_tmdb_movie(tmdb_id_int)
        except Exception:
            logger.warning(
                "upser_tmdb_movie failed user=%s tmdb_id=%s",
                request.user.id,
                tmdb_id_int,
            )
            continue

        if not _is_valid_movie(mv):
            logger.warning(
                "Invalid movie after upsert user=%s tmdb_id=%s",
                request.user.id,
                tmdb_id_int,
            )
            continue
    
        seen_tmdb_ids.add(tmdb_id_int)

        # persist recommendation in filmbank
        FilmBank.objects.update_or_create(
            user = request.user,
            movie=mv,
            defaults={
                "query_text":msg,
                "reason": why,
            },
        )

        movies_payload.append(_movie_payload(mv, why=why))

        if len(movies_payload) == 3:
            break

    if  len(movies_payload) != 3:
        logger.info(
            "chat_recommend clarify_after filter user=%s, taste_store=%s excluded_count=%s raw_recs=%s final_recs=%s",
            request.user.id,
            bool(taste_store_id),
            len(excluded_tmdb_ids),
            len(recs) if isinstance(recs,list) else None,
            len(movies_payload),
        )
        return Response(
            {
                "type":"clarify",
                "assistant": "I couldn't lock in 3 good picks. Try a 'like <movie title>' request.",
                "recommendations": [],
            },
            status=status.HTTP_200_OK,
        )
    
    logger.info(
        "chat_recommend usccess user=%s taste_store=%s excluded_count=%s raw_recs=%s final_recs=%s",
        request.user.id,
        bool(taste_store_id),
        len(excluded_tmdb_ids),
        len(recs) if isinstance(recs,list) else None,
        len(movies_payload),
    )
    return Response(
        {
            "type": "recommendations",
            "assistant": data.get("assistant", "Here are a few picks:"),
            "recommendations": movies_payload,
        },
        status=status.HTTP_200_OK,
    )
