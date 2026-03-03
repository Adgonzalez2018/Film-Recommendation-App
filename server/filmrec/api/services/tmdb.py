# Service Py File for TMDB Views
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime

from django.db import transaction
from django.core.exceptions import ValidationError

from .tmdb import get_movie_details, IMG_BASE_W500, IMG_PROFILE_W185

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

session = requests.session()

retries = Retry(
    total = 3,
    backoff_factor=0.5,
    status_forcelist=[429,500,502,503,504],
    allowed_methods=["GET"],
)
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://",adapter)
session.mount("http://",adapter)

def tmdb_get(path, params=None):
    if not TMDB_API_KEY:
        raise RuntimeError("TMDB_API_KEY not set")
    params = params or {}
    params["api_key"] = TMDB_API_KEY

    try:
        r = session.get(f"{BASE_URL}{path}", params=params,timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(
            f"TMDB HTTP error {r.status_code}: {r.text[:300]}"
        ) from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"TMDB request failed: {str(e)}") from e
    



def tmdb_get(path, params=None):
    if not TMDB_API_KEY:
        raise RuntimeError("API Key not set")
    
    params = params or {}
    params["api_key"] = TMDB_API_KEY

    r = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def search_movie(query):
    return tmdb_get("/search/movie", {"query":query})

def get_movie_details(tmdb_id):
    return tmdb_get(f"/movie/{tmdb_id}", {"append_to_response":"credits"})

# ------------------------
# Inject Movies, Actors, Directors, Genre

@transaction.atomic
def upsert_tmdb_movie(tmdb_id, cast_limit=12):
    data = get_movie_details(tmdb_id)

    release_date = data.get("release_date")
    year = None
    if release_date:
        try:
            year = datetime.strptime(release_date, "%Y-%m-%d").date().year
        except Exception:
            pass

    movie, _ = Movie.objects.update_or_create(
        tmdb_id=tmdb_id,
        defaults={
            "title":data.get("title"),
            "year": year,
            "overview": data.get("overview"),
            "avg_rating": data.get("vote_average"),
            "budget": data.get("budget"),
            "revenue": data.get("revenue"),
            "runtime": data.get("runtime"),
            "language": data.get("original_language"),
            "country": (
                data.get("production_countries")[0]["name"]
                if data.get("production_countries")
                else None
            ),
            "poster_url": IMG_BASE_W500 + data["poster_path"] if data.get("poster_path") else None,
        },
    )

    # --- Genres ---
    # simple + idempotent: wipe & re-add links for this movie
    MovieGenre.objects.filter(movie=movie).delete()
    for g in data.get("genres") or []:
        genre_obj, _ = Genre.objects.update_or_create(
            tmdb_id=g["id"],
            defaults={"name": g["name"]},
        )
        MovieGenre.objects.create(movie=movie,genre=genre_obj)

    credits = data.get("credits") or {}

    # --- Cast (Actors) ---
    MovieCast.objects.filter(movie=movie).delete()

    for c in (credits.get("cast") or [])[:cast_limit]:
        person_obj, _ = Person.objects.update_or_create(
            tmdb_id=c["id"],
            defaults={
                "name":c.get("name") or c.get("original_name") or "Unknown",
                "profile_url":(
                    IMG_PROFILE_W185 + c["profile_path"] if c.get("profile_path") else None
                ),
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
        person_obj, _ = Person.objects.update_or_create(
            tmdb_id=cr["id"],
            defaults={
                "name":cr.get("name") or cr.get("original_name") or "Unknown",
                "profile_url":(
                    IMG_PROFILE_W185 + cr["profile_path"] if cr.get("profile_path") else None
                ),
            }
        )

        MovieCrew.objects.create(
            movie=movie,
            person=person_obj,
            job="Director",
            department=cr.get("department"),
        )

@transaction.atomic
def attach_tmdb_to_movie(*, movie_id: int, tmdb_id: int, cast_limit: int=12) -> Movie:
    """
    Attach TMDB id to existing movie row and enrich it with TMDB fields + credits.
    """

    # lock row to avoid race conditions
    movie = Movie.objects.select_for_update().get(id=movie_id)

    # if movie alr has tmdb id -> must match
    if movie.tmdb_id and int(movie.tmdb_id) != int(tmdb_id):
        raise ValidationError(f"tmdb_id={tmdb_id} is already attached to movie id={movie.tmdb_id}, cannot attach tmdb_id = {tmdb_id}")

    # if another movie alr has this tmdb_id don't dupe
    existing = Movie.objects.filter(tmdb_id = tmdb_id).exclude(id=movie_id).first()
    if existing:
        raise ValidationError(
            f"tmdb_id={tmdb_id} is already attached to Movie Id={existing.id}"
            f"Decide whether to merge or pick the correct row."
        )
    data = get_movie_details(tmdb_id)
    release_date = data.get("release_date")
    year = None
    if release_date:
        try:
            year = datetime.strptime(release_date, "%Y-%m-%d").date().year
        except Exception:
            year = None

    # enrich fields (don't wipe letterboxd uri; just add tmdb info)
    movie.tmdb_id = tmdb_id
    movie.title = data.get("title") or movie.title
    movie.year = year or movie.year
    movie.overview = data.get("overview") or movie.overview
    movie.avg_rating = data.get("vote_average") if data.get("vote_average") is not None else movie.avg_rating
    movie.budget = data.get("budget") if data.get("budget") is not None else movie.budget
    movie.revenue = data.get("revenue") if data.get("revenue") is not None else movie.revenue
    movie.runtime = data.get("runtime") if data.get("runtime") is not None else movie.runtime
    movie.language = data.get("original_language") or movie.language

    prod_countries = data.get("production_countries") or []
    movie.country = (prod_countries[0].get("name") if prod_countries else movie.country)

    poster_path = data.get("poster_path")
    if poster_path:
        movie.poster_url = IMG_BASE_W500 + poster_path

    movie.save()

    # --- Genres ---
    # simple + idempotent: wipe & re-add links for this movie
    MovieGenre.objects.filter(movie=movie).delete()
    for g in data.get("genres") or []:
        genre_obj, _ = Genre.objects.update_or_create(
            tmdb_id=g["id"],
            defaults={"name": g["name"]},
        )
        MovieGenre.objects.create(movie=movie,genre=genre_obj)

    credits = data.get("credits") or {}

    # --- Cast (Actors) ---
    MovieCast.objects.filter(movie=movie).delete()

    for c in (credits.get("cast") or [])[:cast_limit]:
        person_obj, _ = Person.objects.update_or_create(
            tmdb_id=c["id"],
            defaults={
                "name":c.get("name") or c.get("original_name") or "Unknown",
                "profile_url":(
                    IMG_PROFILE_W185 + c["profile_path"] if c.get("profile_path") else None
                ),
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
        person_obj, _ = Person.objects.update_or_create(
            tmdb_id=cr["id"],
            defaults={
                "name":cr.get("name") or cr.get("original_name") or "Unknown",
                "profile_url":(
                    IMG_PROFILE_W185 + cr["profile_path"] if cr.get("profile_path") else None
                ),
            }
        )

        MovieCrew.objects.create(
            movie=movie,
            person=person_obj,
            job="Director",
            department=cr.get("department"),
        )

    return movie