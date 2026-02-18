from collections import Counter

from django.db import models
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import MovieUser, Director, Actor, Genre
from ..utils.dates import week_window_sunday_anchor  # you already created this


DECADE_ORDER = ["Pre-1960s", "60s", "70s", "80s", "90s", "00s", "10s", "20s"]


def loadWeekly(user, start_date, end_date):
    return MovieUser.objects.filter(
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
    for entry in entries:
        delta = (entry.watched_date.date() - start_date.date()).days
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
    years = movieuser_qs.values_list("movie__release_date__year", flat=True)

    counts = Counter()
    for y in years:
        if y is None:
            continue
        counts[getDecadeLabel(int(y))] += 1

    return [{"label": lab, "count": counts.get(lab, 0)} for lab in DECADE_ORDER]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def stats_payload(request):
    lastWeekStart, lastWeekEnd, thisWeekStart, thisWeekEnd = week_window_sunday_anchor()

    thisWeekMovies = loadWeekly(request.user, thisWeekStart, thisWeekEnd)
    lastWeekMovies = loadWeekly(request.user, lastWeekStart, lastWeekEnd)

    days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    thisWeekArr = calculatePerDay(thisWeekMovies, thisWeekStart)
    lastWeekArr = calculatePerDay(lastWeekMovies, lastWeekStart)

    topDirectors = (
        Director.objects.filter(moviedirector__movie__movieuser__in=thisWeekMovies)
        .annotate(count=models.Count("moviedirector__movie__movieuser", distinct=True))
        .order_by("-count")[:5]
    )

    topActors = (
        Actor.objects.filter(movieactor__movie__movieuser__in=thisWeekMovies)
        .annotate(count=models.Count("movieactor__movie__movieuser", distinct=True))
        .order_by("-count")[:5]
    )

    topGenres = (
        Genre.objects.filter(moviegenre__movie__movieuser__in=thisWeekMovies)
        .annotate(count=models.Count("moviegenre__movie__movieuser", distinct=True))
        .order_by("-count")[:5]
    )

    recentEntries = thisWeekMovies.select_related("movie").order_by("-watched_date")[:5]
    recentMovies = [entry.movie for entry in recentEntries]

    thisWeekCount = thisWeekMovies.count()
    lastWeekCount = lastWeekMovies.count()
    percentChange = calc_percentChange(lastWeekCount, thisWeekCount)

    decadeCounts = byDecadePayload(thisWeekMovies)

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
            "recentFilms": [{"name": m.title} for m in recentMovies],
            "byDecade": decadeCounts,
        },
        status=status.HTTP_200_OK,
    )
