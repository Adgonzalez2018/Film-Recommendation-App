from urllib.parse import urlparse
import re

_USERNAME_RE = re.compile(r"^/([^/]+)/?$")
_USERNAME_SAFE_RE = re.compile(r"^[A-Za-z0-9_]+$")

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
    username = extract_letterboxd_username(raw)
    if not username:
        return ""
    return f"https://letterboxd.com/{username}/rss/"
    