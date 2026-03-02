"""
Models for Database:
User - base user
Attr:
    - first_name
    - email
    - password
    - birthday
    - last sync (for letterboxd data)
    - letterboxd username
    - rss/manual import count
    
Movie - Attr:
    - id
    - title
    - year
    - overview
    - language
    - budget
    - runtime
    - revenue
    - country
    - poster/letterboxd url

Person - Director/Actor
    - id
    - name 
    - birth_date
    - profile url
    - biography

Genre 
    - name/id
"""

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

import hashlib

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
    tmdb_id = models.IntegerField(blank=True, null=True, unique=True, db_index=True)
    year = models.IntegerField(blank=True, null=True)
    overview = models.TextField(blank=True, null=True)
    avg_rating = models.FloatField(default=0.0, blank=True, null=True)
    
    budget = models.BigIntegerField(blank=True, null=True)
    revenue = models.BigIntegerField(blank=True, null=True)
    runtime = models.BigIntegerField(blank=True, null=True)

    language = models.CharField(max_length=50, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    poster_url = models.URLField(max_length=500, blank=True, null=True)

    # Letterboxd URI
    letterboxd_uri = models.CharField(max_length=500, unique=True, null=True, blank=True)

    # For RAG - Global movie output jsonl
    movie_vector_store_id = models.CharField(null=True, unique=True, db_index=True)

    def __str__(self):
        return self.title

# --- User Model ---
class User(AbstractUser):
    last_sync = models.DateTimeField(blank=True,null=True)         # Track when the user last synced their data
    birthday = models.DateTimeField(blank=True,null=True)
    
    #letterboxd
    letterboxd_username = models.CharField(max_length=64,blank=True,null=True)

    # import tracking
    manual_import_count = models.PositiveIntegerField(default=0)
    rss_import_count = models.PositiveIntegerField(default=0)

    # RAG - store id for vector store -> goes to LM (for taste summary)
    taste_vector_store_id = models.CharField(null=True, unique=True, db_index=True)

    def __str__(self):
        return self.username
    
class ImportBatch(models.Model):
    SOURCE_CHOICES = [
        ("csv", "CSV"),
        ("rss", "RSS"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="import_batches")
    source = models.CharField(max_length=8, choices=SOURCE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    # store whatever counters you want (from your importer)
    movies_created = models.IntegerField(default=0)
    movies_matched = models.IntegerField(default=0)
    rel_created = models.IntegerField(default=0)
    rel_updated = models.IntegerField(default=0)

    # optional: what files were included
    had_reviews = models.BooleanField(default=False)
    had_watchlist = models.BooleanField(default=False)
    had_films = models.BooleanField(default=False)

    # add to event
    events_created = models.IntegerField(default=0)
    def __str__(self):
        return f"ImportBatch<{self.user_id}:{self.source}:{self.created_at}>"

# --- Person Model ---
# joins Actor & Director model
class Person(models.Model):
    tmdb_id = models.IntegerField(unique=True, db_index=True, null=True, blank=True)
    name = models.CharField(max_length=255)
    birth_date = models.DateField(blank=True, null=True)
    profile_url = models.URLField(max_length=500, blank=True, null=True)
    biography = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
    

# --- Genre Model ---
class Genre(models.Model):
    tmdb_id = models.IntegerField(unique=True, db_index=True, null=True, blank=True)
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


# --- Watch Event Model ---
class WatchEvent(models.Model):
    SOURCE_CHOICES = [("rss","RSS"),("csv","CSV"), ("manual","MANUAL")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)

    watched_date = models.DateField(null=True, blank=True, db_index = True)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="rss")
    posted_date = models.DateField(db_index=True)
    entry_url = models.URLField(max_length=500, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    event_key = models.CharField(max_length=40, db_index=True)
    rewatch = models.BooleanField(default=False)
    # best dedupde key if you can get it


    class Meta:
        constraints = [
            models.UniqueConstraint(fields=[
                "user", "event_key"
            ], name="unique_watch_event_user_event_key")
        ]


"""
Relationships:
"""
# --- Movie-User Relationship ---
class MovieUser(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
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
class MovieCrew(models.Model):
    # Crew Roles: TMDB credits.crew
    # Director is just job = "Director"
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)

    job = models.CharField(max_length=64,blank=True, null = True)       # Director
    department = models.CharField(max_length=64, blank=True, null=True) # Directing
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['movie', 'person', 'job'], 
                name='uniq_movie_crew_role'
                )
        ]

# --- Movie-Actor Relationship ---
class MovieCast(models.Model):
    # Cast = actors -> TMDB credits.cast
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)

    character = models.CharField(max_length=64,blank=True, null = True)
    order = models.IntegerField(blank=True, null=True)            
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['movie', 'person'], name='uniq_movie_cast'
                )
        ]

# --- Movie-Genre Relationship ---
class MovieGenre(models.Model):
    movie = models.ForeignKey("Movie", on_delete=models.CASCADE)
    genre = models.ForeignKey(Genre, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['movie', 'genre'], name='uniq_movie_genre'
                )
        ]


# --- Film Bank for Recommended Films ---
class FilmBank(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="film_bank")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="recommended_to")
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default="active")
    dismissed_at = models.DateTimeField(null=True, blank=True)
    # tiny audit trail
    query_text = models.TextField(blank=True, null=True)
    reason = models.TextField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "movie"], name="uniq_reco_user_movie")
        ]
