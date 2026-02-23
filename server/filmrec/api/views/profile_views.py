# api/views/profile_views.py
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from ..serializer import ProfileSerializer
from ..utils.letterboxd import extract_letterboxd_username

# Read Profile
@api_view(["GET","PATCH"])
@permission_classes([IsAuthenticated])
def profileView(request):
    user = request.user

    if request.method == "GET":
        return Response(ProfileSerializer(user).data, status=status.HTTP_200_OK)
    
    # PATCH
    serializer = ProfileSerializer(user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def profile_set_letterboxd(request):
    """
    PATCH { "rss": "<username or letterboxd url or rss url>" }
    Saves user.profile.letterboxd_username
    """
    rss_input = (request.data.get("rss") or "").strip()
    username = extract_letterboxd_username(rss_input)
    if not username:
        return Response({"error": "Invalid Letterboxd RSS/profile input."}, status=status.HTTP_400_BAD_REQUEST)

    prof = request.user
    prof.letterboxd_username = username
    prof.save(update_fields=["letterboxd_username"])

    return Response(ProfileSerializer(request.user).data, status=status.HTTP_200_OK)