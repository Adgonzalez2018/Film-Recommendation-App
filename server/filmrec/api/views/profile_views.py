# api/views/profile_views.py
"""
Endpoints for Profile.js
Loads Profile Info
Allows user to set letterboxd rss link
"""

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
    # if update then reset last sync and their taste summer store id
    if "rss" in request.data:
        user.taste_vector_store_id = None
        user.last_sync = None
        user.save(update_fields=["taste_vector_store_id", "last_sync"])

    # store new data in profile serializer
    serializer = ProfileSerializer(user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)
