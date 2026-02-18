from datetime import datetime, timedelta
from django.utils import timezone

def parse_iso_date(s: str):
    s = (s or "").strip()
    if not s:
        return None
    # Letterboxd export uses YYY-MM-DD
    return datetime.strptime(s, "%Y-%m-%d").date()

# creates week windows
def week_window_sunday_anchor(now=None):
    # returns prev start, prev_end, curr_start, curr_end
    # weeks stsart on sunday 00:00
    # ranges are half-open intervals [start, end)
    # prev_week = [prev_start, prev_end) = [curr_start - 7 days, curr_start)
    # curr_week = [curr_start, curr_end) = [prev_end, prev_end
    if now is None:
        now = timezone.now()
        
    # Convert to local timezone
    local_now = timezone.localtime(now)

    # Python weekday(): Monday=0, Sunday=6
    # Days since sunday
    days_since_sunday = (local_now.weekday() + 1) % 7
    # most recent sunday date
    recent_sunday = local_now - timedelta(days=days_since_sunday)

    # sunday local time at 00:00
    curr_start = timezone.make_aware(
        datetime.combine(recent_sunday.date(), datetime.min.time()),
        timezone.get_current_timezone(),
    )

    curr_end = curr_start + timedelta(days=7)

    prev_start = curr_start - timedelta(days=7)
    prev_end = curr_start

    return prev_start, prev_end, curr_start, curr_end
