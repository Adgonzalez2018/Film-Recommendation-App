from django.shortcuts import render
from django.contrib.auth import authenticate
from django.db import transaction

from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt import tokens, views as jwt_views, serializers as jwt_serializers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from datetime import timedelta, timezone, datetime, date
from collections import Counter
import csv
import io
import re
import feedparser


from .models import *
from .serializer import *


"""
Importing User Data helper functions
"""


# Functions for CSV Files
def parse_iso_date(s: str):
    s = (s or "").strip()
    if not s:
        return None
    # Letterboxd export uses YYY-MM-DD
    return datetime.strptime(s, "%Y-%m-%d").date()

def normalize_letterboxd_uri(uri: str):
    uri = (uri or "").strip()
    # Simple store as is
    return uri[:-1] if uri.endswith("/") else uri

# RSS Helper Function
def _build_letterboxd_rss_url(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    
    # if they paste "letterboxd.com/username" without scheme
    if s.startswith("letterboxd.com/"):
        s = "https://" + s
    
    # Full URL with scheme
    if s.startsqwith("http://") or s.startswith("https://"):
        # if it's already an rss URL, keep it
        if s.rstrip("/").endswith("/rss/"):
            return s.rstrip("/") + "/"
        # if it's a profile URL like httsp://letterboxd.com/<user>/
        m = re.match(r"^https?://letterboxd\.com/([^/]+)/?$", s.rstrip("/"))
        if m:
            username = m.group(2)
            return f"https://letterboxd.com/{username}/rss/"
        # unnknown URL Format
        return ""
    
    # otherwise treat as username
    username = s.strip("/").replace(" ", "")
    if not username:
        return ""
    return f"https://letterboxd.com/{username}/rss/"

def _parse_published_date(entry) -> datetime | None:
    # feedparser gives published_parsed as a time.struct_time sometimes
    tp = getattr(entry, "published_parsed", None)
    if tp:
        try:
            return datetime(tp.tm_year, tp.tm_mon, tp.tm_mday, tp.tm_hour, tp.tm_min, tp.tm_sec)
        except Exception:
            return None
        
    # fallback: try published string
    pub = getattr(entry, "published", None)
    if pub:
        try:
            # very lose fallback; tighten later
            return datetime.fromisoformat(pub)
        except Exception:
            return None
        
"""
Statistics and Utility Functions
"""
# Centralized data check
def user_has_letterboxd_data(user):
    return MovieUser.objects.filter(user=user).exists()
    
DECADE_ORDER = ["Pre-60s", "60s", "70s", "80s", "90s", "00s", "10s", "20s"]

# Produces token for user which can be used for authentication in subsequent requests.
def get_user_tokens(user):
    refresh = tokens.RefreshToken.for_user(user)
    return {
        "access_token": str(refresh.access_token),
    }

# creates week windows
def week_window_sunday_anchor(now=None):
    # returns prev start, prev_end, curr_start, curr_end
    # weeks stsart on sunday 00:00
    # ranges are half-open intervals [start, end)
    # prev_week = [prev_start, prev_end) = [curr_start - 7 days, curr_start)
    # curr_week = [curr_start, curr_end) = [prev_end, prev_end
    if now is None:
        now = datetime.now()
        
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

# Load Movies for the given user and week window
def loadWeekly(user, start_date, end_date):
    # Get all MovieUser entries for the user within the specified date range
    movie_user_entries = MovieUser.objects.filter(
        user=user,
        watch_status="Watched",         # Only consider movies that were actually watched
        watched_date__isnull=False,     # Ensure watched_date is not null
        watched_date__gte=start_date,
        watched_date__lt=end_date
    )

    return movie_user_entries
    
# Function for Percent Change from Last Week to This Week
def calc_percentChange(old, new):
    if old == 0:
        return None                                             # return None or some default value when old is 0 to avoid division by zero
    return ((new - old) / abs(old)) * 100

# Function for Chart
def calculatePerDay(entries, start_date):
    weekData = [0] * 7                                          # Initialize counts for each day of the week 
    for entry in entries:
        delta = (entry.watched_date.date() - start_date).days   # Calculate the day index (0 for Sunday, 1 for Monday, ..., 6 for Saturday)
        if 0 <= delta < 7:
            weekData[delta] += 1

    return weekData

# Functions for By Decade Distribution
def getDecadeLabel(year: int) -> str:
    if year < 1960:
        return "Pre-60s"
    decade = (year // 10) * 10
    two = (decade % 100)
    return f"{two:02d}s"

def byDecadePayload(movieuser_qs):
    # pull years from MovieUser entries and calculate decade distribution
    years = movieuser_qs.values_list("movie__release_date__year", flat=True)
    
    counts = Counter()
    for y in years:
        if y is None:
            continue
        label = getDecadeLabel(int(y))
        counts[label] += 1

    return [{"label": lab, "count": counts.get(lab, 0)} for lab in DECADE_ORDER]


"""
API Endpoints
"""

# --- Login Endpoint ---
@api_view(['POST'])
@permission_classes([AllowAny])
def loginView(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    username = serializer.validated_data['username']
    password = serializer.validated_data['password']
    user = authenticate(username=username, password=password)

    if user is not None:
        tokens = get_user_tokens(user)
        return Response(tokens, status=status.HTTP_200_OK)
    else:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
    
# --- Registration Endpoint ---
@api_view(['POST'])
@permission_classes([AllowAny])
def registerView(request):
    serializer = RegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    user_tokens = get_user_tokens(user)
    return Response(user_tokens, status=status.HTTP_201_CREATED)


# --- Stats Endpoint ---
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stats_payload(request):
    # check if user imported data
    if user_has_letterboxd_data(request.user):
        return Response(
            {"error": "Import Required"},
            status=status.HTTP_409_CONFLICT,
        )
    
    lastWeekStart, lastWeekEnd, thisWeekStart, thisWeekEnd = week_window_sunday_anchor()
    thisWeekMovies = loadWeekly(request.user, thisWeekStart, thisWeekEnd)
    lastWeekMovies = loadWeekly(request.user, lastWeekStart, lastWeekEnd)

    days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    # Calculate day indices for this and last week
    thisWeekArr = calculatePerDay(thisWeekMovies, thisWeekStart)
    lastWeekArr = calculatePerDay(lastWeekMovies, lastWeekStart)

    # --- Calculate top directors, actors, genres ---
    # Top 5 Directors 
    topDirectors = (
        Director.objects
        .filter(moviedirector__movie__movieuser__in=thisWeekMovies)
        .annotate(count=models.Count('moviedirector__movie__movieuser', distinct=True))
        .order_by('-count')[:5]
    )
    # Top 5 actors
    topActors = (
        Actor.objects
        .filter(movieactor__movie__movieuser__in=thisWeekMovies)
        .annotate(count=models.Count('movieactor__movie__movieuser', distinct=True))
        .order_by('-count')[:5]
    )
    # Top 5 genres
    topGenres = (
        Genre.objects
        .filter(moviegenre__movie__movieuser__in=thisWeekMovies)
        .annotate(count=models.Count('moviegenre__movie__movieuser', distinct=True))
        .order_by('-count')[:5]
    )
    # Get most recent movies for this week
    recentEntries = (
        thisWeekMovies
        .select_related("movie")
        .order_by("-watched_date")[:5]
    )
    recentMovies = [entry.movie for entry in recentEntries]
    
    # Calculate Statistics
    # movie count
    thisWeekCount = thisWeekMovies.count()
    lastWeekCount = lastWeekMovies.count()
    percentChange = calc_percentChange(lastWeekCount, thisWeekCount)
    decadeCounts = byDecadePayload(
        thisWeekMovies.values_list('movie__release_date__year', flat=True)
        )

    return Response({
        "totalWatches": thisWeekCount,
        "percentChange": percentChange,
        "days": days,
        "thisWeek": thisWeekArr,
        "lastWeek": lastWeekArr,
        "directors": [
            {"name": d.name, "count": d.count} for d in topDirectors
        ],
        "actors": [
            {"name": a.name, "count": a.count} for a in topActors
        ],
        "genres": [
            {"name": g.name, "count": g.count} for g in topGenres
        ],
        "recentFilms": [
            {"name": m.title} for m in recentMovies
        ],
        "byDecade": decadeCounts,
    }, status=status.HTTP_200_OK)
    
# --- User Import (Manual) Endpoint --- 
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def letterboxd_import(request):
    """
    Manual Letterboxd import.

    Accepts multipart/form-data with any of:
      - reviews (CSV)
      - watchlist (CSV)
      - films (CSV)   # films.csv inside the likes folder export

    Upserts:
      - Movie by letterboxd_uri
      - MovieUser by (user, movie)
    """
    reviews_file = request.FILES.get("reviews")
    watchlist_file = request.FILES.get("watchlist")
    films_file = request.FILES.get("films") or request.FILES.get("likes")  # tolerate either

    if not reviews_file and not watchlist_file and not films_file:
        return Response(
            {"error": "No files provided. Upload at least one of: reviews, watchlist, films."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = request.user

    # Counters
    movies_created, movies_matched, rel_created, rel_updated = 0, 0, 0, 0

    # ---------- shared helpers ----------
    def iter_csv(file_obj):
        text = io.TextIOWrapper(file_obj.file, encoding="utf-8-sig")
        return csv.DictReader(text)

    def year_to_date(year_str):
        try:
            y = int(year_str) if year_str else None
            return date(y, 1, 1) if y else None
        except Exception:
            return None

    def upsert_movie(name, year, uri):
        nonlocal movies_created, movies_matched

        uri = normalize_letterboxd_uri(uri)
        if not uri:
            return None

        movie = Movie.objects.filter(letterboxd_uri=uri).first()
        if movie:
            movies_matched += 1
            # optional: fill title if blank
            if (not movie.title) and name:
                movie.title = (name or "").strip()[:255]
                movie.save(update_fields=["title"])
            return movie

        movie = Movie.objects.create(
            title=((name or "").strip()[:255] or "Unknown"),
            release_date=year_to_date(year),
            letterboxd_uri=uri,
        )
        movies_created += 1
        return movie

    def get_or_create_mu(movie):
        nonlocal rel_created
        mu, created = MovieUser.objects.get_or_create(user=user, movie=movie)
        if created:
            rel_created += 1
        return mu

    def apply_update(mu: MovieUser, updates: dict):
        nonlocal rel_updated
        changed = False
        for k, v in updates.items():
            if getattr(mu, k) != v:
                setattr(mu, k, v)
                changed = True
        if changed:
            mu.save()
            rel_updated += 1

    def parse_float(s):
        s = (s or "").strip()
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    # ---------- per-csv handlers ----------
    def import_reviews_csv(file_obj):
        """
        Reviews header:
        Date,Name,Year,Letterboxd URI,Rating,Rewatch,Review,Tags,Watched Date
        """
        for row in iter_csv(file_obj):
            name = row.get("Name")
            year = row.get("Year")
            uri = row.get("Letterboxd URI")

            movie = upsert_movie(name, year, uri)
            if not movie:
                continue

            mu = get_or_create_mu(movie)

            watched_date = parse_iso_date(row.get("Watched Date"))
            rating = parse_float(row.get("Rating"))
            review_text = (row.get("Review") or "").strip()
            rewatch_raw = (row.get("Rewatch") or "").strip()

            # Normalize rewatch to bool if you want it later
            # Letterboxd sometimes uses "Yes" or "true" or "1" (varies)
            rewatch = rewatch_raw.lower() in {"yes", "true", "1", "y"} if rewatch_raw else None

            updates = {
                "watch_status": "Watched",
            }
            if watched_date:
                updates["watched_date"] = watched_date
            if rating is not None:
                updates["rating"] = rating
            if review_text:
                updates["review"] = review_text

            # Only if you add a field to MovieUser, e.g. `rewatch = models.BooleanField(...)`
            # if rewatch is not None:
            #     updates["rewatch"] = rewatch

            apply_update(mu, updates)

    def import_watchlist_csv(file_obj):
        """
        Watchlist header:
        Date,Name,Year,Letterboxd URI
        """
        for row in iter_csv(file_obj):
            name = row.get("Name")
            year = row.get("Year")
            uri = row.get("Letterboxd URI")

            movie = upsert_movie(name, year, uri)
            if not movie:
                continue

            mu = get_or_create_mu(movie)

            updates = {"in_watchlist": True}

            # Don't overwrite watched records
            if not mu.watched_date and mu.watch_status != "Watched":
                updates["watch_status"] = "Want to Watch"

            apply_update(mu, updates)

    def import_films_likes_csv(file_obj):
        """
        Likes export is films.csv inside likes folder:
        Date,Name,Year,Letterboxd URI
        """
        for row in iter_csv(file_obj):
            name = row.get("Name")
            year = row.get("Year")
            uri = row.get("Letterboxd URI")

            movie = upsert_movie(name, year, uri)
            if not movie:
                continue

            mu = get_or_create_mu(movie)
            apply_update(mu, {"liked": True})

    # ---------- run import ----------
    with transaction.atomic():
        if reviews_file:
            import_reviews_csv(reviews_file)
        if watchlist_file:
            import_watchlist_csv(watchlist_file)
        if films_file:
            import_films_likes_csv(films_file)

    return Response(
        {
            "status": "ok",
            "movies_created": movies_created,
            "movies_matched": movies_matched,
            "relationships_created": rel_created,
            "relationships_updated": rel_updated,
        },
        status=status.HTTP_200_OK,
    )
    

# --- RSS Import Endpoint ---
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def letterboxd_rss(request):
    """
    POST {rss : "<username OR profile url OR rss url>"}
    syncs recent watches from public Letterboxd RSS.
    """
    rss_input = (request.data.get("rss") or "").strip()
    rss_url = _build_letterboxd_rss_url(rss_input)
    if not rss_url:
        return Response(
            {"error": "Invalid RSS input"}, 
            status=status.HTTP_400_BAD_REQUEST,
            )
    feed = feedparser.parse(rss_url)
    # feed.bozo indicates a parsing error
    if getattr(feed, "bozo", False):
        return Response(
            {"error": "Could not read that RSS feed. Make sure the profile is public and the input is correct."}, 
            status=status.HTTP_400_BAD_REQUEST,
            )
    user = request.user
    synced, created_movies, created_links, updated_links = 0, 0, 0, 0
    # Typical entries ~20
    for entry in feed.entries:
        link = (getattr(entry, "link", "") or "").strip()
        title = (getattr(entry, "title", "") or "").strip()
        if not link:
            continue
        # use the entry link as our letterboxd_uri key
        movie, movie_created = Movie.objects.get_or_create(
            letterboxd_uri=link,
            defaults={"title": title[:255] if title else None}
        )
        if movie_created:
            created_movies += 1

        # Create or update relationship for this user and movie
        mu, created = MovieUser.objects.get_or_create(
            user=user,
            movie=movie,
        )
        if created:
            created_links += 1
        
        # Mark watched + set watched_date from RSS publish date if present
        pub_dt = _parse_published_date(entry)
        watched_date = pub_dt if pub_dt else None
        
        changed = False
        if mu.watch_status != "Watched":
            mu.watch_status = "Watched"
            changed = True

        if watched_date and mu.watched_date != watched_date:
            mu.watched_date = watched_date
            changed = True
        
        if changed:
            mu.save()
            if not created:
                updated_links += 1

        synced += 1

        return Response({
            "status": "ok",
            "rss_url": rss_url,
            "entries_processed": synced,
            "movies_created": created_movies,
            "movieuser_created": created_links,
            "movieuser_updated": updated_links,
        })
        

# --- Authenticated Ping Endpoint ---
# Check for authentication and return user info if authenticated, otherwise return 401   
@api_view(['GET'])
def ping(request):
    user = request.user
    return Response({"username": user.username, "id": user.id}, 
                    status=status.HTTP_200_OK)

