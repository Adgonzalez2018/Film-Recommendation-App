from urllib.parse import urlparse
import re

_USERNAME_RE = re.compile(r"^/([^/]+)/?$")

def normalize_letterboxd_uri(uri: str):
    """
    Canonicalize Letterboxd film URI.
    Accepts:
      - https://letterboxd.com/film/<slug>/
      - https://letterboxd.com/film/<slug>
      - /film/<slug>/
      - film/<slug>
    Returns canonical: https://letterboxd.com/film/<slug>/
    or None if it can't parse.
    """
    uri = (uri or "").strip()
    if not uri:
        return None

    # If it's just a path-ish value, normalize it
    if uri.startswith("/"):
        path = uri
    elif "://" not in uri:
        path = "/" + uri
    else:
        try:
            parsed = urlparse(uri)
            path = parsed.path or ""
        except Exception:
            return None

    # Expect /film/<slug>/...
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2 or parts[0] != "film":
        return None

    slug = parts[1]
    if not slug:
        return None

    return f"https://letterboxd.com/film/{slug}/"

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
    if "://" not in s and "/" not in s:
        return s.strip("@")

    try:
        u = urlparse(s)
    except Exception:
        return None

    # allow letterboxd.com only (or loosen if you want)
    host = (u.netloc or "").lower()
    if "letterboxd.com" not in host:
        return None

    # path forms: /username/ or /username/rss/
    path = (u.path or "").rstrip("/")
    if path.endswith("/rss"):
        path = path[:-4].rstrip("/")  # remove trailing /rss

    m = _USERNAME_RE.match(path)
    if not m:
        return None

    username = m.group(1)
    # quick sanity
    if not re.match(r"^[A-Za-z0-9_]+$", username):
        return None
    return username

# RSS Helper Function
def build_letterboxd_rss_url(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    
    # if they paste "letterboxd.com/username" without scheme
    if s.startswith("letterboxd.com/"):
        s = "https://" + s
    
    # Full URL with scheme
    if s.startswith("http://") or s.startswith("https://"):
        # if it's already an rss URL, keep it
        if s.rstrip("/").endswith("/rss/"):
            return s.rstrip("/") + "/"
        # if it's a profile URL like httsp://letterboxd.com/<user>/
        m = re.match(r"^https?://letterboxd\.com/([^/]+)/?$", s.rstrip("/"))
        if m:
            username = m.group(1)
            return f"https://letterboxd.com/{username}/rss/"
        # unnknown URL Format
        return ""
    