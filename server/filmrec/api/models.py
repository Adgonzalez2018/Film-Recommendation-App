from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

WATCH_STATUS_CHOICES = [
    ("Watched", "Watched"),
    ("Want to Watch", "Want to Watch"),
    ("Not Interested", "Not Interested"),
]   

"""
=========================================================================================
================================== MODELS ===============================================
=========================================================================================

--- MOVIE MODEL ---
Attributes:
    - tmdb id
    - title
    - year (release date)
    - overview (synopsis)
    - language (that it's in)
    - budget   (how much it cost)
    - runtime
    - revenue
    - country  (where it was made)
    - poster/letterboxd url
    - Vector store id (index)
"""
class Movie(models.Model):
    title = models.CharField(max_length=255)

    # TMDb attributes
    tmdb_id = models.IntegerField(unique=True, db_index=True, null=True)
    year = models.IntegerField(blank=True, null=True)
    overview = models.TextField(blank=True, null=True)
    avg_rating = models.FloatField(default=0.0, blank=True, null=True)
    
    budget = models.BigIntegerField(blank=True, null=True)
    revenue = models.BigIntegerField(blank=True, null=True)
    runtime = models.IntegerField(blank=True, null=True)

    language = models.CharField(max_length=50, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    poster_url = models.URLField(max_length=500, blank=True, null=True)
    # Letterboxd URI
    letterboxd_uri = models.CharField(max_length=500, unique=True, null=True, blank=True)

    # For RAG - Global movie output jsonl
    movie_vector_store_id = models.CharField(max_length=255, blank=True, null=True, unique=True, db_index=True)

    enrichment_status = models.CharField(
        max_length=20,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("queued", "Queued"),
            ("enriching", "Enriching"),
            ("done", "Done"),
            ("failed", "Failed"),
            ("not_found", "Not Found"),
        ]
    )

    enrichment_attempts = models.PositiveIntegerField(default=0)
    last_enriched_at = models.DateTimeField(blank=True, null = True)
    enrichment_error = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.title
    
"""
--- USER MODEL ---

Attr:
    - first_name
    - email
    - password
    - birthday
    - General last sync (for letterboxd data) 
    - manual last sync
    - rss last sync
    - letterboxd username
    - rss/manual import count
    - taste vector store id for user taste summary
"""
class User(AbstractUser):
    last_sync = models.DateTimeField(blank=True,null=True)         # Track when the user last synced their data
    birthday = models.DateField(blank=True,null=True)
    has_skipped_onboarding = models.BooleanField(default=False)

    #letterboxd
    letterboxd_username = models.CharField(max_length=64,blank=True,null=True)
    
    # import & onboarding
    manual_import_count = models.PositiveIntegerField(default=0)
    rss_import_count = models.PositiveIntegerField(default=0)
    last_manual_sync = models.DateTimeField(null=True, blank=True)
    last_rss_sync = models.DateTimeField(null=True, blank=True)
    last_rss_account_switch = models.DateTimeField(null=True, blank=True)

    # RAG - store id for vector store -> goes to LM (for taste summary)
    taste_vector_store_id = models.CharField(max_length=255, blank=True, null=True, unique=True, db_index=True)

    def __str__(self):
        return self.username
    
