from rest_framework.test import APITestCase
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

from unittest.mock import patch
from .models import Movie, MovieUser, ImportBatch


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
        r = self.client.post("/api/register/", {
            "email": "statstest@example.com",
            "password": "TestPass123!",
            "first_name": "Stats",
        }, format="json")

        self.assertIn(r.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED])
        self.token = r.data["access_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

        self.user = User.objects.get(email="statstest@example.com")

    def create_movie(self, title, runtime, watched_date):
        movie = Movie.objects.create(
            title=title,
            runtime=runtime,
            year= 2020,
        )

        MovieUser.objects.create(
            user=self.user,
            movie=movie,
            watch_status="Watched",
            watched_date=watched_date
        )
        return movie
    
    def test_weekly_stats(self):
        today = date.today()

        self.create_movie("Movie 1 ", 120, today)
        self.create_movie("Movie 2", 90, today)

        response = self.client.get("/api/stats/weekly/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["totalWatches"], 2)
        self.assertIn("directors", response.data)
        self.assertIn("byDecade", response.data)

    def test_all_time_stats_lifetime_hours(self):
        today = date.today()

        self.create_movie("Movie A ", 120, today)
        self.create_movie("Movie B", 180, today)

        response = self.client.get("/api/stats/all-time/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["totalWatches"], 2)


        lifetime = response.data["totalTimeWatched"]
        self.assertEqual(lifetime["days"], 0)
        self.assertEqual(lifetime["hours"], 5)

    def test_rss_import_endpoint(self):


        response = self.client.post("/api/import/letterboxd/rss/", {
            "rss": "https://letterboxd.com/test/rss"
        }, format="json"
        )

        self.assertIn(response.status_code, [200, 400])

class ImportTests(APITestCase):
    def setUp(self):
        r = self.client.post(
            "/api/register/",
            {
                "email": "importtest@example.com",
                "password": "TestPass123!",
                "first_name": "Import",
            },
            format="json",
        )
        self.assertIn(r.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED])
        token = r.data["access_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.user = User.objects.get(email="importtest@example.com")

    # ---------- helpers ----------
    def _csv_file(self, name="file.csv"):
        return SimpleUploadedFile(
            name,
            b"Name,Year,Letterboxd URI\nTest,2020,https://letterboxd.com/film/test/\n",
            content_type="text/csv",
        )

    def _post_csv_import(self, *, reviews=False, watchlist=False, likes=False, films=False):
        payload = {}
        if reviews:
            payload["reviews"] = self._csv_file("reviews.csv")
        if watchlist:
            payload["watchlist"] = self._csv_file("watchlist.csv")
        if likes:
            payload["likes"] = self._csv_file("likes.csv")
        if films:
            payload["films"] = self._csv_file("films.csv")

        return self.client.post("/api/import/letterboxd/csv/", payload, format="multipart")

    def _latest_csv_batch(self):
        return ImportBatch.objects.filter(user=self.user, source="csv").latest("created_at")

    def _assert_csv_flags(self, *, had_reviews, had_watchlist, had_films):
        batch = self._latest_csv_batch()
        self.assertEqual(batch.had_reviews, had_reviews)
        self.assertEqual(batch.had_watchlist, had_watchlist)
        self.assertEqual(batch.had_films, had_films)

    # ---------- tests ----------
    def test_csv_import_requires_file(self):
        r = self.client.post("/api/import/letterboxd/csv/", {}, format="multipart")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", r.data)

    @patch("api.views.letterboxd_views.run_letterboxd_import")
    def test_csv_import_watchlist_only(self, mock_run):
        mock_run.return_value = {"movies_created": 0, "movies_matched": 0, "rel_created": 0, "rel_updated": 0}

        before = self.user.manual_import_count
        r = self._post_csv_import(watchlist=True)

        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data.get("status"), "ok")
        self._assert_csv_flags(had_reviews=False, had_watchlist=True, had_films=False)

        self.user.refresh_from_db()
        self.assertEqual(self.user.manual_import_count, before + 1)
        self.assertIsNotNone(self.user.last_sync)

    @patch("api.views.letterboxd_views.run_letterboxd_import")
    def test_csv_import_likes_only_maps_to_films(self, mock_run):
        mock_run.return_value = {"movies_created": 0, "movies_matched": 0, "rel_created": 0, "rel_updated": 0}

        r = self._post_csv_import(likes=True)

        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data.get("status"), "ok")
        self._assert_csv_flags(had_reviews=False, had_watchlist=False, had_films=True)

    @patch("api.views.letterboxd_views.run_letterboxd_import")
    def test_csv_import_films_only(self, mock_run):
        mock_run.return_value = {"movies_created": 0, "movies_matched": 0, "rel_created": 0, "rel_updated": 0}

        r = self._post_csv_import(films=True)

        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data.get("status"), "ok")
        self._assert_csv_flags(had_reviews=False, had_watchlist=False, had_films=True)

    @patch("api.views.letterboxd_views.run_letterboxd_import")
    def test_csv_import_watchlist_and_likes_together(self, mock_run):
        mock_run.return_value = {"movies_created": 0, "movies_matched": 0, "rel_created": 0, "rel_updated": 0}

        r = self._post_csv_import(watchlist=True, likes=True)

        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data.get("status"), "ok")
        self._assert_csv_flags(had_reviews=False, had_watchlist=True, had_films=True)

    @patch("api.views.letterboxd_views.run_letterboxd_import")
    def test_csv_import_all_three_together(self, mock_run):
        mock_run.return_value = {"movies_created": 0, "movies_matched": 0, "rel_created": 0, "rel_updated": 0}

        r = self._post_csv_import(reviews=True, watchlist=True, likes=True)

        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data.get("status"), "ok")
        self._assert_csv_flags(had_reviews=True, had_watchlist=True, had_films=True)