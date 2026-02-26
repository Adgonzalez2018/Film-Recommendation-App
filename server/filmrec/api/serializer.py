from rest_framework import serializers
from .models import Movie, User, Genre, MovieUser, MovieGenre, Person, FilmBank
from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth.hashers import make_password
from api.utils.letterboxd import extract_letterboxd_username

User = get_user_model()

# --- User Serializer ---
class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)  # Ensure password is write-only

    class Meta:
        model = User
        fields = ['id', 
                  'first_name',
                  'email', 
                  'password']

# --- Login ---
class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField(
        style={'input_type': 'password'},
        write_only=True
    )

# --- Register --
class RegistrationSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(required=False, allow_blank=False)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        style = {'input_type': 'password'},
        write_only = True
    )

    class Meta:
        model = User
        fields = ["first_name", "email", "password"]
    
    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value
    
    def create(self, validated_data):
        email = validated_data["email"]
        

        user = User.objects.create_user(
            username=email,
            first_name=validated_data.get("first_name", ""),
            email=email,
            password=validated_data["password"],
        )
        return user
    
# --- Profile Page ---
class ProfileSerializer(serializers.ModelSerializer):
    letterboxd_username = serializers.CharField(required=False,allow_blank=True, allow_null=True)
    birthday = serializers.DateTimeField(required=False, allow_null=True)
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
    
    def get_letterboxd_username(self, obj):
        return getattr(obj, "letterboxd_username", None)

    def get_has_imports(self, obj):
        return MovieUser.objects.filter(user=obj).exists()
    
    def get_has_letterboxd_link(self, obj):
        return bool(getattr(obj, "letterboxd_username", None))

    def get_manual_import_count(self, obj):
        return obj.manual_import_count
    
    def get_rss_import_count(self, obj):
        return obj.rss_import_count
    
    def get_last_sync(self, obj):
        return obj.last_sync.isoformat() if obj.last_sync else None


# --- MOVIE CORPUUS --- 
# --- Movie Serializer ---
class MovieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Movie
        fields = '__all__'

    
# --- Person Serializer ---
class ActorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = '__all__'

# --- Genre Serializer ---
class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = '__all__'


# --- CHAT RELATED SERIALIZERS ---
# --- Chat Serializers ---
class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField()

class ChatMovieCardSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    poster_url = serializers.CharField(allow_null=True, required=False)
    tmdb_id = serializers.IntegerField(allow_null=True, required=False)
    

# --- FilmBank Serializer ---
class FilmBankSerializer(serializers.ModelSerializer):
    movie = MovieSerializer(read_only=True)
    class Meta:
        model = FilmBank
        fields = [
            "id",
            "movie",
            "query_text",
            "reason",
            "status",
            "created_at",
            "dismissed_at",
        ]
        read_only_fields = [
            "id",
            "movie",
            "reason",
            "status",
            "created_at",
        ]

class MovieCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Movie
        fields = [
            "id",
            "title",
            "year",
            "poster_url",
            "tmdb_id",
            "avg_rating",
        ]