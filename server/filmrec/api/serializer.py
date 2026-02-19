from rest_framework import serializers
from .models import Movie, User, Actor, Director, Genre, MovieUser, MovieDirector, MovieGenre, MovieActor
from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth.hashers import make_password


User = get_user_model()

# --- Movie Serializer ---
class MovieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Movie
        fields = '__all__'

# --- User Serializer ---
class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)  # Ensure password is write-only

    class Meta:
        model = User
        fields = ['id', 
                  'first_name',
                  'email', 
                  'password']

    
class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField(
        style={'input_type': 'password'},
        write_only=True
    )

class RegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        style = {'input_type': 'password'},
        write_only = True
    )
    
    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value
    
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["email"],
            first_name=validated_data["first_name"],
            email=validated_data["email"],
            password=validated_data["password"],
        )
        return user
    
# --- Actor Serializer ---
class ActorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Actor
        fields = '__all__'

# --- Director Serializer ---
class DirectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Director
        fields = '__all__'

# --- Genre Serializer ---
class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = '__all__'