"""
--- IMPORT BATCH FOR RSS/CSV & TMDB ENRICHMENT JOBS --- 

Such that any user can import using async/synchronous jobs
status updates, source (rss/manual)
csv file paths, rss input
time started/finished
errors (if any)

How many movies created, updated
how many WATCHEVENTS created

This also does TMDB enrichment. Once movies are injected into DB through MovieUser/WatchEvent
movies not in our main movie Corpus are marked for enrichment
if marked for enrichment then (asynrchonously) a worker does the enrichment and finds tmdb data on letterboxd found movies
"""
class ImportBatch(models.Model):
    SOURCE_CHOICES = [
        ("csv", "CSV"),
        ("rss", "RSS"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="import_batches")
    status = models.CharField(max_length=20, default="queued")
    source = models.CharField(max_length=8, choices=SOURCE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)

    # queue payload / debugging
    rss_input = models.CharField(max_length=255, blank=True, null=True)

    # temp uploaded file paths
    watched_path = models.CharField(max_length=500, blank=True,null=True)
    reviews_path = models.CharField(max_length=500, blank=True,null=True)
    watchlist_path = models.CharField(max_length=500, blank=True,null=True)
    films_path = models.CharField(max_length=500, blank=True,null=True)

    # store whatever counters you want (from your importer)
    movies_created = models.IntegerField(default=0)
    movies_matched = models.IntegerField(default=0)
    rel_created = models.IntegerField(default=0)
    rel_updated = models.IntegerField(default=0)
    events_created = models.IntegerField(default=0)

    # enrichments
    tmdb_queued = models.IntegerField(default=0)
    tmdb_done = models.IntegerField(default=0)
    tmdb_failed = models.IntegerField(default=0)
    
    # optional: what files were included
    had_watched_file = models.BooleanField(default=False)
    had_reviews = models.BooleanField(default=False)
    had_watchlist = models.BooleanField(default=False)
    had_films = models.BooleanField(default=False)

    # add to event
    events_created = models.IntegerField(default=0)
    def __str__(self):
        return f"ImportBatch<{self.user_id}:{self.source}:{self.created_at}>"


"""
--- PERSON MODEL ---    

joins Actor & Director model
Person - Director/Actor
    - id
    - name 
    - birth_date
    - profile url
    - biography

Separated by job/crew
Directors are in moviecrew
Actors are in moviecast
"""
class Person(models.Model):
    tmdb_id = models.IntegerField(unique=True, db_index=True, null=True, blank=True)
    name = models.CharField(max_length=255)
    birth_date = models.DateField(blank=True, null=True)
    profile_url = models.URLField(max_length=500, blank=True, null=True)
    biography = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
    


"""
# --- Genre Model ---
Only a small finite amount of Genres with
    - name
    - id
but if new ones are found in the database they get added
"""
class Genre(models.Model):
    tmdb_id = models.IntegerField(unique=True, db_index=True, null=True, blank=True)
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


# --- Watch Event Model ---
"""
--- WATCH EVENTS ---
works hand in hand with Import Batches
finds where the source is coming from
focuses on specifics of when the user watched it 
utilized heavily in STATS FEATURE

Ties user, movie, and watch-date/posted_date together
ties the entry and checks if it's a rewatch
"""
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
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=[
                "user", "event_key"
            ], name="unique_watch_event_user_event_key")
        ]

"""
--- FILMBANK MODEL ---
Only get the bare essentials for the films recommended
Attributes:
    - when it was created
    - User that the movie was given to
    - Movie that was recommended
    - If it's in User's FilmBank
    - If removed by User
    - Film Recommender's Reasoning
"""
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

"""
=========================================================================================
============================ RELATIONSHIPS ==============================================
=========================================================================================

--- MOVIEUSER RELATIONSHIP ---
ties Movie and User with the specifics
Attributes:
    - watched the movie
    - user's rating
    - user's review
    - watch status
    - watched date
    - if in user's watchlist
    - user rewatched True/False
"""
class MovieUser(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="user_links")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="movie_links")
    rating = models.FloatField(blank=True, null=True)       # User's rating for the movie
    review = models.TextField(blank=True, null=True)        # User's review for the movie
    watch_status = models.CharField(max_length=50, 
                                    choices=WATCH_STATUS_CHOICES, 
                                    default="Watched")      # e.g., "Watched", "Want to Watch", "Not Interested"
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
        indexes = [
            models.Index(fields=["user","watch_status","watched_date"]),
        ]
        
"""
--- MOVIECREW RELATIONSHIP ---
more specifically for Directors
Attributes:
    - Director's Movie
    - Director's name/record
    - their job title == "Director"
    - department == "Directing"
"""
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

"""
--- MOVIECAST RELATIONSHIP ---
More specifically for Actors
Attributes:
    - Actor's Movie
    - Actor's name/record
    - Actor's Character name
    - Actor's Order
"""
class MovieCast(models.Model):
    # Cast = actors -> TMDB credits.cast
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    person = models.ForeignKey(Person, on_delete=models.CASCADE)

    character = models.CharField(max_length=255,blank=True, null = True)
    order = models.IntegerField(blank=True, null=True)            
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['movie', 'person'], name='uniq_movie_cast'
                )
        ]

"""
--- MOIVIEGENRE RELATIONSHIP ---
Genres that Movies have
"""
class MovieGenre(models.Model):
    movie = models.ForeignKey("Movie", on_delete=models.CASCADE)
    genre = models.ForeignKey(Genre, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['movie', 'genre'], name='uniq_movie_genre'
                )
        ]