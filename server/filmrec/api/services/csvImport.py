# api/services/csvImport.py
# Service Py File for (import_views)
# Import Page (Used to be LetterboxdConnect) 
# & Profile Page
import csv
import io
from collections import defaultdict

from ..models import MovieUser, WatchEvent
from ..utils.unifiedImportHelper import (
    makeWatchKey,
    resolve_movies_bulk,
    resolve_movie_one,
    normalize_movie_candidate,
    needToEnrich
)
from ..utils.dates import parse_iso_date

def run_letterboxd_import(*, user, watched_file=None, reviews_file=None, watchlist_file=None, films_file=None):
    """
    CSV import Pipeline:
        - never attach user data to weak placeholder Movie rows
        - prefer bulk resolution for speed, but fall bac kt orws
        - dedupe watch events soruce-agnostically by (user, canonical movie uri, date)
        - collapse all csv rows into one final Movieuser snapshot per movie
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
        
    # For User's Rating
    def parse_float(s):
        s = (s or "").strip()
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    def parse_rows():
        # Parse all csv rows first
        # watched -> reviews -> watchlist -> films/likes
        rows = []

        if watched_file:
            for row in iter_csv(watched_file):
                rows.append({
                    "kind": "watched",
                    "title": row.get("Name"),
                    "year": row.get("Year"),
                    "uri": row.get("Letterboxd URI"),
                    "posted_date": parse_iso_date(row.get("Date")),
                    "watched_date": None,
                    "rating": None,
                    "review": "",
                    "rewatch": False,
                    "liked": False,
                    "in_watchlist": False,
                })

        if reviews_file:
            for row in iter_csv(reviews_file):
                rows.append({
                    "kind": "review",
                    "title": row.get("Name"),
                    "year": row.get("Year"),
                    "uri": row.get("Letterboxd URI"),
                    "posted_date": parse_iso_date(row.get("Date")),
                    "watched_date": parse_iso_date(row.get("Watched Date")),
                    "rating": parse_float(row.get("Rating")),
                    "review": (row.get("Review") or "").strip(),
                    "rewatch": ((row.get("Rewatch") or "").strip().lower() == "yes"),
                    "liked": False,
                    "in_watchlist": False,
                })

        if watchlist_file:
            for row in iter_csv(watchlist_file):
                rows.append({
                    "kind": "watchlist",
                    "title": row.get("Name"),
                    "year": row.get("Year"),
                    "uri": row.get("Letterboxd URI"),
                    "posted_date": None,
                    "watched_date": None,
                    "rating": None,
                    "review": "",
                    "rewatch": False,
                    "liked": False,
                    "in_watchlist": True,
                })

        if films_file:
            for row in iter_csv(films_file):
                rows.append({
                    "kind": "likes",
                    "title": row.get("Name"),
                    "year": row.get("Year"),
                    "uri": row.get("Letterboxd URI"),
                    "posted_date": None,
                    "watched_date": None,
                    "rating": None,
                    "review": "",
                    "rewatch": False,
                    "liked": True,
                    "in_watchlist": False,
                })

        return rows

    def apply_update(state, updates):
        changed = False
        for k, v in updates.items():
            if state.get(k) != v:
                state[k] = v
                changed = True
        return changed
    
    def is_strong_movie_identity(movie):
        if not movie or not getattr(movie,"id", None):
            return False
        return bool(
            getattr(movie, "tmdb_id", None) is not None
            or getattr(movie, "letterboxd_uri", None)
            or getattr(movie, "year", None) is not None
        )
    
    rows = parse_rows()
    if not rows:
        return {
            "movies_created": 0,
            "movies_matched": 0,
            "events_created": 0,
            "rel_created": 0,
            "rel_updated": 0,
            "movies_to_enrich": [],
        }
    
    candidates = [
        normalize_movie_candidate(
            title=r["title"],
            year=r["year"],
            uri=r["uri"],
            tmdb_id=None,
        )
        for r in rows
    ]

    # First pass: bulk resolution for speed
    bulk_resolved = resolve_movies_bulk(candidates)

    for r, cand, movie in zip(rows, candidates, bulk_resolved):
        final_movie = movie
        weak_movie = (
            final_movie is None
            or final_movie.id is None
            or not is_strong_movie_identity(final_movie)
        )

        if weak_movie:
            final_movie, created, _ = resolve_movie_one(
                title=cand.title,
                year=cand.year,
                uri=cand.raw_uri,
                tmdb_id=cand.tmdb_id,
            )
            if created:
                movies_created += 1
        if not final_movie or not final_movie.id:
            continue

        if not is_strong_movie_identity(final_movie):
            # last guard: do not persisst user data
            continue

        r["_movie"] = final_movie
        movies_matched += 1
        if needToEnrich(final_movie):
            movies_to_enrich.add(final_movie.id)

    movie_ids = list({r["_movie"].id for r in rows if r.get("_movie")})
    if not movie_ids:
        return {
            "movies_created": movies_created,
            "movies_matched": 0,
            "events_created": 0,
            "rel_created": 0,
            "rel_updated": 0,
            "movies_to_enrich": list(movies_to_enrich),
        }
    
    existing_mu_qs = MovieUser.objects.filter(user=user,movie_id__in=movie_ids)
    existing_mu_map = {mu.movie_id: mu for mu in existing_mu_qs}

    # build all event keys first, then bulk fetch existing events
    desired_event_rows = []
    desired_event_keys = set()

    for r in rows:
        movie = r.get("_movie")
        if not movie:
            continue
        
        if r["kind"] == "watched":
            event_posted = r["posted_date"]
            if event_posted and movie.letterboxd_uri:
                event_key = makeWatchKey(user.id, movie.letterboxd_uri, event_posted)
                desired_event_rows.append({
                    "event_key": event_key,
                    "movie": movie,
                    "posted_date": r["posted_date"],
                    "watched_date": None,
                    "rewatch": False,
                    "source": "csv",
                    "entry_url": movie.letterboxd_uri,
                })
                desired_event_keys.add(event_key)

        elif r["kind"] == "review":
            event_posted = r["posted_date"] or r["watched_date"]
            if event_posted and movie.letterboxd_uri:
                event_key = makeWatchKey(user.id, movie.letterboxd_uri, event_posted)
                desired_event_rows.append({
                    "event_key": event_key,
                    "movie": movie,
                    "posted_date": event_posted,
                    "watched_date": r["watched_date"],
                    "rewatch": r["rewatch"],
                    "source": "csv",
                    "entry_url": movie.letterboxd_uri,
                })
                desired_event_keys.add(event_key)

    existing_event_keys = set(
        WatchEvent.objects.filter(user=user, event_key__in=desired_event_keys)
        .values_list("event_key", flat=True)
    )

    new_event_objects = []
    staged_event_keys = set()

    for e in desired_event_rows:
        if e["event_key"] in existing_event_keys or e["event_key"] in staged_event_keys:
            continue
        new_event_objects.append(
        WatchEvent(
                user=user,
                movie=e["movie"],
                posted_date=e["posted_date"],
                watched_date=e["watched_date"],
                rewatch=e["rewatch"],
                source=e["source"],
                entry_url=e["entry_url"],
                event_key=e["event_key"],
            )
        )
        staged_event_keys.add(e["event_key"])

    if new_event_objects:
        WatchEvent.objects.bulk_create(new_event_objects, ignore_conflicts=True)
        events_created = len(new_event_objects)

    # aggregate one final movieuser state per movie, in the same row order as before
    snapshot_state = {}
    snapshot_changed = set()

    def base_state_for_movie(movie_id):
        mu = existing_mu_map.get(movie_id)
        if mu:
            return {
                "rating": mu.rating,
                "review": mu.review,
                "watch_status": mu.watch_status,
                "watched_date": mu.watched_date,
                "liked": mu.liked,
                "in_watchlist": mu.in_watchlist,
                "rewatch": mu.rewatch,
                "_exists": True,
            }
        return {
            "rating": None,
            "review": None,
            "watch_status": "Watched",
            "watched_date": None,
            "liked": False,
            "in_watchlist": False,
            "rewatch": False,
            "_exists": False,
        }

    for r in rows:
        movie = r.get("_movie")
        if not movie:
            continue
        
        movie_id = movie.id
        if movie_id not in snapshot_state:
            snapshot_state[movie_id] = base_state_for_movie(movie_id)
        
        state = snapshot_state[movie_id]
        before = dict(state)
        if r["kind"] == "watched":
            updates = {
                "watch_status": "Watched",
                "in_watchlist": False,
            }

            posted_date = r["posted_date"]
            if posted_date:
                updates["watched_date"] = posted_date
                current_watched = state.get("watched_date")
                if current_watched and posted_date > current_watched:
                    updates["rewatch"] = True
            apply_update(state, updates)
                    
        elif r["kind"] == "review":
            updates = {
                "watch_status": "Watched",
                "in_watchlist": False,
            }

            snap_date = r["watched_date"] or r["posted_date"]
            if snap_date:
                updates["watched_date"] = snap_date
            if r["rewatch"]:
                updates["rewatch"] = True
            if r["rating"] is not None:
                updates["rating"] = r["rating"]
            if r["review"]:
                updates["review"] = r["review"]
            
            apply_update(state, updates)

        elif r["kind"] == "watchlist":
            updates = {"in_watchlist": True}

            if not state.get("watched_date") and state.get("watch_status") != "Watched":
                updates["watch_status"] = "Want to Watch"
            apply_update(state, updates)

        elif r["kind"] == "likes":
            apply_update(state, {"liked": True})

        if state != before:
            snapshot_changed.add(movie_id)

    new_mu_objects = []
    update_mu_objects = []
    for movie_id, state in snapshot_state.items():
        if not state["_exists"]:
            new_mu_objects.append(
                MovieUser(
                    user=user,
                    movie_id=movie_id,
                    rating=state["rating"],
                    review=state["review"],
                    watch_status=state["watch_status"],
                    watched_date=state["watched_date"],
                    liked=state["liked"],
                    in_watchlist=state["in_watchlist"],
                    rewatch=state["rewatch"],
                )
            )
            
        elif movie_id in snapshot_changed:
            mu = existing_mu_map[movie_id]
            mu.rating = state["rating"]
            mu.review = state["review"]
            mu.watch_status = state["watch_status"]
            mu.watched_date = state["watched_date"]
            mu.liked = state["liked"]
            mu.in_watchlist = state["in_watchlist"]
            mu.rewatch = state["rewatch"]
            update_mu_objects.append(mu)
    
    if new_mu_objects:
        MovieUser.objects.bulk_create(new_mu_objects, ignore_conflicts=True)
        rel_created = len(new_mu_objects)
    
    if update_mu_objects:
        MovieUser.objects.bulk_update(
            update_mu_objects,
            ["rating","review","watch_status","watched_date", "liked", "in_watchlist", "rewatch"],
        )
        rel_updated = len(update_mu_objects)

    return {
        "movies_created": movies_created,
        "movies_matched": movies_matched,
        "events_created": events_created,
        "rel_created": rel_created,
        "rel_updated": rel_updated,
        "movies_to_enrich": list(movies_to_enrich),
    }

