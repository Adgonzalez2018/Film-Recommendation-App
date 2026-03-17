from typing import Optional
import hashlib
from datetime import date

def make_eventkey(user_id:int, uri: str, posted_date: Optional[date], entry_url: str | None = None) -> str:
    date_part = posted_date.isoformat() if posted_date else "nodate"
    unique_part = (entry_url or uri or "").strip()
    return hashlib.sha1(
        f"{user_id}|{unique_part}|{date_part}".encode("utf-8")
    ).hexdigest()
