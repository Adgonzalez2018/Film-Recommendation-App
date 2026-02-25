"""
Endpoint to inject TMDB movie database

Dependent on tmdb.py
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from ..services.tmdb import search_movie, upsert_tmdb_movie

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tmdb_search(request):
    query = request.GET.get("q")
    if not query:
        return Response({"error": "Missing query"}, status=status.HTTP_400_BAD_REQUEST)
    
    data = search_movie(query)
    results = []

    for r in data.get("results",[])[:5]:
        results.append({
            "tmdb_id": r["id"],
            "title": r["title"],
            "year": r.get("release_date", "")[:4],
            "poster_url": f"https://image.tmdb.org/t/p/w200{r['poster_path']}" if r.get("poster_path") else None,
        })

    return Response({"results": results})

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def tmdb_ensure(request):
    tmdb_id = request.data.get("tmdb_id")
    if not tmdb_id:
        return Response({"error": "Missing tmdb_id"}, status=status.HTTP_400_BAD_REQUEST)
    
    movie = upsert_tmdb_movie(tmdb_id)
    return Response({
        "id": movie.id,
        "title": movie.title,
        "poster_url": movie.poster_url,
        "tmdb_id": movie.tmdb_id,
    })