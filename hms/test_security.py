"""Security protections that cut across modules (HMS-SR-001, SR-005, SR-006)."""

import os
import re
import subprocess
import sys
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.testutils import PASSWORD, login
from apps.admissions.testutils import allocated_resident, make_resident, make_room

User = get_user_model()
R = User.Role
ROOT = Path(__file__).resolve().parent.parent


def settings_in_production(**env):
    """Settings values as a production process (DJANGO_DEBUG=false) would see them."""
    code = (
        "from hms import settings as s;"
        "print(s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_SECONDS, s.SESSION_COOKIE_SECURE,"
        " s.CSRF_COOKIE_SECURE, getattr(s, 'SECURE_PROXY_SSL_HEADER', None))"
    )
    environment = {**os.environ, "DJANGO_DEBUG": "false", **env}
    environment.pop("HMS_FORCE_HTTPS", None)
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=environment,
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


class TlsSettingsTests(SimpleTestCase):
    """TC-SEC-01: outside development, every connection must be HTTPS."""

    def test_production_forces_https_hsts_and_secure_cookies(self):
        self.assertEqual(settings_in_production(), "True 31536000 True True None")

    def test_development_does_not_force_https(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "from hms import settings as s; "
             "print(s.SECURE_SSL_REDIRECT, s.SESSION_COOKIE_SECURE)"],
            cwd=ROOT, env={**os.environ, "DJANGO_DEBUG": "true"}, capture_output=True, text=True,
            check=True)
        self.assertEqual(result.stdout.strip(), "False False")

    def test_proxy_header_is_trusted_only_when_asked(self):
        out = settings_in_production(HMS_BEHIND_PROXY="true")
        self.assertIn("('HTTP_X_FORWARDED_PROTO', 'https')", out)

    def test_django_deployment_checklist_is_clean(self):
        environment = {**os.environ, "DJANGO_DEBUG": "false", "HMS_BEHIND_PROXY": "true",
                       "DJANGO_SECRET_KEY": "k" * 20 + "".join(chr(65 + i) for i in range(26)) * 2}
        environment.pop("HMS_FORCE_HTTPS", None)
        result = subprocess.run(
            [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
            cwd=ROOT, env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_plain_http_is_redirected_to_https(self):
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].startswith("https://"))

    def test_nginx_example_allows_only_tls_1_2_and_above(self):
        config = (ROOT / "deploy" / "nginx.conf.example").read_text()
        self.assertIn("ssl_protocols TLSv1.2 TLSv1.3;", config)
        self.assertNotRegex(config, r"TLSv1[ ;]|TLSv1\.1|SSLv")
        self.assertNotRegex(config, r"(?i)\b(RC4|3DES|MD5|NULL|EXPORT)\b")


class HeaderTests(TestCase):
    def test_security_headers_on_every_response(self):
        response = self.client.get("/accounts/login/")
        csp = response["Content-Security-Policy"]
        for part in ("default-src 'self'", "object-src 'none'", "frame-ancestors 'none'",
                     "script-src 'self' https://cdn.jsdelivr.net"):
            self.assertIn(part, csp)
        self.assertNotIn("'unsafe-inline'", csp.split("style-src")[0])
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_signed_in_pages_are_not_cached(self):
        make_resident("r1")
        login(self.client, "r1")
        self.assertEqual(self.client.get(reverse("home"))["Cache-Control"], "no-store")


class ContentSecurityPolicyCompatibilityTests(TestCase):
    """The CSP blocks inline script, so no page may depend on any."""

    def test_no_page_has_inline_script_or_event_handlers(self):
        User.objects.create_user(username="warden0", password=PASSWORD, role=R.WARDEN)
        allocated_resident("r1", room=make_room())
        for role, username in ((R.GATE if hasattr(R, "GATE") else R.SECURITY_GUARD, "g1"),
                               (R.MAINTENANCE_STAFF, "m1"), (R.MESS_MANAGER, "ms1")):
            make_resident(username, role=role)
        User.objects.create_superuser(username="a1", password=PASSWORD)
        pages = {
            "r1": ["/", "/application/", "/fees/", "/profile/"],
            "warden0": ["/", "/applications/", "/rooms/", "/residents/"],
            "g1": ["/"], "m1": ["/"], "ms1": ["/"],
            "a1": ["/admin/", "/admin/admissions/room/", "/admin/accounts/user/",
                   "/admin/audit/auditentry/"],
        }
        for username, paths in pages.items():
            self.client.logout()
            login(self.client, username)
            for path in paths:
                with self.subTest(user=username, path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200, path)
                    html = response.content.decode()
                    inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.+?)</script>", html, re.S)
                    self.assertEqual([i for i in inline if i.strip()], [], path)
                    self.assertNotRegex(html, r"\son[a-z]+=\"", path)
                    self.assertNotIn("javascript:", html, path)


