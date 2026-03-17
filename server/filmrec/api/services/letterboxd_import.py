# Service Py File for (letterboxd_views)
# Import Page (LetterboxdConnect) 
# & Profile Page
import csv
import io
from datetime import date, datetime
from email.utils import parsedate_to_datetime


from django.db import transaction

from ..models import Movie, MovieUser, WatchEvent
from ..utils.letterboxd import normalize_letterboxd_uri
from ..utils.dates import parse_iso_date
from ..utils.rss import make_eventkey

MUST_ENRICH_STATUS = ["pending", "queued", "failed", "not_found"]
def run_letterboxd_import(*, user, watched_file=None, reviews_file=None, watchlist_file=None, films_file=None):
    """
    Business-logic import. No DRF here.

    Returns counters dict.
    """
    movies_to_enrich = set()
    events_created = 0 # go to watchEvent 
    movies_created = 0
    movies_matched = 0
    rel_created = 0
    rel_updated = 0

    def mark_for_enrichment(movie):
        if not movie:
            return
        if not movie.tmdb_id:
            movies_to_enrich.add(movie.id)
            return
        if getattr(movie, "enrichment_status", None) in MUST_ENRICH_STATUS:
            movies_to_enrich.add(movie.id)

    def iter_csv(file_obj):
        file_obj.file.seek(0)
        text = io.TextIOWrapper(file_obj.file, encoding="utf-8-sig")
        return csv.DictReader(text)

    def parse_year(year_str):
        try:
            y = int((year_str or "").strip())
            return y
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
        movie = None
        clean_name = ((name or "").strip()[:255] or "Unknown")
        y = parse_year(year)
        uri = normalize_letterboxd_uri(uri)

        # 1 Best local key: Letterboxd URI
        if uri:
            movie = Movie.objects.filter(letterboxd_uri=uri).first()

        # 2 Fallback local key: title + year
        if not movie and clean_name and y is not None:
            movie = Movie.objects.filter(title=clean_name, year=y).first()
            if movie:
                movies_matched += 1
                updates = {}
                if not movie.letterboxd_uri and uri:
                    updates["letterboxd_uri"] = uri
                if updates:
                    for k, v in updates.items():
                        setattr(movie, k,v)
                    movie.save(update_fields=list(updates.keys()))
                return movie
            
        # 3 If found locally, patch missing basics and return
        if movie:
            updates = {}
            # updates movie title if possible
            if (movie.title == "Unknown") and clean_name:
               updates["title"] = clean_name

            # update year if possible
            if movie.year is None and y is not None:
                updates["year"] = y
            
            # update letterboxd uri if possible
            if not movie.letterboxd_uri and uri:
                updates["letterboxd_uri"] = uri
            
            # Apply updates to movie record
            if updates:
                for k, v in updates.items():
                    setattr(movie, k,v)
                movie.save(update_fields=list(updates.keys()))
            return movie

        # 4 Last resort: create local minimal movie row
        movie = Movie.objects.create(
            title=clean_name,
            year=y,
            letterboxd_uri=uri,
            enrichment_status="pending",
        )
        movies_created += 1
        mark_for_enrichment(movie)
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
    def import_watched_csv(file_obj):
        nonlocal events_created

        for row in iter_csv(file_obj):
            name = row.get("Name")
            year = row.get("Year")
            uri = row.get("Letterboxd URI")

            movie = upsert_movie(name, year, uri)
            if not movie:
                continue
            mu = get_or_create_mu(movie)

            posted_date = parse_iso_date(row.get("Date"))
            updates = {"watch_status": "Watched"}

            # keep the latest watched date on the snapshot
            if posted_date:
                if mu.watched_date is not None and posted_date > mu.watched_date:
                    updates["rewatch"] = True
                updates["watched_date"] = posted_date

                event_key = make_eventkey(user.id, movie.letterboxd_uri, posted_date)
                _, created = WatchEvent.objects.get_or_create(
                    user=user,
                    event_key=event_key,
                    defaults={
                        "movie": movie,
                        "posted_date": posted_date,
                        "watched_date": None,
                        "rewatch": False,
                        "source": "csv",
                        "entry_url": movie.letterboxd_uri,
                    },
                )

                if created:
                    events_created += 1
        
            # a watched movie should not remain "want to watch"
            if mu.in_watchlist:
                updates["in_watchlist"] = False
                
            apply_update(mu, updates)

    def import_reviews_csv(file_obj):
        nonlocal events_created

        for row in iter_csv(file_obj):
            name = row.get("Name")
            year = row.get("Year")
            uri = row.get("Letterboxd URI")

            movie = upsert_movie(name, year, uri)
            if not movie:
                continue

            mu = get_or_create_mu(movie)
            posted_date = parse_iso_date(row.get("Date")) # CSV "Date" col
            watched_date = parse_iso_date(row.get("Watched Date"))
            rating = parse_float(row.get("Rating"))
            review_text = (row.get("Review") or "").strip()
            rewatch_flag = ((row.get("Rewatch") or "").strip().lower()=="yes")

            # Create WatchEvent 
            event_posted = posted_date or watched_date
            if event_posted:
                rewatch_flag = ((row.get("Rewatch") or "").strip().lower() == "yes")
                event_key = make_eventkey(user.id, movie.letterboxd_uri, event_posted)

                _, created = WatchEvent.objects.get_or_create(
                    user=user,
                    event_key=event_key,
                    defaults={
                        "movie": movie,
                        "posted_date": event_posted,
                        "watched_date": watched_date,
                        "rewatch": rewatch_flag,
                        "source": "csv",
                        "entry_url": movie.letterboxd_uri,
                    },
                )
                if created:
                    events_created += 1

            
            updates = {"watch_status": "Watched"}
            
            # keep latest watched date on snapshot
            snap_date = watched_date or posted_date
            if snap_date:
                if mu.watched_date is not None and snap_date > mu.watched_date:
                    updates["rewatch"] = True
                elif rewatch_flag:
                    updates["rewatch"] = True
                updates["watched_date"] = snap_date

            if rating is not None:
                updates["rating"] = rating
            if review_text:
                updates["review"] = review_text

            # reviewed movies should not remain in watchlist
            if mu.in_watchlist:
                updates["in_watchlist"] = False

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

    if watched_file:
        import_watched_csv(watched_file)
    if reviews_file:
        import_reviews_csv(reviews_file)
    if watchlist_file:
        import_watchlist_csv(watchlist_file)
    if films_file:
        import_films_likes_csv(films_file)

    return {
        "movies_created": movies_created,
        "movies_matched": movies_matched,
        "events_created": events_created,
        "rel_created": rel_created,
        "rel_updated": rel_updated,
        "movies_to_enrich": list(movies_to_enrich)
    }

def _parse_published_date(entry) -> date | None:
    """
    Returns a *date* for when the RSS entry was published/updated.
    prefer parsed structs if available; fall back to parsing string
    """

    tp = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if tp:
        try:
            return date(tp.tm_year, tp.tm_mon, tp.tm_mday)
        except Exception:
            return None
        
    # fallback: try published string
    s = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if not s:
        return None
    
    # RSS commonly uses RFC822
    try:
        return parsedate_to_datetime(s).date()
    except Exception:
        pass

    # last-ditch: iso like str
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None
        