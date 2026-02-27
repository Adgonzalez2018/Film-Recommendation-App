# endpoint for Film Bank 
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from ..models import FilmBank
from ..serializer import FilmBankSerializer

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def film_bank_list(request):
    # Return ALL film bank entries for current user
    # newest first
    qs = FilmBank.objects.filter(user=request.user).select_related("movie").order_by("-created_at")
    return Response(
        FilmBankSerializer(qs, many=True).data, 
        status=status.HTTP_200_OK
    )

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def film_bank_delete(request, pk: int):
    # Remove a film from the user's film bank (hard delete)
    try:
        fb = FilmBank.objects.get(pk=pk, user=request.user)

    except FilmBank.DoesNotExist:
        return Response(
            {"error": "Not Found."},
            status=status.HTTP_404_NOT_FOUND
        )

    fb.delete()
    return Response(
        {"status": "deleted"}, 
        status=status.HTTP_200_OK
    )