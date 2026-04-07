from urllib.parse import urlparse
import re
from typing import Optional
import hashlib
from datetime import date
from dataclasses import dataclass

from django.db import IntegrityError, transaction

from api.models import Movie, WatchEvent, MovieUser, FilmBank

_USERNAME_RE = re.compile(r"^/([^/]+)/?$")
_USERNAME_SAFE_RE = re.compile(r"^[A-Za-z0-9_]+$")
MUST_ENRICH_STATUS = ["pending", "queued", "failed", "not_found"]

@dataclass
class NormalizedMovieCandidate:
    title: str
    year: Optional[int]
    raw_uri: Optional[str]
    canonical_uri: Optional[str]
    weak_uri: Optional[str]
    tmdb_id: Optional[int] = None

def normalize_letterboxd_movie_identity(uri: str | None) -> tuple[Optional[str], Optional[str]]:
    # Returns canonical uri and weak uri
    # canonical uri is stable film-page uri
    # weak uri are normalized uri that may be useful as a hint but shouldn't be part of movie's primary identity
    normalized = normalize_letterboxd_uri(uri)
    if not normalized:
        return None, None
    
    if "/film/" in normalized:
        return normalized, None
    
    return None, normalized

def normalize_movie_candidate(title, year, uri=None, tmdb_id=None) -> NormalizedMovieCandidate:
    clean_title = clean_letterboxd_title(title)
    parsed = parse_year(year)
    canonical_uri, weak_uri = normalize_letterboxd_movie_identity(uri)

    return NormalizedMovieCandidate(
        title=clean_title,
        year=parsed,
        raw_uri=normalize_letterboxd_uri(uri),
        canonical_uri=canonical_uri,
        weak_uri=weak_uri,
        tmdb_id=tmdb_id,
    )

def patch_movie_from_candidate(movie: Movie, cand: NormalizedMovieCandidate) -> bool:
    changed = False

    if movie.tmdb_id is None and cand.tmdb_id is not None:
        movie.tmdb_id = cand.tmdb_id
        changed = True

    if not movie.letterboxd_uri and cand.canonical_uri:
        movie.letterboxd_uri = cand.canonical_uri
        changed = True
    
    if (not movie.title or movie.title == "Unknown") and cand.title:
        movie.title = cand.title
        changed = True

    if movie.year is None and cand.year is not None:
        movie.year = cand.year
        changed = True

    return changed

def choose_existing_movie_one(cand: NormalizedMovieCandidate) -> Optional[Movie]:
    # Robust single-row lookup policy
    # 1. tmdb id
    # 2. canonical film uri
    # 3. exact title/year
    # 4. weak uri only as a last resort

    if cand.tmdb_id is not None:
        movie = Movie.objects.filter(tmdb_id=cand.tmdb_id).first()
        if movie:
            return movie

    if cand.canonical_uri:
        movie = Movie.objects.filter(letterboxd_uri=cand.canonical_uri).first()
        if movie:
            return movie

    if cand.title and cand.year is not None:
        movie = Movie.objects.filter(title=cand.title, year=cand.year).first()
        if movie:
            return movie

    if cand.weak_uri:
        movie = Movie.objects.filter(letterboxd_uri=cand.weak_uri).first()
        if movie:
            return movie     
        
    return None

def normalize_letterboxd_uri(uri: str):
    """
    Accepts:
        - https://letterboxd.com/film/<slug>/
        - https://letterboxd.com/film/<slug>
        - /film/<slug>/
        - film/<slug>/
        - https://boxd.it/<id>/
        - https://boxd.it/<id>
        returns a normalized url string, or None if blank/unparseable

    """
    # older version
    uri = (uri or "").strip()
    if not uri:
        return None
    if uri.startswith("/"):
        path = uri
        host = ""
    elif "://" not in uri:
        path = "/" + uri
        host = ""
    else:
        try:
            parsed = urlparse(uri)
            host = (parsed.netloc or "").lower()
            path = parsed.path or ""
        except Exception:
            return None
    
    parts = [p for p in path.split("/") if p]

    # global film path: /film/<slug>/
    if len(parts) >= 2 and parts[0] == "film":
        return f"https://letterboxd.com/film/{parts[1]}/"
    # user-scoped RSS item path: /<username>/films/<slug>/
    if len(parts) >= 3 and parts[1] == "film":
        return f"https://letterboxd.com/film/{parts[2]}/"
    # short boxd.it link
    if host in {"boxd.it","www.boxd.it"} and parts:
        return f"https://boxd.it/{parts[0]}/"
    
    return None

