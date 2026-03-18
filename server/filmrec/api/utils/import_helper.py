from urllib.parse import urlparse
import re
from typing import Optional
import hashlib
from datetime import date

from api.models import Movie, WatchEvent, MovieUser

_USERNAME_RE = re.compile(r"^/([^/]+)/?$")
_USERNAME_SAFE_RE = re.compile(r"^[A-Za-z0-9_]+$")
MUST_ENRICH_STATUS = ["pending", "queued", "failed", "not_found"]

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
    uri = (uri or "").strip()
    if not uri:
        return None

    # If it's just a path-ish value, normalize it
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

    # full letterboxd film path
    if len(parts) >= 2 and parts[0] == "film" and parts[1]:
        slug = parts[1]
        return f"https://letterboxd.com/film/{slug}/"
    
    # short boxd.it link from csv exports
    if host in {"boxd.it","www.boxd.it"}and len(parts) >= 1 and parts[0]:
        short_id = parts[0]
        return f"https://boxd.it/{short_id}/"
    
    # Raw boxd.it ish without scheme
    if len(parts) == 1 and parts[0] and "." not in parts[0]:
        # only use this if we allow bare short IDs
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
    s = (raw or "").strip()
    if not s:
        return ""
    
    if s.startswith("letterboxd.com/"):
        s = "https://" + s
    
    if s.startswith("http://") or s.startswith("https://"):
        s_clean = s.rstrip("/")
        if s_clean.endswith("/rss"):
            return s_clean + "/"
        
        m = re.match(r"^https?://letterboxd\.com/([^/]+)/?$", s_clean)
        if m:
            username = m.group(1)
            return f"https://letterboxd.com/{username}/rss/"

        return ""

    username = extract_letterboxd_username(s)
    if username:
        return f"https://letterboxd.com/{username}/rss/"

    return ""    

# --- Unified Import Functions ---
def parse_year(year_str):
    try:
        y = int((year_str or "").strip())
        return y
    except Exception:
        return None

def clean_letterboxd_title(name: str) -> str:
    return ((name or "").strip()[:255] or "Unknown")

def upsertMovie(title: str, year: int | None, uri: str | None):
    # Returns movie created matched_existing
    # - matches by letterboxd uri first
    # fall back to title + year
    # patches missing basics
    # creats minimal movie with enrichment status if needed
    #nonlocal movies_created, movies_matched
    movie = None
    created = False
    matched_existing = False
    clean_name = clean_letterboxd_title(title)
    y = parse_year(year)
    uri = normalize_letterboxd_uri(uri)

    # 1 Best local key: Letterboxd URI
    if uri:
        movie = Movie.objects.filter(letterboxd_uri=uri).first()

    # 2 Fallback local key: title + year
    if not movie and clean_name and y is not None:
        movie = Movie.objects.filter(title=clean_name, year=y).first()
        if movie:
            matched_existing = True
            updates = {}
            if not movie.letterboxd_uri and uri:
                updates["letterboxd_uri"] = uri
            if (movie.title == "Unknown") and clean_name:
                updates["title"] = clean_name
            if movie.year is None and y is not None:
                updates["year"] = y
            if updates:
                for k, v in updates.items():
                    setattr(movie, k,v)
                movie.save(update_fields=list(updates.keys()))
            return movie, created, matched_existing 
        
    # 3 If found locally, patch missing basics and return
    if movie:
        matched_existing = True
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
        return movie, created, matched_existing 

    # 4 Last resort: create local minimal movie row
    movie = Movie.objects.create(
        title=clean_name,
        year=y,
        letterboxd_uri=uri,
        enrichment_status="pending",
    )
    created = True
    return movie, created, matched_existing

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
    
    event_key = makeEventKey(user.id, movie.letterboxd_uri, posted_date)

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

def upsert_movieuser_snapshot(user, movie, updates):
    # returns (movie_user, created)
    mu, created = MovieUser.objects.get_or_create(user=user, movie=movie)
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
        movie is not None and (
            not movie.tmdb_id or 
            getattr(movie, "enrichment_status", None) in MUST_ENRICH_STATUS
        )
    )