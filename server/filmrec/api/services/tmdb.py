import os
import requests

from datetime import datetime
from ..models import Movie
from django.db import transaction

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
    return tmdb_get(f"/movie/{tmdb_id}")

# ------------------------
# Inject Movies, Actors, Directors, Genre

@transaction.atomic
def upsert_tmdb_movie(tmdb_id, cast_limit=12):
    data = get_movie_details(tmdb_id)

    release_date = data.get("release_date")
    parsed_date = None
    year = None
    if release_date:
        try:
            parsed_date = datetime.strptime(release_date, "%Y-%m-%d").date()
            year = parsed_date.year
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
                "name":c.get("name") or c.get("original_name") or "Unknown",
                "profile_url":(
                    IMG_PROFILE_W185 + c["profile_path"] if c.get("profile_path") else None
                ),
            }
        )

        MovieCrew.objects.create(
            movie=movie,
            person=person_obj,
            job="Director",
            department=cr.get("department"),
        )

