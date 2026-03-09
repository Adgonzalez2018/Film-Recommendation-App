"""
Endpoints:
- sends stats payloads for:
    - all time stats report
    - weekly stats report
"""
from collections import Counter

from django.db import models
from django.db.models import Sum
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
        watch_status="Watched",
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
        wd = entry.posted_date
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

def byDecadePayload(movieuser_qs):
    years = movieuser_qs.values_list("movie__year", flat=True)

    counts = Counter()
    for y in years:
        if y is None:
            continue
        counts[getDecadeLabel(int(y))] += 1

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

    thisWeekEvents = loadWeekly(request.user, thisWeekStart, thisWeekEnd)
    lastWeekEvents = loadWeekly(request.user, lastWeekStart, lastWeekEnd)

    days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    thisWeekArr = calculatePerDay(thisWeekEvents, thisWeekStart)
    lastWeekArr = calculatePerDay(lastWeekEvents, lastWeekStart)

    week_movie_ids = thisWeekEvents.values_list("movie_id", flat=True)

    # Top 5 Directors Watched - Distinct
    topDirectors = (
        Person.objects.filter(
            moviecrew__movie_id__in = week_movie_ids,
            moviecrew__job="Director",
        )
        .annotate(count=models.Count("moviecrew__movie", distinct=True))
        .order_by("-count")[:5]
    )

    # Top 5 Actors Watched - Distinct
    topActors = (
        Person.objects.filter(
            moviecast__movie_id__in = week_movie_ids
        )
        .annotate(count=models.Count("moviecast__movie", distinct=True))
        .order_by("-count")[:5]
    )

    # Top 5 Genres (weekly) - Distinct
    topGenres = (
        Genre.objects.filter(moviegenre__movie_id__in=week_movie_ids)
        .annotate(count=models.Count("moviegenre__movie", distinct=True))
        .order_by("-count")[:5]
    )


    recentEntries = thisWeekEvents.order_by("-watched_date")[:5]
    recentMovies = [entry.movie for entry in recentEntries]

    thisWeekCount = thisWeekEvents.count()
    lastWeekCount = lastWeekEvents.count()
    percentChange = calc_percentChange(lastWeekCount, thisWeekCount)

    decadeCounts = byDecadePayload(
        MovieUser.objects.filter(
            user = request.user,
            movie_id__in = week_movie_ids,
        )
    )

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
    allMovies = loadAllTime(request.user)   # Query Set -> MovieUser
    all_movie_ids = allMovies.values_list("movie_id", flat=True)


    topDirectors = (
        Person.objects.filter(
            moviecrew__movie_id__in=all_movie_ids,
            moviecrew__job="Director",
        ).annotate(count=models.Count("moviecrew__movie",distinct=True))
        .order_by("-count")[:5]
    )

    topActors = (
        Person.objects.filter(
            moviecast__movie_id__in=all_movie_ids,
        ).annotate(count=models.Count("moviecast__movie",distinct=True))
        .order_by("-count")[:5]
    )

    topGenres = (
        Genre.objects.filter(moviegenre__movie_id__in=all_movie_ids)
        .annotate(count=models.Count("moviegenre__movie",distinct=True))
        .order_by("-count")[:5]
    )

    recentEntries = (
        allMovies.select_related("movie")
        .exclude(movie__isnull=True)
        .order_by("-watched_date", "-id")[:5]
    )
    recentMovies = [entry.movie for entry in recentEntries]

    totalCount = allMovies.count()
    decadeCounts = byDecadePayload(allMovies)

    # New stat - total lifetime watch time (minutes)
    agg = allMovies.aggregate(
        total_minutes=Coalesce(Sum("movie__runtime"),0),
        runtime_movies = models.Count(
            "movie_id",
            filter=models.Q(movie__runtime__isnull=False),
            distinct=True,
        ),
    )
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