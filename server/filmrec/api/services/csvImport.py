# Service Py File for (letterboxd_views)
# Import Page (LetterboxdConnect) 
# & Profile Page
import csv
import io
from datetime import date, datetime
from email.utils import parsedate_to_datetime

from django.db.models import Q

from ..models import MovieUser, Movie, WatchEvent
from ..utils.unifiedImportHelper import (
    normalize_letterboxd_uri, 
    needToEnrich, 
    upsert_movieuser_snapshot, 
    upsert_watch_event,
    clean_letterboxd_title,
    parse_year,
    makeEventKey
)

from ..utils.dates import parse_iso_date

def run_letterboxd_import(*, user, watched_file=None, reviews_file=None, watchlist_file=None, films_file=None):
    """
    Optimized business logic import

    same return shape as before
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
                    "uri": normalize_letterboxd_uri(row.get("Letterboxd URI")),
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
                    "uri": normalize_letterboxd_uri(row.get("Letterboxd URI")),
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
                    "uri": normalize_letterboxd_uri(row.get("Letterboxd URI")),
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
                    "uri": normalize_letterboxd_uri(row.get("Letterboxd URI")),
                    "posted_date": None,
                    "watched_date": None,
                    "rating": None,
                    "review": "",
                    "rewatch": False,
                    "liked": True,
                    "in_watchlist": False,
                })

        return rows

    def resolve_movies(rows):
        # Bulk resolve/create movies by:
        # letterboxd uri
        # fallback title + year
        nonlocal movies_created, movies_matched
        uris = {r["uri"] for r in rows if r["uri"]}
        pair_rows = []
        titles = set()
        years = set()

        for r in rows:
            title = clean_letterboxd_title(r["title"])
            year = parse_year(r["year"])
            r["_clean_title_"] = title
            r["_parsed_year_"] = year
            if title and year is not None:
                pair_rows.append((title, year))
                titles.add(title)
                years.add(year)

        existing_by_uri = {}
        if uris:
            for m in Movie.objects.filter(letterboxd_uri__in=uris):
                existing_by_uri[m.letterboxd_uri] = m

        existing_by_pair = {}
        if titles and years:
            for m in Movie.objects.filter(title__in=titles, year__in=years):
                existing_by_pair[(m.title, m.year)] = m
        
        
        movies_to_patch = {}
        create_candidates = {}
        row_movie_keys = []

        def row_key_for_create(r):
            if r["uri"]:
                return ("uri", r["uri"])
            return ("pai", r["_clean_title_"], r["_parsed_year"])
        
        # first pass: resolve existing or stage new creations
        for r in rows:
            movie = None
            uri = r["uri"]
            pair = (r["_clean_title"], r["_parsed_year"])

            if uri and uri in existing_by_uri:
                movie = existing_by_uri[uri]
            elif pair[0] and pair[1] is not None and pair in existing_by_pair:
                movie = existing_by_pair[pair]

            if movie:
                row_movie_keys.append(("existing", movie))
                patch = movies_to_patch.get(movie.id)
                if patch is None:
                    patch = {"movie": movie, "changed": False}
                    movies_to_patch[movie.id] = patch

                if not movie.letterboxd_uri and uri:
                    movie.letterboxd_uri = uri
                    patch["changed"] = True
                if movie.title == "Unknown" and r["_clean_title"]:
                    movie.title = r["_clean_title"]
                    patch["changed"] = True
                if movie.year is None and r["_parsed_year"] is not None:
                    movie.year = r["_parsed_year"]
                    patch["changed"] = True
            else:
                create_key = row_key_for_create(r)
                if create_key not in create_candidates:
                    create_candidates[create_key] = Movie(
                        title=r["_clean_title"],
                        year=r["_parsed_year"],
                        letterboxd_ur=r["uri"],
                        enrichment_status="pending",
                    )
                row_movie_keys.append(("created_or_fetch", create_key))

            # Patch existing movies in bulk
            patch_list = [v["movie"] for v in movies_to_patch.values() if v["changed"]]
            if patch_list:
                Movie.objects.bulk_update(patch_list, ["letterboxd_uri", "title", "year"])

            # bulk create missing movies
            if create_candidates:
                Movie.objects.bulk_create(list(create_candidates.values()), ignore_conflicts=True)

            # Re-fetch after create/patch
            all_by_uri = {}
            if uris:
                for m in Movie.objects.filter(letterboxd_uri__in=uris):
                    all_by_uri[m.letterboxd_uri] = m
            
            all_by_pair = {}
            if titles and years:
                for m in Movie.objects.filter(title__in=titles, year__in=years):
                    all_by_pair[(m.title,m.year)] = m

            # Final row -> movie resolution and counters
            seen_created_keys = set()
            for idx, r in enumerate(rows):
                marker, payload = row_movie_keys[idx]

                if marker == "existing":
                    movie = payload
                    movies_matched += 1
                else:
                    create_key = payload
                    movie = None

                    if create_key[0] == "uri":
                        movie = all_by_uri.get(create_key[1])
                    else:
                        movie = all_by_pair.get((create_key[1], create_key[2]))

                    if not movie:
                        # very defensive fallback
                        movie = Movie.objects.create(
                            title=r["_clean_title"],
                            year=r["_parsed_year"],
                            letterboxd_ur=r["uri"],
                            enrichment_status="pending",
                        )
                    
                    if create_key not in seen_created_keys:
                        movies_created += 1
                        seen_created_keys.add(create_key)
                    else:
                        movies_matched += 1
                
                r["_movie"] = movie

                if needToEnrich(movie):
                    movies_to_enrich.add(movie.id)

        def apply_updates(state, updates):
            changed = False
            for k, v in updates.items():
                if state.get(k) != v:
                    state[k] = v
                    changed = True
            return changed
        
        rows = parse_rows()
        if not rows:
            return {
                "movies_created": 0,
                "movies_matched": 0,
                "events_created": 0,
                "rel_created": 0,
                "rel_matched": 0,
                "movies_to_enrich": [],
            }
        
        resolve_movies(rows)

        movie_ids = {r["_movie"].id for r in rows if r.get("_movie")}

        existing_mu_qs = MovieUser.objects.filter(user=user,movie_id__in=movie_ids)
        existing_mu_map = {mu.movie_id: mu for mu in existing_mu_qs}

        # build all event keys first, then bulk fetch existing events
        desired_event_rows = []
        desired_event_keys = set()

        for r in rows:
            movie = r["_movie"]

            if r["kind"] == "watched":
                if r["posted_date"] and movie.letterboxd_uri:
                    event_key = makeEventKey(user.id, movie.letterboxd_uri, r["posted_date"])
                    desired_event_rows.append({
                        "event_key": event_key,
                        "movie_id": movie.id,
                        "movie": movie,
                        "posted_date": r["posted_date"],
                        "watched_date": None,
                        "rewatch": False,
                        "source": "manual",
                        "entry_url": movie.letterboxd_uri,
                    })
                    desired_event_keys.add(event_key)

            elif r["kind"] == "review":
                event_posted = r["posted_date"] or r["watched_date"]
                if r["posted_date"] and movie.letterboxd_uri:
                    event_key = makeEventKey(user.id, movie.letterboxd_uri, r["posted_date"])
                    desired_event_rows.append({
                        "event_key": event_key,
                        "movie_id": movie.id,
                        "movie": movie,
                        "posted_date": event_posted,
                        "watched_date": r["watched_date"],
                        "rewatch": r["rewatch"],
                        "source": "manual",
                        "entry_url": movie.letterboxd_uri,
                    })
                    desired_event_keys.add(event_key)

        existing_event_keys = set(
            WatchEvent.objects.filter(user=user,event_key__in=desired_event_keys)
            .values_list("event_key", flat=True)
        )
    
        new_event_objects = []
        staged_event_keys = set()

        for e in desired_event_rows:
            if e["event_key"] in existing_event_keys or e["event_keys"] in staged_event_keys:
                continue
            new_event_objects.append(
                WatchEvent(
                    user=user,
                    movie=e["movie"],
                    posted_date=e["posted_date"],
                    watched_date=e["watched_date"],
                    rewatch=e["rewatch"],
                    source=e["rewatch"],
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
            movie = r["movie"]
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
                apply_updates(state, updates)
                        
            elif r["kind"] == "review":
                updates = {
                    "watch_status": "Watched",
                    "in_watchlist": False,
                }

                snap_date = r["posted_date"] or r["watched_date"]
                if snap_date:
                    updates["watched_date"] = snap_date
                if r["rewatch"]:
                    updates["rewatch"] = True
                if r["rating"] is not None:
                    updates["rating"] = r["rating"]
                if r["review"]:
                    updates["review"] = r["review"]
                
                apply_updates(state, updates)

            elif r["kind"] == "watchlist":
                updates = {"in_watchlist": True}

                if not state.get("watched_date") and state.get("watch_status") != "Watched":
                    updates["watch_status"] = "Want to Watch"
                apply_updates(state, updates)

            elif r["kind"] == "likes":
                apply_updates(state, {"liked": True})

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
            MovieUser.objects.bulk_create(
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
        