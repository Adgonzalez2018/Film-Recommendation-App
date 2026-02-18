from urllib.parse import urlparse


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
