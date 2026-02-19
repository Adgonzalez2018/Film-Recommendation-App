import csv
import io
import re
from datetime import date, datetime

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

# RSS Helper Function
def _build_letterboxd_rss_url(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    
    # if they paste "letterboxd.com/username" without scheme
    if s.startswith("letterboxd.com/"):
        s = "https://" + s
    
    # Full URL with scheme
    if s.startsqwith("http://") or s.startswith("https://"):
        # if it's already an rss URL, keep it
        if s.rstrip("/").endswith("/rss/"):
            return s.rstrip("/") + "/"
        # if it's a profile URL like httsp://letterboxd.com/<user>/
        m = re.match(r"^https?://letterboxd\.com/([^/]+)/?$", s.rstrip("/"))
        if m:
            username = m.group(2)
            return f"https://letterboxd.com/{username}/rss/"
        # unnknown URL Format
        return ""
    
    # otherwise treat as username
    username = s.strip("/").replace(" ", "")
    if not username:
        return ""
    return f"https://letterboxd.com/{username}/rss/"

def _parse_published_date(entry) -> datetime | None:
    # feedparser gives published_parsed as a time.struct_time sometimes
    tp = getattr(entry, "published_parsed", None)
    if tp:
        try:
            return datetime(tp.tm_year, tp.tm_mon, tp.tm_mday, tp.tm_hour, tp.tm_min, tp.tm_sec)
        except Exception:
            return None
        
    # fallback: try published string
    pub = getattr(entry, "published", None)
    if pub:
        try:
            # very lose fallback; tighten later
            return datetime.fromisoformat(pub)
        except Exception:
            return None
        