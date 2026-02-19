from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings


from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt import tokens

from ..serializer import LoginSerializer, RegistrationSerializer

User = get_user_model()
token_generator = PasswordResetTokenGenerator()

# create a user token once logged in, store in local storage (frontend)
def get_user_tokens(user):
    refresh = tokens.RefreshToken.for_user(user)
    return {"access_token": str(refresh.access_token)}

# Log in
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


# Registration
@api_view(["POST"])
@permission_classes([AllowAny])
def registerView(request):
    serializer = RegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response(get_user_tokens(user), status=status.HTTP_201_CREATED)


# Ping for Token Authentication
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ping(request):
    user = request.user
    return Response({"username": user.username, "id": user.id}, status=status.HTTP_200_OK)

# Pass Reset Request
@api_view(["POST"])
def password_reset_request(request):
    email = request.data.get("email")

    if not email:
        return Response(
            {"detail": "Email is required."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        # always return success to prevent user enumeration
        return Response(
            {"detail": "If an account exists, a reset link has been sent."}
        )
    
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = token_generator.make_token(user)

    reset_link = f"http://localhost:3000/reset-password/{uid}/{token}/"

    # DEV: print link instead of emailing
    print("PASSWORD RESET LINK:", reset_link)

    # If you want real email sending:
    # send_mail(
    #     subject="Password Reset",
    #     message=f"Click the link to reset your password: {reset_link}",
    #     from_email=settings.DEFAULT_FROM_EMAIL,
    #     recipient_list=[email],
    # )

    return Response(
        {"detail": "If an account exists, a reset link has been sent."}
    )


# Set new password
@api_view(["POST"])
def password_reset_confirm(request):
    uid = request.data.get("uid")
    token = request.data.get("token")
    new_password = request.data.get("new_password")

    # Checks
    # no uid/token/password
    if not uid or not token or not new_password:
        return Response(
            {"detail": "Invalid Request."},
            status=status.HTTP_400_BAD_REQUEST
        )
    # decode it and check
    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response(
            {"detail": "Invalid Request Link."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # check token
    if not token_generator.check_token(user, token):
        return Response(
            {"detail": "Invalid or expired token."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # passed checks save new password
    user.set_password(new_password)
    user.save()

    return Response({"detail": "Password has been reset successfuly."})