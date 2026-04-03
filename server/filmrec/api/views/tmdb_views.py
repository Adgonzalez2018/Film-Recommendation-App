# api/views/tmdb_views.py
"""
Endpoint to inject TMDB movie database
TMDB ENRICHMENT
used for Asynchronous jobs
If user gives FilmRecommender a movie that we DONT KNOW -> Find it and enrich it inside our DB
Dependent on tmdb.py
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from django.core.exceptions import ValidationError

from ..services.tmdb import search_movie, upsert_tmdb_movie, attach_tmdb_to_movie

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tmdb_search(request):
    query = request.GET.get("q")

    if not query:
        return Response(
            {"error": "Missing query"}, 
            status=status.HTTP_400_BAD_REQUEST,
            )
    
    try:
        data = search_movie(query)
    except Exception as e:
        return Response(
            {"error": f"TMDB search failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    results = []
    for r in data.get("results",[])[:5]:
        # added catch if no release date
        release_date = r.get("release_date")
        year = release_date[:4] if release_date else None

        results.append({
            "tmdb_id": r["id"],
            "title": r["title"],
            "year": year,
            "poster_url": f"https://image.tmdb.org/t/p/w200{r['poster_path']}" if r.get("poster_path") else None,
        })
    return Response({"results": results})

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def tmdb_ensure(request):
    raw_tmdb_id = request.data.get("tmdb_id")
    raw_movie_id = request.data.get("movie_id") # optional
    if not raw_tmdb_id:
        return Response({"error": "Missing tmdb_id"}, status=status.HTTP_400_BAD_REQUEST)
    # validate ints safely
    try:
        tmdb_id = int(raw_tmdb_id)
    except (TypeError, ValueError):
        return Response({"error": "Invalid tmdb_id"}, status=status.HTTP_400_BAD_REQUEST)
    movie_id = None
    if raw_movie_id:
        try:
            movie_id = int(raw_movie_id)
        except (TypeError, ValueError):
            return Response({"error": "Invalid movie_id"}, status=status.HTTP_400_BAD_REQUEST)
    try:         
        if movie_id:
            movie = attach_tmdb_to_movie(movie_id=movie_id, tmdb_id=tmdb_id)
        else:
            movie = upsert_tmdb_movie(tmdb_id)
    except ValidationError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({
        "id": movie.id,
        "title": movie.title,
        "poster_url": movie.poster_url,
        "tmdb_id": movie.tmdb_id,
    })