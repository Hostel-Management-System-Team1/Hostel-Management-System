from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from .testutils import PASSWORD, login

User = get_user_model()
R = User.Role


def current_code(device):
    return f"{TOTP(device.bin_key, device.step, device.t0, device.digits).token():06d}"


class PasswordStorageTests(TestCase):
    @override_settings(
        PASSWORD_HASHERS=[
            "django.contrib.auth.hashers.Argon2PasswordHasher",
            "django.contrib.auth.hashers.PBKDF2PasswordHasher",
        ]
    )
    def test_passwords_are_stored_as_salted_argon2_hashes(self):
        a = User.objects.create_user(username="r1", password=PASSWORD)
        b = User.objects.create_user(username="r2", password=PASSWORD)
        self.assertTrue(a.password.startswith("argon2$"))
        self.assertNotIn(PASSWORD, a.password)
        self.assertNotEqual(a.password, b.password)  # same password, different salt
        self.assertTrue(a.check_password(PASSWORD))


class SessionTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="r1", password=PASSWORD)

    def test_idle_session_lasts_fifteen_minutes(self):
        from django.conf import settings

        self.assertEqual(settings.SESSION_COOKIE_AGE, 15 * 60)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)  # the clock restarts on each request

    def test_session_idle_past_fifteen_minutes_is_rejected(self):
        login(self.client, "r1")
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        Session.objects.update(expire_date=timezone.now() - timedelta(seconds=1))
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, f"{reverse('login')}?next=/")

    def test_each_request_extends_the_session(self):
        login(self.client, "r1")
        Session.objects.update(expire_date=timezone.now() + timedelta(minutes=1))
        self.client.get(reverse("home"))
        expires = Session.objects.get().expire_date
        self.assertGreater(expires, timezone.now() + timedelta(minutes=14))

    def test_logout_invalidates_the_session_token(self):
        login(self.client, "r1")
        cookie = self.client.cookies["sessionid"].value
        self.client.post(reverse("logout"))
        self.assertFalse(Session.objects.filter(session_key=cookie).exists())
        # Replaying the old cookie gets nothing.
        self.client.cookies["sessionid"] = cookie
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, f"{reverse('login')}?next=/")


class MFATests(TestCase):
    def setUp(self):
        self.warden = User.objects.create_user(username="w1", password=PASSWORD, role=R.WARDEN)
        self.resident = User.objects.create_user(username="r1", password=PASSWORD)

    def test_residents_do_not_need_a_second_step(self):
        login(self.client, "r1")
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_warden_with_only_a_password_is_held_at_the_second_step(self):
        self.client.login(username="w1", password=PASSWORD)
        response = self.client.get(reverse("home"))
        self.assertRedirects(
            response, f"{reverse('mfa')}?next=/", fetch_redirect_response=False
        )

    def test_api_refuses_a_half_signed_in_warden(self):
        self.client.login(username="w1", password=PASSWORD)
        response = self.client.get("/api/v1/me")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["message"], "Multi-factor verification required.")

    def test_first_sign_in_links_an_authenticator_app(self):
        self.client.login(username="w1", password=PASSWORD)
        page = self.client.get(reverse("mfa"))
        self.assertContains(page, "Set up your authenticator app")
        self.assertContains(page, "<svg")  # the QR code
        device = TOTPDevice.objects.get(user=self.warden)
        self.assertFalse(device.confirmed)

        ok = self.client.post(reverse("mfa"), {"token": current_code(device), "next": "/"})
        self.assertRedirects(ok, "/", fetch_redirect_response=False)
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_later_sign_ins_ask_for_the_code_only(self):
        device = TOTPDevice.objects.create(user=self.warden, name="phone", confirmed=True)
        self.client.login(username="w1", password=PASSWORD)
        page = self.client.get(reverse("mfa"))
        self.assertContains(page, "Enter your code")
        self.assertNotContains(page, "<svg")
        self.client.post(reverse("mfa"), {"token": current_code(device)})
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_wrong_code_does_not_let_the_warden_in(self):
        TOTPDevice.objects.create(user=self.warden, name="phone", confirmed=True)
        self.client.login(username="w1", password=PASSWORD)
        response = self.client.post(reverse("mfa"), {"token": "123456"})
        self.assertContains(response, "That code is not right")
        self.assertEqual(self.client.get(reverse("home")).status_code, 302)

    def test_guessing_is_throttled(self):
        device = TOTPDevice.objects.create(user=self.warden, name="phone", confirmed=True)
        self.client.login(username="w1", password=PASSWORD)
        self.client.post(reverse("mfa"), {"token": "123456"})
        # Even the right code is refused straight after a wrong one.
        response = self.client.post(reverse("mfa"), {"token": current_code(device)})
        self.assertContains(response, "That code is not right")

    def test_administrator_also_needs_the_second_step(self):
        User.objects.create_superuser(username="a1", password=PASSWORD)
        self.client.login(username="a1", password=PASSWORD)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("mfa"), response["Location"])

    def test_open_redirect_is_ignored(self):
        device = TOTPDevice.objects.create(user=self.warden, name="phone", confirmed=True)
        self.client.login(username="w1", password=PASSWORD)
        response = self.client.post(
            reverse("mfa"), {"token": current_code(device), "next": "https://evil.example/"}
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_sign_out_is_possible_before_the_second_step(self):
        self.client.login(username="w1", password=PASSWORD)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("home")).status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(DEBUG=True)
    def test_totp_code_command_gives_the_current_code(self):
        from io import StringIO

        from django.core.management import call_command

        device = TOTPDevice.objects.create(user=self.warden, name="phone", confirmed=True)
        out = StringIO()
        call_command("totp_code", "w1", stdout=out)
        self.assertEqual(out.getvalue().strip(), current_code(device))


class ApiTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="r1", password=PASSWORD)
        User.objects.create_superuser(username="a1", password=PASSWORD)

    def test_unauthenticated_api_call_is_refused_with_the_error_envelope(self):
        response = self.client.get("/api/v1/me")
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(
            set(body), {"timestamp", "path", "status", "error", "message", "traceId"}
        )
        self.assertEqual((body["status"], body["path"]), (403, "/api/v1/me"))
        self.assertEqual(body["traceId"], response["X-Trace-Id"])

    def test_me_returns_the_callers_role_and_no_password(self):
        login(self.client, "r1")
        body = self.client.get("/api/v1/me").json()
        self.assertEqual((body["username"], body["role"]), ("r1", "RESIDENT"))
        self.assertNotIn("password", body)

    def test_user_list_is_for_administrators_only(self):
        login(self.client, "r1")
        self.assertEqual(self.client.get("/api/v1/users").status_code, 403)
        self.client.logout()
        login(self.client, "a1")
        response = self.client.get("/api/v1/users")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_unknown_api_path_is_a_404_page_not_a_stack_trace(self):
        login(self.client, "r1")
        self.assertEqual(self.client.get("/api/v1/nothing-here").status_code, 404)