def extract_letterboxd_username(input_str: str) -> str | None:
    """
    Accepts:
      - "username"
      - "https://letterboxd.com/username/"
      - "https://letterboxd.com/username/rss/"
    Returns:
      - "username" or None
    """
    s = (input_str or "").strip()
    if not s:
        return None

    # raw username
    if "://" not in s and "letterboxd.com/" not in s and "/" not in s:
        username = s.strip("@").strip().lower()
        return username if _USERNAME_SAFE_RE.match(username) else None

    # support URLs without schem
    if s.startswith("letterboxd.com/") or s.startswith("www.letterboxd.com/"):
        s = "https://" + s

    try:
        u = urlparse(s)
    except Exception:
        return None

    # allow letterboxd.com only (or loosen if you want)
    host = (u.netloc or "").lower()
    if host not in {"letterboxd.com", "www.letterboxd.com"}:
        return None

    # path forms: /username/ or /username/rss/
    path = (u.path or "").rstrip("/")
    if path.endswith("/rss"):
        path = path[:-4].rstrip("/")  # remove trailing /rss

    m = _USERNAME_RE.match(path)
    if not m:
        return None

    username = m.group(1).strip().lower()
    # quick sanity
    if not _USERNAME_SAFE_RE.match(username):
        return None
    
    return username

# RSS Helper Function
def build_letterboxd_rss_url(raw: str) -> str:
    # revert to old simple version of building letterboxd rss url
    username = extract_letterboxd_username(raw)
    if not username:
        return ""
    return f"https://letterboxd.com/{username}/rss/"

"""    
LEGACY CODE
s = (raw or "").strip()
if not s:
    return ""

if s.startswith("letterboxd.com/"):
    s = "https://" + s

if s.startswith("http://") or s.startswith("https://"):
    s_clean = s.rstrip("/")
    if s_clean.endswith("/rss"):
        return s_clean + "/"
    
    m = re.match(r"^https?://letterboxd/.com/([^/]+)/?$", s_clean)
    if m:
        username = m.group(1)
        return f"https://letterboxd.com/{username}/rss/"

    return ""

username = extract_letterboxd_username(s)
if username:
    return f"https://letterboxd.com/{username}/rss/"

return ""    
"""

# --- Resetting User's State (RSS) ---
def reset_RSS_userState(user):
    with transaction.atomic():
        WatchEvent.objects.filter(user=user).delete()
        MovieUser.objects.filter(user=user).delete()
        FilmBank.objects.filter(user=user).delete()
        user.last_rss_sync = None
        user.last_sync = None
        user.rss_import_count = 0
        user.taste_vector_store_id = None
        user.save(update_fields=[
            "last_rss_sync",
            "last_sync",
            "rss_import_count",
            "taste_vector_store_id",
        ])

# --- Unified Import Functions ---
def parse_year(year_str):
    try:
        y = int((year_str or "").strip())
        return y
    except Exception:
        return None

def clean_letterboxd_title(name: str) -> str:
    return ((name or "").strip()[:255] or "Unknown")

def upsertMovie(title: str, year: int | None, uri: str | None, tmdb_id: int | None = None):
    return resolve_movie_one(title, year, uri, tmdb_id)

def resolve_movie_one(title: str, year: int | None, uri: str | None, tmdb_id: int | None = None):
    cand = normalize_movie_candidate(title, year, uri, tmdb_id)

    movie = choose_existing_movie_one(cand)
    created = False
    if movie:
        if patch_movie_from_candidate(movie, cand):
            movie.save(update_fields=["tmdb_id", "letterboxd_uri", "title", "year"])
        return movie, created, needToEnrich(movie)
    
    try:
        create_uri = cand.canonical_uri or None
        movie = Movie.objects.create(
            title=cand.title,
            year=cand.year,
            letterboxd_uri=create_uri,
            tmdb_id=cand.tmdb_id,
        )
        created = True
        return movie, created, needToEnrich(movie)
    
    except IntegrityError:
        movie = choose_existing_movie_one(cand)
        if not movie:
            raise
        if patch_movie_from_candidate(movie, cand):
            movie.save(update_fields=["tmdb_id","letterboxd_uri","title","year"])
        return movie, False, needToEnrich(movie)
    
