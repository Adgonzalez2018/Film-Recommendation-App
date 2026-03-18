# Service Py File for (letterboxd_views)
# Import Page (LetterboxdConnect) 
# & Profile Page
import csv
import io
from datetime import date, datetime
from email.utils import parsedate_to_datetime

from ..models import MovieUser
from ..utils.unifiedImportHelper import (
    upsertMovie, 
    needToEnrich, 
    upsert_movieuser_snapshot, 
    upsert_watch_event,
)

from ..utils.dates import parse_iso_date

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

    def iter_csv(file_obj):
        file_obj.file.seek(0)
        text = io.TextIOWrapper(file_obj.file, encoding="utf-8-sig")
        return csv.DictReader(text)
        
    def parse_float(s):
        s = (s or "").strip()
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None


    # ---------- per-csv handlers ----------
    def import_watched_csv(file_obj):
        nonlocal events_created, movies_created, movies_matched

        for row in iter_csv(file_obj):
            name = row.get("Name")
            year = row.get("Year")
            uri = row.get("Letterboxd URI")

            movie, was_created, was_matched = upsertMovie(name, year, uri)
            if not movie:
                continue
            if was_created:
                movies_created += 1
            if was_matched: 
                movies_matched += 1
            if needToEnrich(movie):
                movies_to_enrich.add(movie.id)

            posted_date = parse_iso_date(row.get("Date"))
            existing_mu = MovieUser.objects.filter(user=user, movie=movie).first()
            # keep the latest watched date on the snapshot
            if posted_date:
                _, created = upsert_watch_event(
                    user=user,
                    movie=movie,
                    posted_date=posted_date,
                    watched_date=None,
                    rewatch=False,
                    source="manual",
                    entry_url=movie.letterboxd_uri,
                )
                if created:
                    events_created += 1
            updates = {
            "watch_status": "Watched",
            "in_watchlist": False,
            }

            if posted_date:
                updates["watched_date"] = posted_date
                if existing_mu and existing_mu.watched_date and posted_date > existing_mu.watched_date:
                    updates["rewatch"] = True
            
            _, created_mu, changed_mu = upsert_movieuser_snapshot(user, movie, updates)
            if created_mu:
                rel_created += 1
            elif changed_mu:
                rel_updated += 1

    def import_reviews_csv(file_obj):
        nonlocal events_created, movies_created, movies_matched
        for row in iter_csv(file_obj):
            name = row.get("Name")
            year = row.get("Year")
            uri = row.get("Letterboxd URI")

            movie, was_created, was_matched = upsertMovie(name, year, uri)
            if not movie:
                continue
            if was_created:
                movies_created += 1
            if was_matched:
                movies_matched += 1
            if needToEnrich(movie):
                movies_to_enrich.add(movie.id)

            posted_date = parse_iso_date(row.get("Date")) # CSV "Date" col
            watched_date = parse_iso_date(row.get("Watched Date"))
            rating = parse_float(row.get("Rating"))
            review_text = (row.get("Review") or "").strip()
            rewatch_flag = ((row.get("Rewatch") or "").strip().lower()=="yes")

            # Create WatchEvent 
            event_posted = posted_date or watched_date
            if event_posted:
                _, created = upsert_watch_event(
                    user=user,
                    movie=movie,
                    posted_date=event_posted,
                    watched_date=watched_date,
                    rewatch=rewatch_flag,
                    source="manual",
                    entry_url=movie.letterboxd_uri,
                )
                if created:
                    events_created += 1

            updates = {
            "watch_status": "Watched",
            "in_watchlist": False,
            }
            # keep latest watched date on snapshot
            snap_date = watched_date or posted_date
            if snap_date:
                updates["watched_date"] = snap_date
            if rewatch_flag:
                updates["rewatch"] = True
            if rating is not None:
                updates["rating"] = rating
            if review_text:
                updates["review"] = review_text
            _, created_mu, changed_mu = upsert_movieuser_snapshot(user, movie, updates)
            if created_mu:
                rel_created += 1
            if changed_mu:
                rel_updated += 1

    def import_watchlist_csv(file_obj):
        nonlocal movies_created, movies_matched

        for row in iter_csv(file_obj):
            name = row.get("Name")
            year = row.get("Year")
            uri = row.get("Letterboxd URI")

            movie, was_created, was_matched = upsertMovie(name, year, uri)
            if not movie:
                continue
            if was_created:
                movies_created += 1
            if was_matched:
                movies_matched += 1
            if needToEnrich(movie):
                movies_to_enrich.add(movie.id)

            existing_mu = MovieUser.objects.filter(user=user, movie=movie).first()
            updates = {"in_watchlist": True}
            # Don't clobber watched entries
            if not existing_mu or (
                not existing_mu.watched_date and existing_mu.watch_status != "Watched"
            ):
                updates["watch_status"] = "Want to Watch"
            _, created_mu, changed_mu = upsert_movieuser_snapshot(user, movie, updates)
            if created_mu:
                rel_created += 1
            if changed_mu:
                rel_updated += 1

    def import_films_likes_csv(file_obj):
        nonlocal movies_created, movies_matched
        for row in iter_csv(file_obj):
            name = row.get("Name")
            year = row.get("Year")
            uri = row.get("Letterboxd URI")

            movie, was_created, was_matched = upsertMovie(name, year, uri)
            if not movie:
                continue
            if was_created:
                movies_created += 1
            if was_matched: 
                movies_matched += 1
            if needToEnrich(movie):
                movies_to_enrich.add(movie.id)

            _, created_mu, changed_mu = upsert_movieuser_snapshot(user, movie, {"liked": True})
            if created_mu:
                rel_created += 1
            if changed_mu:
                rel_updated += 1

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
        