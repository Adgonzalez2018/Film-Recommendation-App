# api/views/profile_views.py
"""
Endpoints for Profile.js
Loads Profile Info

Gives User another chance to Manually Import Or Add their RSS Link
Allows User to give Birthday, and First Name
"""
import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from ..serializer import ProfileSerializer

logger = logging.getLogger(__name__)

# Read Profile
@api_view(["GET","PATCH"])
@permission_classes([IsAuthenticated])
def profileView(request):
    user = request.user
    try:
        if request.method == "GET":
           logger.info("PROFILE GET User=%s", user.id)
           data = ProfileSerializer(user).data
           logger.info("PROFILE GET success user=%s", user.id)
           return Response(data, status=status.HTTP_200_OK)
        
        # PATCH
        logger.info("PROFILE PATCH user=%s payload =%s", user.id, request.data)
        # if update then reset last sync and their taste summer store id
        if "rss" in request.data:
            logger.info("PROFILE PATCH rss reset user=%s", user.id)

            user.taste_vector_store_id = None
            user.last_sync = None
            user.save(update_fields=["taste_vector_store_id", "last_sync"])
        # store new data in profile serializer
        serializer = ProfileSerializer(user, data=request.data, partial=True)

        if not serializer.is_valid():
            logger.warning(
                "PROFILE PATCH Validation failed user=%s errors=%s",
                user.id,
                serializer.errors,
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        logger.info("PROFILE PATCH success user=%s", user.id)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.exception("PROFILE VIEW ERROR user=%s error=%s", user.id, str(e))
        return Response(
            {"error": "Profile service failed."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
