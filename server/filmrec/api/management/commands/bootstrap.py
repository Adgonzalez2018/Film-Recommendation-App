import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction


class Command(BaseCommand):
    help = "Creates a bootstrap superuser if it does not exist"

    def handle(self, *args, **kwargs):
        User = get_user_model()

        username = os.environ.get("BOOTSTRAP_USERNAME", "admin@example.com")
        email = os.environ.get("BOOTSTRAP_EMAIL", "admin@example.com")
        password = os.environ.get("BOOTSTRAP_PASSWORD", "admin123")

        with transaction.atomic():
            if not User.objects.filter(username=username).exists():
                self.stdout.write("Creating bootstrap superuser...")

                User.objects.create_superuser(
                    username=username,
                    email=email,
                    password=password,
                )

                self.stdout.write(self.style.SUCCESS("Bootstrap user created"))
            else:
                self.stdout.write("Bootstrap user already exists")

        self.stdout.write("Bootstrap complete")