from django.contrib.auth import get_user_model
from api.models import WatchEvent, MovieUser, FilmBank, ImportBatch

User = get_user_model()

def reset_user_app_date(user):
    WatchEvent.objects.filter(user=user).delete()
    MovieUser.objects.filter(user=user).delete()
    FilmBank.objects.filter(user=user).delete()
    ImportBatch.objects.filter(user=user).delete()

    user.manual_import_count = 0
    user.rss_import_count = 0
    user.last_sync = None
    user.last_manual_sync = None
    user.last_rss_sync = None
    user.last_rss_account_switch = None
    user.letterboxd_username = ""
    user.taste_vector_store_id = None
    user.has_skipped_onboarding = False
    user.save(update_fields=[
        "manual_import_count",
        "rss_import_count",
        "last_sync",
        "last_manual_sync",
        "last_rss_sync",
        "last_rss_account_switch",
        "letterboxd_username",
        "taste_vector_store_id",
    ])