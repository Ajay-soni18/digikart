"""Auth flow tests: Google-only sign-in/sign-up, single-device sessions, logout.

Google token verification is mocked everywhere (we never call Google in tests).
We patch the verifier at its two boundaries:
  - apps.accounts.views.verify_google_id_token  → exercises the HTTP endpoint,
  - apps.accounts.google.google_id_token.verify_oauth2_token → exercises the
    real verify_google_id_token() checks (issuer / email_verified).
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from .google import GoogleAuthError, GoogleNotConfigured, verify_google_id_token
from .models import User

GOOGLE_URL = "/api/v1/auth/google/"


def fake_idinfo(**overrides):
    """A verified Google ID-token payload (claims dict), tweakable per test."""
    info = {
        "sub": "google-sub-1",
        "email": "a@example.com",
        "email_verified": True,
        "name": "Aisha Khan",
        "given_name": "Aisha",
        "family_name": "Khan",
        "picture": "https://lh3.googleusercontent.com/a/pic",
        "iss": "https://accounts.google.com",
    }
    info.update(overrides)
    return info


class GoogleLoginEndpointTests(TestCase):
    def setUp(self):
        cache.clear()  # reset throttle counters between tests
        self.client = APIClient()

    @patch("apps.accounts.views.verify_google_id_token")
    def test_new_account_created_and_logged_in(self, mock_verify):
        mock_verify.return_value = fake_idinfo()
        res = self.client.post(GOOGLE_URL, {"credential": "tok"}, format="json")

        self.assertEqual(res.status_code, 201)  # brand-new account
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertEqual(res.data["user"]["email"], "a@example.com")
        self.assertEqual(res.data["user"]["first_name"], "Aisha")
        self.assertEqual(res.data["user"]["last_name"], "Khan")
        self.assertFalse(res.data["user"]["is_admin"])
        mock_verify.assert_called_once_with("tok")

        user = User.objects.get(email="a@example.com")
        self.assertEqual(user.google_sub, "google-sub-1")
        # Google accounts have NO usable password (can't be used for password login).
        self.assertFalse(user.has_usable_password())

    @patch("apps.accounts.views.verify_google_id_token")
    def test_returning_user_logs_in_without_duplicate(self, mock_verify):
        mock_verify.return_value = fake_idinfo()
        first = self.client.post(GOOGLE_URL, {"credential": "tok"}, format="json")
        self.assertEqual(first.status_code, 201)

        second = self.client.post(GOOGLE_URL, {"credential": "tok-again"}, format="json")
        self.assertEqual(second.status_code, 200)  # returning user, not "created"
        self.assertEqual(User.objects.filter(email="a@example.com").count(), 1)
        self.assertEqual(User.objects.count(), 1)

    @patch("apps.accounts.views.verify_google_id_token")
    def test_google_login_links_existing_staff_account(self, mock_verify):
        """An admin created locally (createsuperuser) signs in with the same
        Google email → the account is linked, stays staff, and is NOT duplicated.
        This is how staff reach the React admin dashboard."""
        staff = User.objects.create_superuser(
            email="boss@example.com", full_name="Boss", password="Strong@1234"
        )
        mock_verify.return_value = fake_idinfo(
            sub="sub-boss", email="boss@example.com",
            name="Boss Person", given_name="Boss", family_name="Person",
        )
        res = self.client.post(GOOGLE_URL, {"credential": "tok"}, format="json")

        self.assertEqual(res.status_code, 200)  # pre-existing account
        self.assertTrue(res.data["user"]["is_admin"])
        staff.refresh_from_db()
        self.assertEqual(staff.google_sub, "sub-boss")
        self.assertEqual(staff.last_name, "Person")  # blank field back-filled
        self.assertEqual(User.objects.filter(email="boss@example.com").count(), 1)

    @patch("apps.accounts.views.verify_google_id_token")
    def test_first_last_derived_from_full_name(self, mock_verify):
        mock_verify.return_value = fake_idinfo(
            given_name=None, family_name=None, name="Jane Mary Doe"
        )
        res = self.client.post(GOOGLE_URL, {"credential": "tok"}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["user"]["first_name"], "Jane")
        self.assertEqual(res.data["user"]["last_name"], "Mary Doe")

    @patch("apps.accounts.views.verify_google_id_token")
    def test_invalid_token_rejected_401(self, mock_verify):
        mock_verify.side_effect = GoogleAuthError("Could not verify your Google sign-in.")
        res = self.client.post(GOOGLE_URL, {"credential": "bad"}, format="json")
        self.assertEqual(res.status_code, 401)
        self.assertIn("detail", res.data)
        self.assertEqual(User.objects.count(), 0)

    def test_missing_credential_rejected_400(self):
        res = self.client.post(GOOGLE_URL, {}, format="json")
        self.assertEqual(res.status_code, 400)

    @patch("apps.accounts.views.verify_google_id_token")
    def test_not_configured_returns_503(self, mock_verify):
        mock_verify.side_effect = GoogleNotConfigured("no client id")
        res = self.client.post(GOOGLE_URL, {"credential": "tok"}, format="json")
        self.assertEqual(res.status_code, 503)

    @patch("apps.accounts.views.verify_google_id_token")
    def test_me_requires_auth_then_works(self, mock_verify):
        mock_verify.return_value = fake_idinfo()
        login = self.client.post(GOOGLE_URL, {"credential": "tok"}, format="json")
        token = login.data["access"]

        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        me = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["email"], "a@example.com")
        self.assertNotIn("phone", me.data)  # phone is fully gone

    def test_no_password_login_or_register_endpoints(self):
        """The old email/password endpoints no longer exist (Google-only)."""
        self.assertEqual(
            self.client.post("/api/v1/auth/login/", {"email": "x@y.z", "password": "p"}, format="json").status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/api/v1/auth/register/", {"email": "x@y.z"}, format="json").status_code,
            404,
        )


class GoogleTokenVerificationTests(TestCase):
    """Exercise the real verify_google_id_token() guards (mocking only Google's
    library call, so our issuer / email_verified checks actually run)."""

    @patch("apps.accounts.google.google_id_token.verify_oauth2_token")
    def test_valid_token_returns_claims(self, mock_v):
        mock_v.return_value = fake_idinfo()
        info = verify_google_id_token("tok")
        self.assertEqual(info["email"], "a@example.com")

    @patch("apps.accounts.google.google_id_token.verify_oauth2_token")
    def test_unverified_email_rejected(self, mock_v):
        mock_v.return_value = fake_idinfo(email_verified=False)
        with self.assertRaises(GoogleAuthError):
            verify_google_id_token("tok")

    @patch("apps.accounts.google.google_id_token.verify_oauth2_token")
    def test_bad_issuer_rejected(self, mock_v):
        mock_v.return_value = fake_idinfo(iss="https://evil.example.com")
        with self.assertRaises(GoogleAuthError):
            verify_google_id_token("tok")

    @patch("apps.accounts.google.google_id_token.verify_oauth2_token")
    def test_library_value_error_becomes_auth_error(self, mock_v):
        mock_v.side_effect = ValueError("Token expired")
        with self.assertRaises(GoogleAuthError):
            verify_google_id_token("tok")

    def test_empty_credential_rejected(self):
        with self.assertRaises(GoogleAuthError):
            verify_google_id_token("")


class CreateSuperuserTests(TestCase):
    def test_create_superuser_without_phone(self):
        """createsuperuser (email + full_name + password, no phone) still works
        so Django's own admin keeps functioning."""
        u = User.objects.create_superuser(
            email="root@example.com", full_name="Root", password="Strong@1234"
        )
        self.assertTrue(u.is_staff)
        self.assertTrue(u.is_superuser)
        self.assertTrue(u.check_password("Strong@1234"))
        self.assertIsNone(u.google_sub)


