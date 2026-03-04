"""
TMDB Service Layer

Responsibilites:
    - TMDB API wrapper (w/ retries)
    - Search movies
    - fetch movie details (with credits)
    - upsert a movie by tmdb_id 
        create/update movie + enrich genres/cast/crew
    - attach TMDB metadata to an existing movie
        - e.g. a movie created by letterboxd data
    
Notes:
    - This service should not import DRF.
    - Views should call these functions and handle errors.
"""
from __future__ import annotations
import os
import requests
from typing import Any, Dict, Optional, Tuple
from datetime import datetime

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from django.db import transaction
from django.core.exceptions import ValidationError


from ..models import (
    Movie,
    Person,
    Genre,
    MovieGenre,
    MovieCast,
    MovieCrew,
)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

IMG_BASE_W500 = "https://image.tmdb.org/t/p/w500"
IMG_PROFILE_W185 = "https://image.tmdb.org/t/p/w185"

DEFAULT_TIMEOUT_S = 15

# private
_session = requests.session()

retries = Retry(
    total = 3,
    connect = 3,
    backoff_factor=0.5,
    status_forcelist=[429,500,502,503,504],
    allowed_methods=["GET"],
    raise_on_status=False,
)

# Make private
_adapter = HTTPAdapter(max_retries=retries)
_session.mount("https://",_adapter)
_session.mount("http://",_adapter)

def tmdb_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not TMDB_API_KEY:
        raise RuntimeError("TMDB_API_KEY not set")
    
    params = dict(params or {})
    params["api_key"] = TMDB_API_KEY

    url = f"{BASE_URL}{path}"
    r = _session.get(url, params=params, timeout=DEFAULT_TIMEOUT_S)

    # If retry exhausted and still 4xx/5xx/ raise with context
    try:
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(
            f"TMDB HTTP error {r.status_code}: {url}"
        ) from e
    
    return r.json()

def search_movie(query: str) -> Dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"results": []}
    return tmdb_get("/search/movie", {"query":q})

def get_movie_details(tmdb_id: int) -> Dict[str, Any]:
    return tmdb_get(f"/movie/{tmdb_id}", {"append_to_response":"credits"})

# HELPER FUNCTIONS
def _parse_year_from_release_date(release_date: Optional[str]) -> Optional[int]:
    if not release_date:
        return None
    try:
        return datetime.strptime(release_date, "%-%m-%d").date().year
    except Exception:
        return None
    
def _safe_country_name(data: Dict[str, Any]) -> Optional[str]:
    countries = data.get("produciton_countries") or []
    if not countries:
        return None
    first = countries[0] or {}
    return first.get("name") or None

def _enrich_movie_relations_from_tmdb(*, movie: Movie, data: Dict[str, Any], cast_limit: int = 12 ) -> None:
    # Refactored version of the previous injection functions down below
    # enriches movie relations with genre, cast, crew links
    # uses a delete and recreate approach for simplicity adn correctness.

    # --- Genres ---
    # simple + idempotent: wipe & re-add links for this movie
    MovieGenre.objects.filter(movie=movie).delete()
    for g in data.get("genres") or []:
        tmdb_gid = g.get("id")
        name = (g.get("name") or "").strip()
        if not tmdb_gid or not name:
            continue

        genre_obj, _ = Genre.objects.update_or_create(
            tmdb_id=tmdb_gid,
            defaults={"name": name},
        )
        MovieGenre.objects.create(movie=movie,genre=genre_obj)

    credits = data.get("credits") or {}

    # --- Cast (Actors) ---
    MovieCast.objects.filter(movie=movie).delete()
    for c in (credits.get("cast") or [])[:cast_limit]:
        tmdb_pid = c.get("id")
        if not tmdb_pid:
            continue
        name = (c.get("name") or c.get("original_name") or "Unknown").strip()
        profile_path = c.get("profile_path")
        profile_url = (IMG_BASE_W500 + profile_path) if profile_path else None

        person_obj, _ = Person.objects.update_or_create(
            tmdb_id=tmdb_pid,
            defaults={
                "name": name,
                "profile_url":(profile_url),
            },
        )
        MovieCast.objects.create(
            movie=movie,
            person=person_obj,
            character=c.get("character"),
            order=c.get("order"),
        )

    # --- Crew (Directors only for now) ---
    MovieCrew.objects.filter(movie=movie, job="Director").delete()

    for cr in credits.get("crew") or []:
        if cr.get("job") != "Director":
            continue

        tmdb_pid = cr.get("id")
        if not tmdb_pid:
            continue
        name = (cr.get("name") or cr.get("original_name") or "Unknown").strip()
        profile_path = cr.get("profile_path")
        profile_url = (IMG_PROFILE_W185 + profile_path) if profile_path else None

        person_obj, _ = Person.objects.update_or_create(
            tmdb_id=tmdb_pid,
            defaults={
                "name":name,
                "profile_url":(profile_url),
            }
        )

        MovieCrew.objects.create(
            movie=movie,
            person=person_obj,
            job="Director",
            department=cr.get("department"),
        )
    
def _upsert_movie_fields_from_tmdb(*, tmdb_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    release_date = data.get("release_date")
    year = _parse_year_from_release_date(release_date)
    
    poster_path = data.get("poster_path")
    poster_url = (IMG_BASE_W500 + poster_path) if poster_path else None

    return {
            "title":data.get("title" or "").strip() or "Unknown",
            "year": year,
            "overview": data.get("overview"),
            "avg_rating": data.get("vote_average"),
            "budget": data.get("budget"),
            "revenue": data.get("revenue"),
            "runtime": data.get("runtime"),
            "language": data.get("original_language"),
            "country": _safe_country_name(data),
            "poster_url": poster_url,
            "tmdb_id": tmdb_id,
        }

@transaction.atomic
def upsert_tmdb_movie(movie_id: int, tmdb_id, cast_limit: int = 12) -> Movie:
    try:
        tmdb_id_int = int(tmdb_id)
    except Exception:
        raise ValidationError("tmdb_id and  must be integers")
    
    data = get_movie_details(tmdb_id_int)
    fields = _upsert_movie_fields_from_tmdb(tmdb_id=tmdb_id_int, data=data)

    movie, _ = Movie.objects.update_or_create(
        tmdb_id=tmdb_id_int,
        defaults=defaults,
    )

@transaction.atomic
def attach_tmdb_to_movie(*, movie_id: int, tmdb_id: int, cast_limit: int=12) -> Movie:
    """
    Attach TMDB id to existing movie row and enrich it with TMDB fields + credits.
    """

    try:
        tmdb_id_int = int(tmdb_id)
        movie_id_int = int(movie_id)
    except Exception:
        raise ValidationError("tmdb_id and movie_id must be integers")
    
    movie = Movie.objects.filter(id=movie_id_int).first()
    if not movie:
        raise ValidationError("Movie not found")
    
    # if another movie alr has this tmdb id, don't allow attaching
    existing = Movie.objects.filter(tmdb_id= tmdb_id_int).exclude(id=movie).first()
    if existing:
        raise ValidationError("That tmdb_id is already attached to another movie")
    
    data = get_movie_details(tmdb_id_int)
    fields = _upsert_movie_fields_from_tmdb(tmdb_id=tmdb_id_int, data=data)

    # update the existing movie (preserve letterboxd_ur)
    for k, v in fields.items():
        setattr(movie, k, v)
    movie.save()

    _enrich_movie_relations_from_tmdb(movie=movie, data=data, cast_limit=cast_limit)
    return movie