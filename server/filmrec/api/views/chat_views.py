import re
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q

from ..models import Movie, MovieUser, FilmBank, Genres
from ..serializer import ChatRequestSerializer

def _clarify(msg: str) -> str | None:
    m = msg.lower().strip()
    if len(m) < 4:
        return "What kind of movie are you in the mood for (genre, vibe, or a movie you liked)?"
    # "like X" but no title after it
    if "like" in m and len(m.split()) <= 2:
        return "What movie do you want it to feel like? Give me one Title"
    return None

def _parse_intent(msg: str) -> dict:
    m = msg.lower()

    # actor/director naive parse (v1)
    actor = None
    director = None
    if "actor" in m or "with" in m:
        match = re.search(r"(with|starring)\s+([a-z]+(?:\s+[a-z]+){0,2})", m)
    if match:
        actor = match.group(2)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_recommend(request):
    ser = ChatRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    msg = ser.validated_data["message"]

    clarify = _clarify(msg)
    if clarify:
        return Response({"type": "clarify", "assistant": clarify}, status=status.HTTP_200_OK)

    user = request.user
    # Exclusions
    # if in watchlist
    excluded_movie_ids = set(
        MovieUser.objects.filter(user=user, in_watchlist=True).values_list("movie_id", flat=True)
        )
    # if alr watched
    excluded_movie_ids |= set(
        MovieUser.objects.filter(user=user, watch_status="Watched").values_list("movie_id", flat=True)
    )

    # if alr recommended
    excluded_movie_ids |= set(
        FilmBank.objects.filter(user=user).values_list("movie_id", flat=True)
    )

    # candidate pool: movies user hasn't seen, not in watchlist
    candidates = Movie.objects.exclude(id_in=excluded_movie_ids)

    #v