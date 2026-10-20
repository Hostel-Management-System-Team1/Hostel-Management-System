"""Access matrix: every view that declares allowed roles is tried with every role (TC-SEC-02).

The views are found by walking the URL configuration, so a restricted view added by any
module is checked automatically once it uses ``role_required``, ``RoleRequiredMixin`` or
``roles()`` from apps.accounts.permissions.
"""

import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import URLPattern, URLResolver, get_resolver

from .permissions import allowed_roles_of
from .testutils import PASSWORD, login

User = get_user_model()

PLACEHOLDER = {"int": "1", "slug": "x", "str": "x", "uuid": "00000000-0000-0000-0000-000000000000"}


def restricted_routes(patterns=None, prefix=""):
    """Yield (url, allowed roles) for every URL whose view declares roles."""
    patterns = get_resolver().url_patterns if patterns is None else patterns
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from restricted_routes(pattern.url_patterns, route)
        elif isinstance(pattern, URLPattern):
            allowed = allowed_roles_of(pattern.callback)
            if allowed:
                url = re.sub(r"<(?:(\w+):)?\w+>", lambda m: PLACEHOLDER[m.group(1) or "str"], route)
                yield "/" + url, allowed


class AccessMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.routes = sorted(set((url, tuple(sorted(r))) for url, r in restricted_routes()))

    def test_there_are_restricted_views_to_check(self):
        self.assertTrue(self.routes)

    def test_every_other_role_gets_403_and_anonymous_is_turned_away(self):
        for index, role in enumerate(User.Role):
            User.objects.create_user(username=f"u{index}", password=PASSWORD, role=role)
        for url, allowed in self.routes:
            with self.subTest(url=url):
                self.client.logout()
                anon = self.client.get(url)
                self.assertIn(anon.status_code, (302, 403), f"anonymous reached {url}")
                if anon.status_code == 302:
                    self.assertIn("/accounts/login/", anon["Location"])
                for index, role in enumerate(User.Role):
                    self.client.logout()
                    login(self.client, f"u{index}")
                    status = self.client.get(url).status_code
                    if role in allowed:
                        self.assertNotEqual(status, 403, f"{role} should reach {url}")
                    else:
                        self.assertEqual(status, 403, f"{role} should be refused {url}")
