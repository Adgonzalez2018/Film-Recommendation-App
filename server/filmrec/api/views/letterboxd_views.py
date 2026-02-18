# api/views/letterboxd_views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from ..services.letterboxd_import import run_letterboxd_import


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def letterboxd_import(request):
    reviews_file = request.FILES.get("reviews")
    watchlist_file = request.FILES.get("watchlist")
    films_file = request.FILES.get("films") or request.FILES.get("likes")

    if not reviews_file and not watchlist_file and not films_file:
        return Response(
            {"error": "No files provided. Upload at least one of: reviews, watchlist, films."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    counters = run_letterboxd_import(
        user=request.user,
        reviews_file=reviews_file,
        watchlist_file=watchlist_file,
        films_file=films_file,
    )

    return Response({"status": "ok", **counters}, status=status.HTTP_200_OK)
