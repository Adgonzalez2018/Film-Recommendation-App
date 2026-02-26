from rest_framework.test import APITestCase
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.urls import reverse

from unittest.mock import patch
from .models import Movie, MovieUser, Genre, Person
from .utils.dates import week_window_sunday_anchor

from datetime import date

User = get_user_model()

class AuthFlowTests(APITestCase):
    def setUp(self):
        self.email = "apitest@example.com"
        self.password = "TestPass123!"
        self.first_name = "API"

    def test_register_login_ping(self):
        # REGISTER
        r = self.client.post("/api/register/", {
            "email": self.email,
            "password": self.password,
            "first_name": self.first_name,
        }, format="json")
        self.assertIn(r.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED])
        self.assertIn("access_token", r.data)
        token = r.data["access_token"]

        # PING
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        p = self.client.get("/api/ping/")
        self.assertEqual(p.status_code, status.HTTP_200_OK)
        self.assertIn("email", p.data)

        # LOGIN
        self.client.credentials() # clear
        l = self.client.post("/api/login/", {
            "email": self.email,
            "password": self.password,
        }, format="json")
        self.assertEqual(l.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", l.data)

class ProfileTests(APITestCase):
    def _register_and_auth(self):
        r = self.client.post("/api/register/",{
            "email": "profiletest@example.com",
            "password": "TestPass123!",
            "first_name": "Prof",
        }, format="json")
        token = r.data["access_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_get_and_patch_profile(self):
        self._register_and_auth()

        g = self.client.get("/api/profile/")
        self.assertEqual(g.status_code, status.HTTP_200_OK)

        p = self.client.patch("/api/profile/", {"first_name": "New Name"}, format="json")
        self.assertEqual(p.status_code, status.HTTP_200_OK)
        # serializer prob?
        if isinstance(p.data, dict):
            self.assertEqual(p.data.get("first_name"), "New Name")


class StatsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@test.com",
            password="StrongPass123!",
        )

        self.client.login(email="test@test.com",password="StrongPass123!")

    def create_movie(self, title, runtime, watched_date):
        movie = Movie.objects.create(
            title=title,
            runtime=runtime,
            release_date=date(2020,1,1)
        )

        MovieUser.objects.create(
            user=self.user,
            movie=movie,
            watch_status="Watched",
            watched_date=watched_date
        )

        return movie
    
    def test_weekly_stats(self):
        from datetime import timedelta
        today = date.today()

        self.create_movie("Movie 1 ", 120, today)
        self.create_movie("Movie 2", 90, today)

        url = reverse("stats_payload")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["totalWatches"], 2)
        self.assertIn("directors", response.data)
        self.assertIn("byDecade", response.data)

    def test_all_time_stats_lifetime_hours(self):
        today = date.today()

        self.create_movie("Movie A ", 120, today)
        self.create_movie("Movie B", 180, today)

        url = reverse("stats_all_time")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["totalWatches"], 2)

        lifetime = response.data["totalWatches"]
        self.assertEqual(lifetime["days"], 0)
        self.assertEqual(lifetime["dahoursys"], 5)

    def test_rss_import_endpoint(self):
        url = reverse("rss_import")

        response = self.client.post(url, {
            "rss": "https://letterboxd.com/test/rss"
        }, format="json"
        )

        self.assertIn(response.status_code, [200, 400])
"""
class ImportAndStatsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="test@example.com",
            email="test@example.com",
            password="TestPass123!",
        )
        self.client.force_authenticate(user=self.user)

    def test_import_csv_requires_file(self):
        # No Files -> should 400
        r = self.client.post("/api/import/letterboxd/csv/", {}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertin("error", r.data)

        @patch("api.views.letterboxd_views.run_letterboxd_import")
        def test_import_csv_happy_path_logs_batch_and_updates_profile(self, mock_run):
            pass
"""