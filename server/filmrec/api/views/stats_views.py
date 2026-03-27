"""
Endpoints:
- sends stats payloads for:
    - all time stats report
    - weekly stats report
- Both use WatchEvents rather than MovieUser database

- Both stats payload include:
    - top 5 directors
    - top 5 actors
    - top 5 genres
    - 5 most recent movies
    - Movies per Decade

- Weekly Stats include:
    - Last Week vs This week Graph Chart
    - Movies tally per day of This Week

- All Time Stats include:
    - Total hours watched
    - Total Day/hour conversion
"""
from collections import Counter

from django.db import models
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import (
    MovieUser, 
    Genre,
    Person,
    WatchEvent,
    )
from ..utils.dates import week_window_sunday_anchor


DECADE_ORDER = ["Pre-1960s", "60s", "70s", "80s", "90s", "00s", "10s", "20s"]

def loadAllTime(user):
    return MovieUser.objects.filter(
        user=user,
        watch_status="Watched",
        watched_date__isnull=False,
    )

def loadWeekly(user, start_date, end_date):
    return WatchEvent.objects.filter(
        user=user,
        watched_date__isnull=False,
        watched_date__gte=start_date,
        watched_date__lt=end_date,
    )

def calc_percentChange(old, new):
    if old == 0:
        return None
    return ((new - old) / abs(old)) * 100

def calculatePerDay(entries, start_date):
    weekData = [0] * 7
    start = start_date.date() if hasattr(start_date, "date") else start_date

    for entry in entries:
        wd = entry.posted_date or entry.posted_date
        if wd is None:
            continue

        wd = wd.date() if hasattr(wd, "date") else wd
        delta = (wd - start).days

        if 0 <= delta < 7:
            weekData[delta] += 1
    
    return weekData

