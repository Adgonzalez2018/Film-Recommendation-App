# api/services/tmdb.py
"""
TMDB Service Layer

TMDB ENRICHMENT
used for Asynchronous jobs
If user gives FilmRecommender a movie that we DONT KNOW -> Find it and enrich it inside our DB

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
from typing import Any, Dict, Optional
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
            f"TMDB HTTP error {r.status_code}: {url} - {r.text[:200]}"
        ) from e
    
    return r.json()

def search_movie(query: str) -> Dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"results": []}
    return tmdb_get("/search/movie", {"query":q})

def get_movie_details(tmdb_id: int) -> Dict[str, Any]:
    return tmdb_get(f"/movie/{tmdb_id}", {"append_to_response":"credits"})

"""
--- HELPER FUNCTIONS ---
"""
def _parse_year_from_release_date(release_date: Optional[str]) -> Optional[int]:
    if not release_date:
        return None
    try:
        return datetime.strptime(release_date, "%Y-%m-%d").date().year
    except Exception:
        return None
    
def _safe_country_name(data: Dict[str, Any]) -> Optional[str]:
    countries = data.get("production_countries") or []
    if not countries:
        return None
    first = countries[0] or {}
    return first.get("name") or None

def _enrich_movie_relations_from_tmdb(*, movie: Movie, data: Dict[str, Any], cast_limit: int = 12 ) -> None:
    """
    Enrich genre, cast, and crew links for `movie` from a TMDB details payload.
    uses bulk operations - safe to call inside an existing atomic block.
    """
    with transaction.atomic():
        _sync_genres(movie, data.get("genres") or [])
        credits = data.get("credits") or {}
        _sync_cast(movie, (credits.get("cast") or [])[:cast_limit])
        _sync_crew(movie, credits.get("crew") or [])
    
def _upsert_movie_fields_from_tmdb(*, tmdb_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    release_date = data.get("release_date")
    year = _parse_year_from_release_date(release_date)
    
    poster_path = data.get("poster_path")
    poster_url = (IMG_BASE_W500 + poster_path) if poster_path else None

    # keywords comes back as {"keywords": [...]} when appended
    kw_list = (data.get("keywords") or {}).get("keywords") or []
    keywords_str = ", ".join(k["name"] for k in kw_list if k.get("name"))

    collection = (data.get("belongs_to_collection") or {}).get("name")

    return {
        "title": (data.get("title") or "").strip() or "Unknown",
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
        "tagline": (data.get("tagline") or "").strip() or None,
        "keywords": keywords_str or None,
        "collection_name": collection or None,
    }
@transaction.atomic
def upsert_tmdb_movie(tmdb_id, cast_limit: int = 12) -> Movie:
    try:
        tmdb_id_int = int(tmdb_id)
    except Exception:
        raise ValidationError("tmdb_id and  must be integers")
    
    data = get_movie_details(tmdb_id_int)
    defaults = _upsert_movie_fields_from_tmdb(tmdb_id=tmdb_id_int, data=data)

    movie, _ = Movie.objects.update_or_create(
        tmdb_id=tmdb_id_int,
        defaults=defaults,
    )
    _enrich_movie_relations_from_tmdb(movie=movie, data=data, cast_limit=cast_limit)
    return movie

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
    exclude_id = movie.id if hasattr(movie, "id") else movie
    existing = Movie.objects.filter(tmdb_id= tmdb_id_int).exclude(pk=exclude_id).first()
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

def find_best_tmdb_movie_match(title: str, year: Optional[int] = None) -> Optional[int]:
    results = search_movie(title).get("results", [])
    if not results:
        return None
    
    # prefer exact title-ish matches and matching release year
    best = None
    best_score = -1

    for r in results[:10]:
        score = 0
        tmdb_title = (r.get("title") or"").strip().lower()
        q = (title or "").strip().lower()

        if tmdb_title == q:
            score += 5
        elif q and q in tmdb_title:
            score += 2
        
        release_date = r.get("release_date") or ""
        tmdb_year = None
        if len(release_date) >= 4 and release_date[:4].isdigit():
            tmdb_year = int(release_date[:4])

        if year is not None and tmdb_year == year:
            score += 5
        elif year is not None and tmdb_year is not None and abs(tmdb_year - year) == 1:
            score += 2

        popularity = r.get("popularity") or 0
        score += min(popularity / 100.0, 2)

        if score > best_score:
            best_score = score
            best = r

    return best.get("id") if best else None


def _sync_genres(movie: Movie, genres_data: list) -> None:
    # collect valid entries
    entries = [
        (g["id"], (g.get("name") or "").strip())
        for g in genres_data
        if g.get("id") and (g.get("name") or "").strip()
    ]

    if not entries:
        MovieGenre.objects.filter(movie=movie).delete()
        return
    tmdb_ids = [e[0] for e in entries]
    name_by_id = {e[0]: e[1] for e in entries}

    # upsert genre rows (names may change on TMDB's end)
    existing_genres = {g.tmdb_id: g for g in Genre.objects.filter(tmdb_id__in=tmdb_ids)}
    to_create = []
    to_update = []
    for tmdb_gid, name in entries:
        if tmdb_gid in existing_genres:
            g = existing_genres[tmdb_gid]
            if g.name != name:
                g.name = name
                to_update.append(g)
            else:
                to_create.append(Genre(tmdb_id=tmdb_gid,name=name))
    if to_create:
        Genre.objects.bulk_create(to_create, ignore_conflicts=True)
    if to_update:
        Genre.objects.bulk_update(to_update, ["name"])
    genre_objs = Genre.objects.filter(tmdb_id__in=tmdb_ids)
    MovieGenre.objects.filter(movie=movie).delete()
    MovieGenre.objects.bulk_create(
        [MovieGenre(movie=movie, genre=g) for g in genre_objs],
        ignore_conflicts=True
    )

def _sync_cast(movie: Movie, cast_data: list) -> None:
    # collect valid entries
    entries = []
    for c in cast_data:
        tmdb_pid = c.get("id")
        if not tmdb_pid:
            continue
        name = (c.get("name") or c.get("original_name") or "Unknown").strip()
        profile_path = c.get("profile_path")
        profile_url = (IMG_BASE_W500 + profile_path) if profile_path else None
        character = (c.get("character") or "").strip()[:255] or None
        order = c.get("order")
        entries.append((tmdb_pid, name, profile_url, character, order))

    if not entries:
        MovieCast.objects.filter(movie=movie).delete()
        return
    tmdb_ids = [e[0] for e in entries]
    _bulk_upsert_persons(tmdb_ids, {e[0]: (e[1], e[2]) for e in entries})
    person_map = {p.tmdb_id: p for p in Person.objects.filter(tmdb_id__in=tmdb_ids)}

    MovieCast.objects.filter(movie=movie).delete()
    MovieCast.objects.bulk_create(
        [
            MovieCast(
                movie=movie,
                person=person_map[tmdb_pid],
                character=character,
                order=order,
            )
            for tmdb_pid, _name, _url, character, order in entries
            if tmdb_pid in person_map
        ],
        ignore_conflicts=True,
    )

def _sync_crew(movie: Movie, crew_data: list) -> None:
    # collect valid entries
    entries = []
    for cr in crew_data:
        if cr.get("job") != "Director":
            continue
        tmdb_pid = cr.get("id")
        if not tmdb_pid:
            continue
        name = (cr.get("name") or cr.get("original_name") or "Unknown").strip()
        profile_path = cr.get("profile_path")
        profile_url = (IMG_PROFILE_W185 + profile_path) if profile_path else None
        department = cr.get("department")
        entries.append((tmdb_pid, name, profile_url, department))

    MovieCrew.objects.filter(movie=movie, job="Director").delete()

    if not entries:
        return
    
    tmdb_ids = [e[0] for e in entries]
    _bulk_upsert_persons(tmdb_ids, {e[0]: (e[1], e[2]) for e in entries})
    person_map = {p.tmdb_id: p for p in Person.objects.filter(tmdb_id__in=tmdb_ids)}

    MovieCrew.objects.bulk_create(
        [
            MovieCrew(
                movie=movie,
                person=person_map[tmdb_pid],
                job="Director",
                department=department,
            )
            for tmdb_pid, _name, _url, department in entries
            if tmdb_pid in person_map
        ],
        ignore_conflicts=True,
    )

def _bulk_upsert_persons(tmdb_ids: list, name_url_by_tmdb_id: dict) -> None:
    # Create missing person rows and update name/profile_url for existing ones
    # one SELECT + at most one bulk_create + one bulk update
    existing = {p.tmdb_id: p for p in Person.objects.filter(tmdb_id__in=tmdb_ids)}
    to_create = []
    to_update = []
    for tmdb_pid in tmdb_ids:
        name, profile_url = name_url_by_tmdb_id[tmdb_pid]
        changed = False
        if tmdb_pid in existing:
            p = existing[tmdb_pid]
            if p.name != name:
                p.name = name
                changed = True
            if p.profile_url != profile_url:
                p.profile_url = profile_url
                changed = True
            if changed:
                to_update.append(p)
        else:
            to_create.append(Person(tmdb_id=tmdb_pid, name=name, profile_url=profile_url))

    if to_create:
        Person.objects.bulk_create(to_create, ignore_conflicts=True)
    if to_update:
        Person.objects.bulk_update(to_update, ["name", "profile_url"])

def get_movie_details(tmdb_id: int) -> Dict[str, Any]:
    return tmdb_get(f"/movie/{tmdb_id}", {"append_to_response": "credits,keywords"})

