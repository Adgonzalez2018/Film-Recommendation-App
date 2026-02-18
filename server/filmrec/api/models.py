from django.db import models
from django.contrib.auth.models import AbstractUser

WATCH_STATUS_CHOICES = [
    ("Watched", "Watched"),
    ("Want to Watch", "Want to Watch"),
    ("Not Interested", "Not Interested"),
]   

"""
Models:
"""
# --- Movie Model ---
class Movie(models.Model):
    title = models.CharField(max_length=255)

    # TMDb attributes
    description = models.TextField(blank=True, null=True)
    release_date = models.DateField(blank=True, null=True)
    avg_rating = models.FloatField(default=0.0, blank=True, null=True)
    
    budget = models.BigIntegerField(blank=True, null=True)
    revenue = models.BigIntegerField(blank=True, null=True)
    runtime = models.BigIntegerField(blank=True, null=True)

    language = models.CharField(max_length=50, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    poster_url = models.URLField(max_length=500, blank=True, null=True)

    # Letterboxd URI
    letterboxd_uri = models.CharField(max_length=500, unique=True, null=True, blank=True)
    # TMDb id
    tmdb_id = models.IntegerField(unique=True, null = True, blank = True)

    def __str__(self):
        return self.title

# --- User Model ---
class User(AbstractUser):
    last_sync = models.DateTimeField(auto_now=True)         # Track when the user last synced their data
    def __str__(self):
        return self.username

# --- Actor Model ---
class Actor(models.Model):
    name = models.CharField(max_length=255)
    birth_date = models.DateField(blank=True, null=True)
    profile_url = models.URLField(max_length=500, blank=True, null=True)
    biography = models.TextField(blank=True, null=True)

# --- Director Model ---
class Director(models.Model):
    name = models.CharField(max_length=255)
    birth_date = models.DateField(blank=True, null=True)
    profile_url = models.URLField(max_length=500, blank=True, null=True)
    biography = models.TextField(blank=True, null=True)

# --- Genre Model ---
class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True)


"""
Relationships:
"""
# --- Movie-User Relationship ---
class MovieUser(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.FloatField(blank=True, null=True)       # User's rating for the movie
    review = models.TextField(blank=True, null=True)        # User's review for the movie
    watch_status = models.CharField(max_length=50, 
                                    choices=WATCH_STATUS_CHOICES)      # e.g., "Watched", "Want to Watch", "Not Interested"
    watched_date = models.DateField(blank=True, null=True)  # Date when the user watched the movie
    liked = models.BooleanField(default=False)              # Whether the user liked the movie or not
    in_watchlist = models.BooleanField(default=False)       # Whether the movie is in the user's watchlist
    rewatch = models.BooleanField(default=False)            # Whether the user has rewatched the movie or not
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['movie', 'user'],
                name='uniq_user_movie',
            )
        ]
        
# --- Movie-Director Relationship ---
class MovieDirector(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    director = models.ForeignKey(Director, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['movie', 'director'], name='uniq_movie_director'
                )
        ]

# --- Movie-Genre Relationship ---
class MovieGenre(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    genre = models.ForeignKey(Genre, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['movie', 'genre'], name='uniq_movie_genre'
                )
        ]

# --- Movie-Actor Relationship ---
class MovieActor(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    actor = models.ForeignKey(Actor, on_delete=models.CASCADE)
    character_name = models.CharField(max_length=255, blank=True, null=True)       # Name of the character played by the actor
    casting_order = models.IntegerField(blank=True,null=True)                   # Order of the actor in the credits

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['movie', 'actor'], name='uniq_movie_actor'
                 )
        ]
# --- Tables ---
