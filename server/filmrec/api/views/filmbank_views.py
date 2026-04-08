# api/views/filmbank_views.py
# endpoint for Film Bank 
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from ..models import FilmBank
from ..serializer import FilmBankSerializer
from ..tasks.taste_tasks import enqueue_feedback_taste_refresh

"""
Upon pressing the FilmBank Button on /Chat
it loads the whole collection of Films recommended to you

NEXT STEPS:
    - Add User Feedback
"""
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def film_bank_list(request):
    """
    Paginated List of FilmBank entries for current user
    Query params:
        - page default 1
        - page_size defualt 20, max 100
    """
    try:
        page = int(request.GET.get("page",1))
    except Exception:
        page = 1
    try:
        page_size = int(request.GET.get("page_size",20))
    except Exception:
        page_size = 20

    page = max(page, 1)
    page_size = min(max(page_size,1),100)

    qs = FilmBank.objects.filter(
        user=request.user,
        dismissed_at__isnull=True,
    ).select_related("movie").order_by("-created_at")
    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = qs[start:end]

    return Response(
        {
            "page": page,
            "page_size": page_size,
            "total": total,
            "results": FilmBankSerializer(items, many=True).data,
        },
        status=status.HTTP_200_OK,
    )

"""
If User wants to remove theres a small X button
"""
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def film_bank_delete(request, movie_id: int):
    # Remove a film from the user's film bank (hard delete)
    fb = FilmBank.objects.filter(
        user=request.user,
        movie_id=movie_id,
        dismissed_at__isnull=True,
    ).first()

    if not fb:
        return Response(
            {"error": "Film not found in Film Bank."},
            status=status.HTTP_404_NOT_FOUND,
        )
    fb.dismissed_at = timezone.now()
    fb.status = "dismissed"
    fb.save(update_fields=["dismissed_at", "status"])

    return Response(
        {"status": "dismissed"},
        status=status.HTTP_200_OK,
    )

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def film_bank_feedback(request, movie_id: int):
    """
    Submit feedback for FilmBank entry and dismiss it from the active bank.
    POST api/film-bank/<movie_id>/feedback/
    """
    rating = request.data.get("rating")
    watched = request.data.get("watched")
    text = (request.data.get("text") or "").strip()

    if rating not in {"good", "neutral", "bad"}:
        return Response({"error": "Invalid rating."}, status=status.HTTP_400_BAD_REQUEST)
    if watched not in {True, False, None}:
        return Response({"error": "Invalid watched value."}, status=status.HTTP_400_BAD_REQUEST)
    
    fb = FilmBank.objects.filter(
        user=request.user,
        movie_id=movie_id,
        dismissed_at__isnull=True,
    ).first()

    if not fb:
        return Response({"error": "Film not found in Film Bank."},status=status.HTTP_404_NOT_FOUND)
    
    fb.feedback_rating = rating
    fb.feedback_watched = watched
    fb.feedback_text = text
    fb.feedback_submitted_at = timezone.now()
    fb.status = "dismissed"
    fb.dismissed_at = timezone.now()
    fb.save(update_fields=[
        "feedback_rating",
        "feedback_watched",
        "feedback_text",
        "feedback_submitted_at",
        "status",
        "dismissed_at",
    ])
    
    taste_action = enqueue_feedback_taste_refresh(
        user_id=request.user.id,
        rating=rating,
        watched=watched,
        text=text,
    )

    return Response({"status": "saved", "taste_action": taste_action}, status=status.HTTP_200_OK)