class InputHandlingTests(TestCase):
    """HMS-SR-006 / TC-SEC-06: hostile input is refused or shown as plain text."""

    def setUp(self):
        self.user = make_resident("r1", first_name="Aarav")
        login(self.client, "r1")

    def test_markup_in_a_name_is_refused(self):
        response = self.client.post(reverse("profile"), {
            "first_name": "<script>alert(1)</script>", "last_name": "S",
            "email": "a@example.edu", "phone": "9876543210"})
        self.assertContains(response, "Angle brackets are not allowed")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Aarav")

    def test_a_bad_phone_number_is_refused(self):
        response = self.client.post(reverse("profile"), {
            "first_name": "A", "last_name": "S", "email": "a@example.edu", "phone": "abc"})
        self.assertContains(response, "Enter 10 to 15 digits")

    def test_stored_markup_is_escaped_on_every_page(self):
        # Even if markup reached the database some other way, pages print it as text.
        User.objects.filter(pk=self.user.pk).update(first_name="<img src=x onerror=alert(1)>")
        for path in ("/", "/profile/"):
            html = self.client.get(path).content.decode()
            self.assertNotIn("<img src=x onerror", html, path)
            self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html, path)

    def test_sql_injection_in_search_is_just_text(self):
        User.objects.create_user(username="warden0", password=PASSWORD, role=R.WARDEN)
        allocated_resident("r2", room=make_room(), first_name="Zoya")
        self.client.logout()
        login(self.client, "warden0")
        for attack in ("' OR '1'='1", "'; DROP TABLE accounts_user; --", "%' OR 1=1 --",
                       "\\"):
            with self.subTest(attack=attack):
                response = self.client.get(reverse("admissions:resident_list"), {"q": attack})
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "Zoya")
        self.assertTrue(User.objects.filter(username="warden0").exists())

    def test_sql_injection_in_other_parameters_is_harmless(self):
        User.objects.create_user(username="warden0", password=PASSWORD, role=R.WARDEN)
        self.client.logout()
        login(self.client, "warden0")
        for url in ("/applications/?status=' OR 1=1 --", "/rooms/?block=1 OR 1=1",
                    "/rooms/?block=';--"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_oversized_json_is_refused(self):
        response = self.client.post(
            "/api/v1/applications", "x" * (3 * 1024 * 1024), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_nul_characters_are_a_400_everywhere(self):
        self.assertEqual(self.client.get("/rooms/?block=%00").status_code, 400)
        self.assertEqual(
            self.client.post(reverse("profile"), {"first_name": "A\x00B"}).status_code, 400)
        payload = '{"enrolmentNumber": "PES2UG24CS500\\u0000"}'
        response = self.client.post(
            "/api/v1/applications", payload, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_malformed_json_is_a_400_not_a_crash(self):
        response = self.client.post(
            "/api/v1/applications", "{not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)


class QueryStyleTests(SimpleTestCase):
    """Parameterised queries only: no raw SQL is built from input (HMS-SR-006)."""

    ALLOWED_EXECUTE = {"apps/audit/service.py"}  # one fixed statement with a bound parameter

    def python_files(self):
        for path in (ROOT / "apps").rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if "/migrations/" in relative or relative.endswith(("tests.py",)) \
                    or "/test_" in relative:
                continue
            yield relative, path.read_text()

    def test_no_raw_sql_helpers(self):
        for relative, text in self.python_files():
            for banned in (".raw(", ".extra(", "RawSQL(", "mark_safe(f", "|safe"):
                self.assertNotIn(banned, text, f"{banned} in {relative}")

    def test_cursor_execute_is_only_used_with_bound_parameters(self):
        for relative, text in self.python_files():
            for match in re.finditer(r"cursor\.execute\(([^)]*)\)", text):
                self.assertIn(relative, self.ALLOWED_EXECUTE, relative)
                self.assertNotRegex(match.group(1), r'f"|f\'|%\s*\(|\.format\(|\+', relative)

    def test_templates_never_turn_escaping_off(self):
        paths = [*(ROOT / "templates").rglob("*.html"), *(ROOT / "apps").rglob("*.html")]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            # Django's own password-rule help text is server-generated HTML, the one allowed use.
            text = text.replace("help_text|safe", "")
            self.assertNotRegex(text, r"\|\s*safe\b|autoescape\s+off", path.as_posix())
