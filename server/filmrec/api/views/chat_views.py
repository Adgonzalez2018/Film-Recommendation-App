"""
Endpoints for Chat.js
RAG-based recommender using OpenAI API + File search
"""
import os
import logging
import time
import json
import re

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
from ..services.tmdb import upsert_tmdb_movie
logger = logging.getLogger(__name__)

MIN_RECS = 1

# Get the reasoning as to why Film Recommender gave you the movie
def _clean_why(value: str, max_len: int = 360) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip()

    if not text:
        return "Matches your taste and current prompt."

    # remove common junk prefixes
    text = re.sub(r"^(why\s*[:\-]\s*|because\s+)", "", text, flags=re.IGNORECASE).strip()
    text = text.strip("•- ")

    if len(text) <= max_len:
        return text

    # try to cut at sentence boundary first
    clipped = text[:max_len]
    sentence_cut = max(clipped.rfind(". "), clipped.rfind("! "), clipped.rfind("? "))

    if sentence_cut >= int(max_len * 0.6):
        clipped = clipped[: sentence_cut + 1].strip()
    else:
        # fallback: cut at last word
        clipped = clipped.rsplit(" ", 1)[0].strip()

    if clipped and clipped[-1] not in ".!?":
        clipped += "…"

    return clipped

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
            logger.debug(
                "OpenAi raw response: %s",
                getattr(resp, "output_text", None)
            )
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
        "letterboxd_uri": getattr(mv, "letterboxd_uri", None),
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
You are a film recommender. Use the retrieved movie context and user taste summary to recommend films.

Return 3-5 movies ranked strongest first. 
For each recommendation:
- Use exactly one retrieved movie as the source
- The tmdb_id, title, and why must all refer to the same movie
- Do not mix details from different retrieved films
- The "why" must reference the returned movie, not another candidate

For each "why":
- References something specific from the user's taste (a director, genre, theme, or mood they like)
- Mentions one concrete detail about the film (tone, theme, or style) that makes it a match
- Is 1-2 sentences, specific and personal — not generic praise like "a great film" or "you might enjoy"