def resolve_movies_bulk(candidates: list[NormalizedMovieCandidate]):
    canonical_uris = {c.canonical_uri for c in candidates if c.canonical_uri}
    titles = {c.title for c in candidates if c.title}
    years = {c.year for c in candidates if c.year is not None}

    existing_by_uri = {}
    if canonical_uris:
        for m in Movie.objects.filter(letterboxd_uri__in=canonical_uris):
            existing_by_uri[m.letterboxd_uri] = m

    existing_by_pair = {}
    if titles and years:
        for m in Movie.objects.filter(title__in=titles, year__in=years):
            existing_by_pair[(m.title, m.year)] = m

    resolved = []
    to_patch = {}
    to_create = {}

    def choose_existing_bulk(c: NormalizedMovieCandidate):
        if c.canonical_uri and c.canonical_uri in existing_by_uri:
            return existing_by_uri[c.canonical_uri]
        if c.title and c.year is not None and (c.title, c.year) in existing_by_pair:
            return existing_by_pair[(c.title, c.year)]
        return None

    for c in candidates:
        movie = choose_existing_bulk(c)
        if movie:
            if patch_movie_from_candidate(movie, c):
                to_patch[movie.id] = movie
            resolved.append(movie)
            continue

        create_key = (c.canonical_uri, c.title, c.year)

        if create_key not in to_create:
            to_create[create_key] = Movie(
                title=c.title,
                year=c.year,
                letterboxd_uri=c.canonical_uri or None,
            )

        resolved.append(to_create[create_key])

    if to_patch:
        Movie.objects.bulk_update(
            list(to_patch.values()),
            ["letterboxd_uri", "title", "year"],
        )

    if to_create:
        Movie.objects.bulk_create(list(to_create.values()), ignore_conflicts=True)

        # Re-fetch all possible created rows
        refetched_by_uri = {}
        if canonical_uris:
            for m in Movie.objects.filter(letterboxd_uri__in=canonical_uris):
                refetched_by_uri[m.letterboxd_uri] = m

        refetched_by_pair = {}
        if titles and years:
            for m in Movie.objects.filter(title__in=titles, year__in=years):
                refetched_by_pair[(m.title, m.year)] = m

        new_resolved = []
        for movie in resolved:
            if movie.id is not None:
                new_resolved.append(movie)
                continue

            replacement = None
            if movie.letterboxd_uri:
                replacement = refetched_by_uri.get(movie.letterboxd_uri)

            if replacement is None and movie.title and movie.year is not None:
                replacement = refetched_by_pair.get((movie.title, movie.year))

            new_resolved.append(replacement or movie)

        resolved = new_resolved

    return resolved

# --- Unified Event key for both Manual & RSS Imports ---
def makeEventKey(user_id:int, uri: str, posted_date: Optional[date], entry_url: str | None = None) -> str:
    date_part = posted_date.isoformat() if posted_date else "nodate"
    unique_part = (entry_url or uri or "").strip()
    return hashlib.sha1(
        f"{user_id}|{unique_part}|{date_part}".encode("utf-8")
    ).hexdigest()

def build_watchEventKey(user_id: int, movie, posted_date):
    if not movie or not movie.letterboxd_uri or not posted_date:
        return None
    return makeEventKey(user_id, movie.letterboxd_uri, posted_date)

def upsert_watch_event(*, user, movie, posted_date, watched_date=None, rewatch=False, source="csv", entry_url=None):
    if not posted_date or not movie or not movie.letterboxd_uri:
        return None, False
    
    event_key = makeEventKey(user.id, movie.letterboxd_uri, posted_date, entry_url=entry_url or movie.letterboxd_uri,)
    try:
        we, created = WatchEvent.objects.get_or_create(
            user=user,
            event_key=event_key,
            defaults={
                "movie": movie,
                "posted_date": posted_date,
                "watched_date": watched_date,
                "rewatch": rewatch,
                "source": source,
                "entry_url": entry_url or movie.letterboxd_uri,
            },
        )
        return we, created
    except IntegrityError:
        we = WatchEvent.objects.get(user=user, event_key=event_key)
        return we, False

def upsert_movieuser_snapshot(user, movie, updates):
    try:
        mu, created = MovieUser.objects.get_or_create(user=user, movie=movie)
    except IntegrityError:
        # returns (movie_user, created)
        mu, created = MovieUser.objects.get_or_create(user=user, movie=movie)
        created = False

    changed = False
    for k, v in updates.items():
        if getattr(mu, k) != v:
            setattr(mu, k, v)
            changed = True
    if changed:
        mu.save()
    return mu, created, changed

# --- Enrichment Marker ---
def needToEnrich(movie) -> bool:
    if not movie:
        return False
    return(
        not movie.tmdb_id or 
        getattr(movie, "enrichment_status", None) in MUST_ENRICH_STATUS
    )