TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

def _build_poster_url(mv) -> str | None:
    raw = getattr(mv, "poster_url", None) or getattr(mv, "poster_path", None)

    if not raw:
        return None
    
    raw = str(raw).strip()
    if raw.startswith("http"):
        return raw # alr a full URL
    # strip leading slash if present
    return f"{TMDB_IMAGE_BASE}/{raw.lstrip('/')}"