Exclude TMDB IDs: [{excluded_str}]
{taste_line}
No invented titles or TMDB IDs. Only recommend movies from the retrieved context.
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
        .order_by("-watched_date", "-id")[:5]
    )

    if recent_movies:
        recent_titles = [mu.movie.title for mu in recent_movies if mu.movie and mu.movie.title]
        if recent_titles:
            parts.append("recent watches: " + ", ".join(recent_titles))

    # add highly rated movies as taste signal
    loved = list(
        MovieUser.objects.filter(
            user=user,
            movie__title__isnull=False,
            rating__gte=4.0,
        )
        .select_related("movie")
        .order_by("-rating", "-id")[:5]
    )
    if loved:
        loved_titles = [mu.movie.title for mu in loved if mu.movie and mu.movie.title]
        if loved_titles:
            parts.append("highly rated: " + ", ".join(loved_titles))

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
                        },
                        "title": {"type": "string"},
                        "why": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 280   # short explanation
                        },
                    },
                    "required": ["tmdb_id", "title", "why"],
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
    logger.warning(
        "chat_recommend HIT user=%s", request.user.id,
    )
    ser = ChatRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    msg = ser.validated_data["message"].strip()
    start_time = time.time()
    logger.info(
        "chat_recommend start user=%s msg_len=%s",
        request.user.id,
        len(msg),
    )

    # If message is too short -> ask for clarification
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
    logger.debug(
        "chat_recommend contextual_msg user=%s msg=%s",
        request.user.id,
        contextual_msg,
    )

    movies_store_id = os.getenv("OPENAI_MOVIES_VECTOR_STORE_ID")
    # if VECTOR STORAGE DOWN -> send http 500 request
    if not movies_store_id:
        return Response(
            {"error": "Missing OPENAI_MOVIES_VECTOR_STORE_ID env var (global movies vector store not configured)."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    # Find taste summary in storage 
    taste_store_id = getattr(request.user, "taste_vector_store_id", None)
    # Exclude tmdbs from watchlist
    excluded_tmdb_ids = _get_excluded_tmdb_ids(request.user)
    excluded_set = set(excluded_tmdb_ids)
    excluded_str = ", ".join(map(str, excluded_tmdb_ids[:150])) # cap prompt size

    # pick cheap model by default (override via env)
    model = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    client = OpenAI()
    logger.info(
        "chat_recommend setup user=%s movies_store=%s taste_store=%s excluded_movies=%s",
        request.user.id,
        bool(movies_store_id),
        bool(taste_store_id),
        len(excluded_tmdb_ids),
    )
    try:
        logger.info(
            "chat_recommend calling_openai user=%s model=%s",
            request.user.id,
            model,
        )
        data = _retrieve_and_rank(
            client,
            model=model,
            msg=contextual_msg,
            movies_store_id=movies_store_id,
            taste_store_id=taste_store_id,
            excluded_str=excluded_str,
        )
        logger.debug(
            "chat_recommend parsed_response user=%s data=%s",
            request.user.id,
            data,
        )
    except Exception as e:
        logger.exception("chat_recommend retrieval failed user=%s msg=%s", request.user.id, msg)
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
    film_bank_entries = []

    for r in recs:
        tmdb_id = r.get("tmdb_id")
        returned_title = (r.get("title") or "").strip()
        why = _clean_why(r.get("why"))

        # hard exclude safety check
        try:
            tmdb_id_int = int(tmdb_id)
        except Exception:
            continue

        # ensure movie exists in DB
        if tmdb_id_int in excluded_set:
            logger.debug("Skipping tmdb_id=%s reason=excluded", tmdb_id_int)
            continue

        if tmdb_id_int in seen_tmdb_ids:
            logger.debug("Skipping tmdb_id=%s reason=duplicate", tmdb_id_int)
            continue

        # just look up no tmdb api call
        mv = Movie.objects.filter(tmdb_id=tmdb_id_int).first()
        if not mv:
            try:
                mv = upsert_tmdb_movie(tmdb_id_int)
            except:
                continue
        
        if mv and returned_title:
            if mv.title.strip().lower() != returned_title.lower():
                logger.warning(
                    "Rejecting mismatched recommendation tmbdb_id=%s returned_title=%r db_title=%r",
                    tmdb_id_int,
                    returned_title,
                    mv.title,
                )
                continue

        if not _is_valid_movie(mv):
            logger.debug("Skipping tmdb_id=%s reason=invalid_movie", tmdb_id_int)
            continue
    
        seen_tmdb_ids.add(tmdb_id_int)
        movies_payload.append(_movie_payload(mv, why=why))
        film_bank_entries.append((mv, why))

        if len(movies_payload) == 3:
            break

    if  len(movies_payload) < 1:
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
    
    for mv, why in film_bank_entries:
        # persist recommendation in filmbank
        FilmBank.objects.update_or_create(
            user = request.user,
            movie=mv,
            defaults={
                "query_text":msg,
                "reason": why,
            },
        )
        logger.debug(
            "FilmBank upsert user=%s movie_id=%s",
            request.user.id,
            mv.id,
        )
    logger.info(
        "chat_recommend success user=%s taste_store=%s excluded_count=%s raw_recs=%s final_recs=%s duration=%.2fs",
        request.user.id,
        bool(taste_store_id),
        len(excluded_tmdb_ids),
        len(recs) if isinstance(recs,list) else None,
        len(movies_payload),
        time.time() - start_time,
    )
    return Response(
        {
            "type": "recommendations",
            "assistant": data.get("assistant", "Here are a few picks:"),
            "recommendations": movies_payload,
        },
        status=status.HTTP_200_OK,
    )
