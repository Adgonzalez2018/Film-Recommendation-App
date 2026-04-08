import os
from celery import Celery

CELERY_TASK_DEFAULT_QUEUE = "default"

CELERY_TASK_ROUTES = {
    "api.tasks.tmdb_tasks.enrich_movie_from_tmdb": {"queue": "tmdb"},
    "api.tasks.tmdb_tasks.enrich_movie_chunk": {"queue": "tmdb"},

    "api.tasks.taste_tasks.run_init_taste_profile": {"queue": "taste"},
    "api.tasks.taste_tasks.run_rebuild_taste_profile": {"queue": "taste"},
}

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "filmrec.settings")

app = Celery("filmrec")

app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

