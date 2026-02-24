from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status

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