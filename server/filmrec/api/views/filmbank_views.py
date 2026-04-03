# api/views/filmbank_views.py
# endpoint for Film Bank 
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from ..models import FilmBank
from ..serializer import FilmBankSerializer

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

    qs = FilmBank.objects.filter(user=request.user).select_related("movie").order_by("-created_at")
    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = qs[start:end]

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
    deleted, _ = FilmBank.objects.filter(
        user=request.user,
        movie_id=movie_id,
    ).delete()

    return Response(
        {"status": "deleted",
         "deleted": deleted}, 
        status=status.HTTP_200_OK
    )