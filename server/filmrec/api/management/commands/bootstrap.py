import os
from django.contrib.auth import get_user_model
from django.db import transaction

def run():
    User = get_user_model()

    username = os.environ.get("BOOTSTRAP_USERNAME", "test@example.com")
    email = os.environ.get("BOOTSTRAP_EMAIL", "test@example.com")
    password = os.environ.get("BOOTSTRAP_PASSWORD", "test123!")

    if not User.objects.filter(username=username).exists():
        print("Creating bootstrap user...")
        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
    else:
        print("Bootstrap user already exists.")

    print("Bootstrap finished.")