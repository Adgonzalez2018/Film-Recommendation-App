"""
=========================================================================================
================================== SERIALIZER ===========================================
=========================================================================================
"""

from rest_framework import serializers
from .models import Movie, User, Genre, Person, FilmBank
from django.contrib.auth import get_user_model
from .utils.unifiedImportHelper import extract_letterboxd_username

User = get_user_model()

"""
--- USER SERIALIZER ---
Create User
    - Username/Email (Same thing)
    - Password
"""
class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 
                  'first_name',
                  'email', 
                  'password',
                  ]

    def create(self,validated_data):
        user = User.objects.create_user(
            username=validated_data["email"],
            email=validated_data["email"],
            first_name=validated_data.get("first_name", ""),
            password=validated_data["password"],
        )
        return user

"""
--- LOGIN SERIALIZER ---
Login
    - Email
    - Password
"""
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        style={'input_type': 'password'},
        write_only=True,
    )

"""
--- REGISTER SERIALIZER ---
Login
    - Email
    - Password
    - Verify Password
"""
class RegistrationSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        style = {'input_type': 'password'},
        write_only = True
    )

    class Meta:
        model = User
        fields = ["first_name", "email", "password"]
    
    def validate_email(self, value):
        value = (value or "").strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value
    
    def create(self, validated_data):
        email = (validated_data["email"] or "").strip().lower()
        user = User.objects.create_user(
            username=email,
            first_name=validated_data.get("first_name", ""),
            email=email,
            password=validated_data["password"],
        )
        return user
    
"""
--- PROFILE SERIALIZER ---
Load Profile
    - Letterboxd Name (RSS)
    - Birthday (if given)
    - Imports
        - rss, manual sync
        - last general sync
        - import counts
"""
class ProfileSerializer(serializers.ModelSerializer):
    letterboxd_username = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    birthday = serializers.DateField(required=False, allow_null=True)
    rss = serializers.CharField(required=False, allow_blank=True, write_only=True)
    
    has_letterboxd_link = serializers.SerializerMethodField()
    has_imports = serializers.SerializerMethodField()
    manual_import_count = serializers.SerializerMethodField()
    rss_import_count = serializers.SerializerMethodField()
    last_sync = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", 
                  "first_name", 
                  "email",
                  "letterboxd_username",
                  "birthday",
                  "rss",
                  "has_letterboxd_link",
                  "has_imports",
                  "manual_import_count",
                  "rss_import_count",
                  "last_sync",
                  ]
        read_only_fields = [
            "id",
            "email",
            "has_letterboxd_link",
            "has_imports",
            "manual_import_count",
            "rss_import_count",
            "last_sync",
        ]

    def update(self, instance, validated_data):
        rss_input = (validated_data.pop("rss","") or "").strip()
        if rss_input:
            username = extract_letterboxd_username(rss_input)
            if not username:
                raise serializers.ValidationError({"rss": "Invalid Letterboxd RSS/profile input."})
            instance.letterboxd_username = username
        # normal updates (first_name, letterboxd_username, etc)
        return super().update(instance, validated_data)
    
    def get_has_imports(self, obj):
        return (obj.manual_import_count or 0) > 0 or (obj.rss_import_count or 0) > 0
    
    def get_has_letterboxd_link(self, obj):
        return bool(getattr(obj, "letterboxd_username", None))

    def get_manual_import_count(self, obj):
        return obj.manual_import_count or 0
    
    def get_rss_import_count(self, obj):
        return obj.rss_import_count or 0
    
    def get_last_sync(self, obj):
        return obj.last_sync.isoformat() if obj.last_sync else None


"""
=========================================================================================
================================ MOVIE CORPUS ===========================================
=========================================================================================

--- MOVIE SERIALIZER ---
Nothing really needed here
"""
class MovieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Movie
        fields = '__all__'

"""
--- PERSON SERIALIZER ---
For Actors/Directors
Load in person
Used for STATS FEATURE
"""
class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = '__all__'

"""
--- GENRE SERIALIZER ---
For Movie's Genre
Load in genre
Used for STATS FEATURE
"""
class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = '__all__'


"""
=========================================================================================
================================ CHAT ===================================================
=========================================================================================
"""
"""
Load in messages from user to send to the Film Recommender
"""
class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField()

"""
FILMBANK SERIALIZER
Get Film Recommender's reasoning
"""
class FilmBankSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="movie.id", read_only=True)
    title = serializers.CharField(source="movie.title", read_only=True)
    tmdb_id = serializers.IntegerField(source="movie.tmdb_id", read_only=True)
    year = serializers.IntegerField(source="movie.year", allow_null=True, read_only=True)
    poster_url = serializers.URLField(source="movie.poster_url", allow_null=True, read_only=True)
    description = serializers.CharField(source="movie.overview", allow_null=True, read_only=True)
    avg_rating = serializers.FloatField(source="movie.avg_rating", allow_null=True, read_only=True)
    why = serializers.CharField(source="reason", allow_null=True, read_only=True)
    class Meta:
        model = FilmBank
        fields = [
            "id",
            "title",
            "tmdb_id",
            "year",
            "poster_url",
            "description",
            "avg_rating",
            "why",
            "query_text",
            "created_at",
            "dismissed_at",
        ]
        read_only_fields = [
            "id",
            "movie",
            "reason",
            "created_at",
        ]

"""
--- MOVIECARD SERIALIZER ---
Used by FilmBank
    - id
    - title
    - year
    - poster url
    - avg rating
    - description
NEED TO ADD LETTERBOXD URL
"""
class MovieCardSerializer(serializers.ModelSerializer):
    description = serializers.CharField(source="overview", allow_null=True, required=False)
    class Meta:
        model = Movie
        fields = [
            "id",
            "title",
            "year",
            "poster_url",
            "tmdb_id",
            "avg_rating",
            "description",
        ]