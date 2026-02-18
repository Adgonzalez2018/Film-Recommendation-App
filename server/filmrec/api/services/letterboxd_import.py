import csv
import io
from datetime import date
from django.db import transaction

from ..models import Movie, MovieUser
from ..utils.letterboxd import normalize_letterboxd_uri
from ..utils.dates import parse_iso_date


def run_letterboxd_import(*, user, reviews_file=None, watchlist_file=None, films_file=None):
    """
    Business-logic import. No DRF here.

    Returns counters dict.
    """
    movies_created = 0
    movies_matched = 0
    rel_created = 0
    rel_updated = 0

    def iter_csv(file_obj):
        text = io.TextIOWrapper(file_obj.file, encoding="utf-8-sig")
        return csv.DictReader(text)

    def year_to_date(year_str):
        try:
            y = int(year_str) if year_str else None
            return date(y, 1, 1) if y else None
        except Exception:
            return None

    def parse_float(s):
        s = (s or "").strip()
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    def upsert_movie(name, year, uri):
        nonlocal movies_created, movies_matched

        uri = normalize_letterboxd_uri(uri)
        if not uri:
            return None

        movie = Movie.objects.filter(letterboxd_uri=uri).first()
        if movie:
            movies_matched += 1
            if (not movie.title) and name:
                movie.title = (name or "").strip()[:255]
                movie.save(update_fields=["title"])
            return movie

        movie = Movie.objects.create(
            title=((name or "").strip()[:255] or "Unknown"),
            release_date=year_to_date(year),
            letterboxd_uri=uri,
        )
        movies_created += 1
        return movie

    def get_or_create_mu(movie):
        nonlocal rel_created
        mu, created = MovieUser.objects.get_or_create(user=user, movie=movie)
        if created:
            rel_created += 1
        return mu

    def apply_update(mu: MovieUser, updates: dict):
        nonlocal rel_updated
        changed = False
        for k, v in updates.items():
            if getattr(mu, k) != v:
                setattr(mu, k, v)
                changed = True
        if changed:
            mu.save()
            rel_updated += 1

    # ---------- per-csv handlers ----------
    def import_reviews_csv(file_obj):
        for row in iter_csv(file_obj):
            name = row.get("Name")
            year = row.get("Year")
            uri = row.get("Letterboxd URI")

            movie = upsert_movie(name, year, uri)
            if not movie:
                continue

            mu = get_or_create_mu(movie)

            watched_date = parse_iso_date(row.get("Watched Date"))
            rating = parse_float(row.get("Rating"))
            review_text = (row.get("Review") or "").strip()

            updates = {"watch_status": "Watched"}
            if watched_date:
                updates["watched_date"] = watched_date
            if rating is not None:
                updates["rating"] = rating
            if review_text:
                updates["review"] = review_text

            apply_update(mu, updates)

    def import_watchlist_csv(file_obj):
        for row in iter_csv(file_obj):
            name = row.get("Name")
            year = row.get("Year")
            uri = row.get("Letterboxd URI")

            movie = upsert_movie(name, year, uri)
            if not movie:
                continue

            mu = get_or_create_mu(movie)

            updates = {"in_watchlist": True}

            # Don't clobber watched entries
            if not mu.watched_date and mu.watch_status != "Watched":
                updates["watch_status"] = "Want to Watch"

            apply_update(mu, updates)

    def import_films_likes_csv(file_obj):
        for row in iter_csv(file_obj):
            name = row.get("Name")
            year = row.get("Year")
            uri = row.get("Letterboxd URI")

            movie = upsert_movie(name, year, uri)
            if not movie:
                continue

            mu = get_or_create_mu(movie)
            apply_update(mu, {"liked": True})

    # ---------- run import ----------
    with transaction.atomic():
        if reviews_file:
            import_reviews_csv(reviews_file)
        if watchlist_file:
            import_watchlist_csv(watchlist_file)
        if films_file:
            import_films_likes_csv(films_file)

    return {
        "movies_created": movies_created,
        "movies_matched": movies_matched,
        "relationships_created": rel_created,
        "relationships_updated": rel_updated,
    }
