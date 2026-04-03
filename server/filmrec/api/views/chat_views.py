"""
Endpoints for Chat.js
RAG-based recommender using OpenAI API + File search
"""
import os
import logging
import time
import json

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from openai import OpenAI

from ..models import (
    FilmBank,
    MovieUser,
    Movie
)

from ..utils.photoHelper import _build_poster_url
from ..serializer import ChatRequestSerializer

logger = logging.getLogger(__name__)

# Get the reasoning as to why Film Recommender gave you the movie
def _clean_why(value: str) -> str:
    text = " ".join((value or "").split()).strip()
    if not text:
        return "Matches your taste and current prompt."
    return text[:280]

def _safe_parsed_response(resp):
    parsed = getattr(resp, "output_parsed", None)

    if isinstance(parsed, dict):
        return parsed
    if hasattr(parsed, "model_dump"):
        dumped = parsed.model_dump()
        if isinstance(dumped, dict):
            return dumped

    out_text = getattr(resp, "output_text", None)
    if out_text:
        try:
            clean = out_text.strip()
            if clean.startswith("```"):
                clean = clean.split("```", 2)[1]
                if "\n" in clean:
                    clean = clean[clean.index("\n"):].strip()
                if clean.endswith("```"):
                    clean = clean[:-3].strip()
            data = json.loads(clean)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    raise ValueError(
        f"Structured output was not parsed into a dict. "
        f"output_text={getattr(resp, 'output_text', None)!r}"
    )
def _is_valid_movie(mv) -> bool:
    return bool(
        mv
        and getattr(mv, "tmdb_id", None)
        and getattr(mv, "title", None)
    )

def _call_openai_with_retry(
    client, *, model, system, msg, tools=None, text_format=None, timeout=25, max_attempts=2
):
    last_exc = None
    resp = None

    for attempt in range(1, max_attempts + 1):
        try:
            kwargs = {
                "model": model,
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": msg}],
                    },
                ],
                "timeout": timeout,
            }
            if tools:
                kwargs["tools"] = tools
            if text_format:
                kwargs["text"] = {"format": text_format}

            resp = client.responses.create(**kwargs)
            return _safe_parsed_response(resp)

        except Exception as e:
            last_exc = e
            logger.warning(
                "OpenAI chat attempt %s/%s failed: %s | output_text=$r",
                attempt,
                max_attempts,
                str(e),
                getattr(resp, "output_text", "NO_RESP") if 'resp' in dir() else "NO_RESP",
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
        "poster_url": _build_poster_url(mv),
        "description": getattr(mv,"overview", None),
        "avg_rating": getattr(mv, "avg_rating", None),
        "year": getattr(mv, "year", None),
        "why": why,
    }

def _retrieve_and_rank(client, *, model, msg, movies_store_id, taste_store_id, excluded_str):
    tools = [
        {
            "type": "file_search",
            "vector_store_ids": [movies_store_id] + ([taste_store_id] if taste_store_id else []),
            "max_num_results": 8,
        }
    ]
    taste_line = (
        "A user taste summary is available in the vector store - use it to personalize."
        if taste_store_id
        else "No taste summary available, rely only on the user's prompt."
    )
    system = f"""
Movie recommender. Use retrieved context to find and rank real candidates only.
Return 3-5 movies, strongest first. No invented titles or TMDB IDs.
Exclude TMDB IDs: [{excluded_str}]
{taste_line}
""".strip()

    return _call_openai_with_retry(
        client,
        model=model,
        system=system,
        msg=msg,
        tools=tools,
        text_format=CHAT_RESPONSE_SCHEMA,
        timeout=60,
        max_attempts=1,
    )

def _build_contextual_query(msg: str, user) -> str:
    parts = [msg.strip()]

    recent_movies = list(
        MovieUser.objects.filter(
            user=user,
            movie__title__isnull=False, 
            watch_status="Watched",
        )
        .select_related("movie")
        .order_by("-watched_date", "-id")[:3] # recent watch pull ups
    )

    if recent_movies:
        recent_titles = [mu.movie.title for mu in recent_movies if mu.movie and mu.movie.title]
        if recent_titles:
            parts.append("recent user watches: " + ", ".join(recent_titles))
    
    return "\n".join(parts)

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
                "maxItems": 5,  # 3 + 2 backups
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
    contextual_msg = _build_contextual_query(msg, request.user)
    
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
    excluded_str = ", ".join(map(str, excluded_tmdb_ids[:150])) # cap prompt size

    # pick cheap model by default (override via env)
    model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    client = OpenAI()

    try:
        data = _retrieve_and_rank(
            client,
            model=model,
            msg=contextual_msg,
            movies_store_id=movies_store_id,
            taste_store_id=taste_store_id,
            excluded_str=excluded_str,
        )
    except Exception as e:
        logger.exception("chat_recommend retrieval failed user=%s", request.user.id)
        return Response(
            {"error": "Recommendation service is temporarily unavailable."},
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
        if tmdb_id_int in excluded_set or tmdb_id_int in seen_tmdb_ids:
            continue    

        # just look up no tmdb api call
        mv = Movie.objects.filter(tmdb_id=tmdb_id_int).first()

        if not mv:
            # movie not in db yet - skip rather than blocking on TMDB fetch
            logger.info(
                "Chat_recommend skipping unknown tmdb_id=%s user=%s",
                tmdb_id_int, request.user.id,
            )
            continue

        if not _is_valid_movie(mv):
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
            "chat_recommend clarify after filter user=%s, taste_store=%s excluded_count=%s raw_recs=%s final_recs=%s",
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
        "chat_recommend success user=%s taste_store=%s excluded_count=%s raw_recs=%s final_recs=%s",
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
