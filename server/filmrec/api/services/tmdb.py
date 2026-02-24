import os
import requests

from datetime import datetime
from ..models import Movie

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"
IMG_BASE = "https://image.tmdb.org/t/p/w500"

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

def upsert_tmdb_movie(tmdb_id):
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
            "poster_url": IMG_BASE + data["poster_path"] if data.get("poster_path") else None,
        },
    )