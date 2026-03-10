from typing import Optional
import hashlib
from datetime import date

def make_eventkey(user_id:int, uri: str, posted_date: Optional[date]) -> str:
    date_part = posted_date.isoformat() if posted_date else "nodate"
    return hashlib.sha1(
        f"{user_id}|{uri}|{date_part}".encode("utf-8")
    ).hexdigest()