def getDecadeLabel(year: int) -> str:
    if year < 1960:
        return "Pre-1960s"
    decade = (year // 10) * 10
    two = decade % 100
    return f"{two:02d}s"


# pulling from watchevents instead of movieuser
def byDecadePayloadFromEvents(event_qs):
    counts = Counter()
    
    for event in event_qs:
        movie = getattr(event, "movie", None)
        year = getattr(movie," year", None)
        if year is None:
            continue
        counts[getDecadeLabel(int(year))] += 1

    return [{"label": lab, "count": counts.get(lab, 0)} for lab in DECADE_ORDER]

def _movie_card(m):
    return {
        "id": m.id,
        "title": m.title,
        "year": getattr(m, "year", None),
        "poster_url": getattr(m, "poster_url", None),
        "tmdb_id": getattr(m, "tmdb_id", None),
    }

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def stats_payload(request):
    lastWeekStart, lastWeekEnd, thisWeekStart, thisWeekEnd = week_window_sunday_anchor()
    user = request.user

    thisWeekEvents = (
        loadWeekly(request.user, thisWeekStart, thisWeekEnd)
        .select_related("movie")
        .exclude(movie__isnull=True)
    )
    lastWeekEvents = (
        loadWeekly(request.user, lastWeekStart, lastWeekEnd)
        .select_related("movie")
        .exclude(movie__isnull=True)
    )

    days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    thisWeekArr = calculatePerDay(thisWeekEvents, thisWeekStart)
    lastWeekArr = calculatePerDay(lastWeekEvents, lastWeekStart)

    week_movie_ids = thisWeekEvents.values_list("movie_id", flat=True)

    # Top 5 Directors Watched - Distinct
    topDirectors = (
        Person.objects.filter(
            moviecrew__job="Director",
            moviecrew__movie__watchevent__user=user,
            moviecrew__movie__watchevent__watched_date__gte=thisWeekStart,
            moviecrew__movie__watchevent__watched_date__lt=thisWeekEnd,
            moviecrew__movie__watchevent__watch_status="Watched",
            moviecrew__movie__watchevent__movie__isnull=False,
        )
        .annotate(count=models.Count("moviecrew__movie__watchevent"))
        .order_by("-count", "name")[:5]
    )

    # Top 5 Actors Watched - Distinct
    topActors = (
        Person.objects.filter(
            moviecast__movie__watchevent__user=user,
            moviecast__movie__watchevent__watched_date__gte=thisWeekStart,
            moviecast__movie__watchevent__watched_date__lt=thisWeekEnd,
            moviecast__movie__watchevent__watch_status="Watched",
            moviecast__movie__watchevent__movie__isnull=False,
        )
        .annotate(count=models.Count("moviecast__movie__watchevent"))
        .order_by("-count", "name")[:5]
    )

    # Top 5 Genres (weekly) - Distinct
    topGenres = (
        Genre.objects.filter(
            moviegenre__movie__watchevent__user=user,
            moviegenre__movie__watchevent__watched_date__gte=thisWeekStart,
            moviegenre__movie__watchevent__watched_date__lt=thisWeekEnd,
            moviegenre__movie__watchevent__watch_status="Watched",
            moviegenre__movie__watchevent__movie__isnull=False,
        )
        .annotate(count=models.Count("moviegenre__movie__watchevent"))
        .order_by("-count", "name")[:5]
    )


    recentEntries = thisWeekEvents.order_by("-posted_date")[:5]
    recentMovies = [entry.movie for entry in recentEntries]

    thisWeekCount = thisWeekEvents.count()
    lastWeekCount = lastWeekEvents.count()
    percentChange = calc_percentChange(lastWeekCount, thisWeekCount)

    decadeCounts = byDecadePayloadFromEvents(thisWeekEvents)

    return Response(
        {
            "totalWatches": thisWeekCount,
            "percentChange": percentChange,
            "days": days,
            "thisWeek": thisWeekArr,
            "lastWeek": lastWeekArr,
            "directors": [{"name": d.name, "count": d.count} for d in topDirectors],
            "actors": [{"name": a.name, "count": a.count} for a in topActors],
            "genres": [{"name": g.name, "count": g.count} for g in topGenres],
            "recentFilms": [_movie_card(m) for m in recentMovies],
            "byDecade": decadeCounts,
        },
        status=status.HTTP_200_OK,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def stats_all_time(request):
    user = request.user
    allEvents = (
        WatchEvent.objects
        .filter(user=user)
        .select_related("movie")
        .exclude(movie__isnull=True)
    )
    

    topDirectors = (
        Person.objects.filter(
            moviecrew__movie__watchevent__user=user,
            moviecrew__job="Director",
        )
        .annotate(count=models.Count("moviecrew__movie__watchevent"))
        .order_by("-count")[:5]
    )

    topActors = (
        Person.objects.filter(
            moviecast__movie__watchevent__user=user,
        )
        .annotate(count=models.Count("moviecast__movie__watchevent"))
        .order_by("-count")[:5]
    )

    topGenres = (
        Genre.objects.filter(
            moviegenre__movie__watchevent__user=user
        )
        .annotate(count=models.Count("moviegenre__movie__watchevent"))
        .order_by("-count")[:5]
    )

    recentEntries = (
       allEvents
       .order_by("-posted_date","-id")[:5]
    )
    recentMovies = [entry.movie for entry in recentEntries]

    # totalCount = allMovies.count() 
    # bandaid fix for dupe movies atm
    totalCount = allEvents.count()
    decadeCounts = byDecadePayloadFromEvents(allEvents)


    # New stat - total lifetime watch time (minutes)
    agg = allEvents.aggregate(
        total_minutes=Coalesce(Sum("movie__runtime"), 0),
        runtime_watches=models.Count(
            "id",
            filter=models.Q(runtime__isnull=False),
        ),
    )
    # minutes to hours and days conversion
    total_minutes = int(agg["total_minutes"] or 0)
    total_hours = total_minutes // 60
    days = total_hours // 24
    hours = total_hours % 24
    runtime_movies = int(agg["runtime_movies"] or 0)
    return Response(
        {
            "totalWatches": totalCount,
            "totalMinutesWatched": total_minutes,
            "totalHoursWatched": total_hours,
            "totalTimeWatched": {
                "days": days,
                "hours": hours,
            },
            "runtimeCoverage":{
                "withRuntime": runtime_movies,
                "withoutRuntime": max(totalCount - runtime_movies, 0),
            },
            "directors": [{"name": d.name, "count": d.count} for d in topDirectors],
            "actors": [{"name": a.name, "count": a.count} for a in topActors],
            "genres": [{"name": g.name, "count": g.count} for g in topGenres],
            "recentFilms": [_movie_card(m) for m in recentMovies],
            "byDecade": decadeCounts,
        },
        status=status.HTTP_200_OK,
    )