class SingleSessionTests(TestCase):
    """One active device per account: a new login kills the previous one. Logins
    go through the Google endpoint (verifier mocked) for the same Google user."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        patcher = patch("apps.accounts.views.verify_google_id_token")
        self.mock_verify = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_verify.return_value = fake_idinfo(sub="dev-sub", email="d@example.com")

    def login(self):
        res = self.client.post(GOOGLE_URL, {"credential": "tok"}, format="json")
        return res.data["access"], res.data["refresh"]

    def me(self, access):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return c.get("/api/v1/auth/me/")

    def test_new_login_logs_out_old_device(self):
        a1, _ = self.login()              # device 1
        self.assertEqual(self.me(a1).status_code, 200)
        a2, _ = self.login()              # device 2 logs in
        self.assertEqual(self.me(a1).status_code, 401)  # device 1 evicted
        self.assertEqual(self.me(a2).status_code, 200)

    def test_old_refresh_token_rejected_after_new_login(self):
        _, r1 = self.login()
        self.login()  # new device
        res = self.client.post("/api/v1/auth/token/refresh/", {"refresh": r1}, format="json")
        self.assertEqual(res.status_code, 401)

    def test_logout_ends_session_immediately(self):
        a, r = self.login()
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {a}")
        self.assertEqual(
            c.post("/api/v1/auth/logout/", {"refresh": r}, format="json").status_code, 205
        )
        self.assertEqual(self.me(a).status_code, 401)
