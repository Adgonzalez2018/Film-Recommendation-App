from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from api.models import WatchEvent, MovieUser, FilmBank, ImportBatch

User = get_user_model()

class Command(BaseCommand):
    help = "Reset all app data for a user"
    def add_arguments(self, parser):
        parser.add_argument("--username", type=str, required=True)
    def handle(self, *args, **opts):
        user = User.objects.get(username=opts["username"])

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
        user.save()

        self.stdout.write(self.style.SUCCESS(f"Reset data for {user.username}"))