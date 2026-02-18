from django.contrib.auth import authenticate

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt import tokens

from ..serializer import LoginSerializer, RegistrationSerializer


def get_user_tokens(user):
    refresh = tokens.RefreshToken.for_user(user)
    return {"access_token": str(refresh.access_token)}


@api_view(["POST"])
@permission_classes([AllowAny])
def loginView(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    username = serializer.validated_data["username"]
    password = serializer.validated_data["password"]
    user = authenticate(username=username, password=password)

    if user is None:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    return Response(get_user_tokens(user), status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def registerView(request):
    serializer = RegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response(get_user_tokens(user), status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ping(request):
    user = request.user
    return Response({"username": user.username, "id": user.id}, status=status.HTTP_200_OK)
