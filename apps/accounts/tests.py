from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .testutils import PASSWORD, login, verify_mfa

User = get_user_model()


class UserModelTests(TestCase):
    def test_new_user_defaults_to_resident(self):
        user = User.objects.create_user(username="r1", password=PASSWORD)
        self.assertEqual(user.role, User.Role.RESIDENT)

    def test_superuser_defaults_to_administrator(self):
        admin = User.objects.create_superuser(username="a1", password=PASSWORD)
        self.assertEqual(admin.role, User.Role.ADMINISTRATOR)

    def test_role_decides_admin_access(self):
        user = User.objects.create_user(
            username="x1", password=PASSWORD, role=User.Role.ADMINISTRATOR
        )
        self.assertTrue(user.is_staff and user.is_superuser)
        user.role = User.Role.WARDEN
        user.save()
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_six_login_roles_defined(self):
        # Seven SRS roles minus Guardian, who is notified but never logs in.
        self.assertEqual(len(User.Role.choices), 6)


class PageTests(TestCase):
    def login_as(self, role, **extra):
        User.objects.create_user(username="u1", password=PASSWORD, role=role, **extra)
        login(self.client, "u1")

    def test_login_page_loads(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, f"{reverse('login')}?next=/")

    def test_dashboard_shows_role(self):
        self.login_as(User.Role.WARDEN)
        self.assertContains(self.client.get(reverse("home")), "Warden")

    def test_resident_sees_only_resident_modules(self):
        self.login_as(User.Role.RESIDENT)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Fees &amp; receipts")
        self.assertContains(response, "No application yet")
        self.assertNotContains(response, "Audit log")
        self.assertNotContains(response, "Visitors")

    def test_security_guard_sees_gate_and_visitors(self):
        self.login_as(User.Role.SECURITY_GUARD)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Gate log")
        self.assertContains(response, "Visitors")
        self.assertNotContains(response, "Fees &amp; receipts")

    def test_administrator_is_sent_to_admin_site(self):
        self.login_as(User.Role.ADMINISTRATOR)
        self.assertRedirects(self.client.get(reverse("home")), reverse("admin:index"))

    def test_dashboard_link_marked_current(self):
        self.login_as(User.Role.WARDEN)
        self.assertContains(self.client.get(reverse("home")), 'aria-current="page"')


class NavigationTests(TestCase):
    def login_as(self, role, **extra):
        User.objects.create_user(username="u1", password=PASSWORD, role=role, **extra)
        login(self.client, "u1")

    def test_built_outpass_item_opens_its_page(self):
        self.login_as(User.Role.RESIDENT)
        response = self.client.get(reverse("gate:outpasses"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My outpasses")
        self.assertContains(response, "Request an outpass")
        self.assertContains(response, 'aria-current="page"')
        
    def test_role_cannot_open_another_roles_page(self):
        self.login_as(User.Role.WARDEN)
        response = self.client.get(reverse("module", args=["outpass"]))
        self.assertEqual(response.status_code, 404)

    def test_dashboard_cards_link_to_pages(self):
        self.login_as(User.Role.SECURITY_GUARD)
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("module", args=["gate-log"])}"')

    def test_portal_password_change_uses_portal_layout(self):
        self.login_as(User.Role.RESIDENT)
        response = self.client.get(reverse("password_change"))
        self.assertTemplateUsed(response, "registration/password_change_form.html")
        self.assertContains(response, "hm-sidebar")

    def test_admin_password_change_uses_admin_layout(self):
        User.objects.create_superuser(username="a1", password=PASSWORD)
        login(self.client, "a1")
        response = self.client.get(reverse("admin:password_change"))
        self.assertTemplateUsed(response, "admin/hms_password_change_form.html")
        self.assertContains(response, "Account menu")



class AdminSiteTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="a1", password=PASSWORD, first_name="Asha")
        User.objects.create_user(username="r1", password=PASSWORD)
        User.objects.create_user(username="r2", password=PASSWORD, is_active=False)

    def test_dashboard_shows_live_counts_and_hms_navigation(self):
        login(self.client, "a1")
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(
            response.context["stats"], {"total": 3, "residents": 2, "staff": 1, "inactive": 1}
        )
        self.assertContains(response, "Users &amp; roles")
        self.assertContains(response, "People by role")


    def test_admin_reports_page_opens(self):
        login(self.client, "a1")
        response = self.client.get(reverse("reporting:dashboard"))
        self.assertEqual(response.status_code, 200)


    def test_portal_roles_cannot_open_admin(self):
        login(self.client, "r1")
        response = self.client.get(reverse("admin:index"), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse("home"))

    def test_admin_login_uses_the_portal_sign_in(self):
        response = self.client.get(reverse("admin:login"), {"next": "/admin/"})
        self.assertRedirects(
            response, f"{reverse('login')}?next=/admin/", fetch_redirect_response=False
        )

    def test_administrator_signs_in_once_and_lands_in_admin(self):
        # The password step leads to the second step; once verified the admin site opens.
        self.client.post(reverse("login"), {"username": "a1", "password": PASSWORD})
        verify_mfa(self.client, User.objects.get(username="a1"))
        response = self.client.get(reverse("home"), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse("admin:index"))

    def test_user_list_role_tabs_and_status_filter(self):
        login(self.client, "a1")
        url = reverse("admin:accounts_user_changelist")
        response = self.client.get(url, {"role__exact": "RESIDENT"})
        self.assertEqual(response.context["cl"].result_count, 2)
        resident_tab = next(t for t in response.context["role_tabs"] if t["label"] == "Resident")
        self.assertTrue(resident_tab["active"])
        self.assertEqual(resident_tab["count"], 2)
        response = self.client.get(url, {"role__exact": "RESIDENT", "is_active__exact": "0"})
        self.assertEqual(response.context["cl"].result_count, 1)

    def test_user_list_has_no_bulk_actions(self):
        login(self.client, "a1")
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertNotContains(response, 'name="action"')
        self.assertNotContains(response, "action-checkbox")

    def test_app_overview_page_opens_its_list(self):
        login(self.client, "a1")
        response = self.client.get(reverse("admin:app_list", args=["accounts"]))
        self.assertRedirects(response, reverse("admin:accounts_user_changelist"))

    def test_breadcrumbs_leave_out_the_app_name(self):
        login(self.client, "a1")
        user = User.objects.get(username="r1")
        for url in [
            reverse("admin:accounts_user_changelist"),
            reverse("admin:accounts_user_add"),
            reverse("admin:accounts_user_change", args=[user.pk]),
            reverse("admin:accounts_user_delete", args=[user.pk]),
            reverse("admin:accounts_user_history", args=[user.pk]),
            reverse("admin:auth_user_password_change", args=[user.pk]),
        ]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertNotContains(response, "Auth &amp; RBAC Service", msg_prefix=url)

    def test_add_user_is_one_form_with_role(self):
        login(self.client, "a1")
        url = reverse("admin:accounts_user_add")
        response = self.client.get(url)
        self.assertEqual(response.content.decode().count('<fieldset class="module aligned'), 1)
        self.assertNotContains(response, 'name="usable_password"')
        response = self.client.post(url, {
            "username": "w9", "role": User.Role.WARDEN, "phone": "9876543210",
            "password1": "Strong-pass-77", "password2": "Strong-pass-77", "_save": "1",
        })
        self.assertEqual(response.status_code, 302)
        created = User.objects.get(username="w9")
        self.assertEqual(created.role, User.Role.WARDEN)
        self.assertTrue(created.check_password("Strong-pass-77"))

    def test_password_shows_status_not_hash(self):
        login(self.client, "a1")
        user = User.objects.get(username="r1")
        response = self.client.get(reverse("admin:accounts_user_change", args=[user.pk]))
        self.assertNotContains(response, "pbkdf2")
        self.assertNotContains(response, "salt")
        self.assertContains(response, "Reset password")


class ProfileTests(TestCase):
    def test_resident_edits_own_contact_details_only(self):
        user = User.objects.create_user(username="r1", password=PASSWORD)
        login(self.client, "r1")
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)
        response = self.client.post(reverse("profile"), {
            "first_name": "Aarav", "last_name": "Sharma", "email": "aarav@example.edu",
            "phone": "9876543210", "role": User.Role.ADMINISTRATOR, "username": "hacker",
        })
        self.assertRedirects(response, reverse("profile"))
        user.refresh_from_db()
        self.assertEqual((user.first_name, user.phone), ("Aarav", "9876543210"))
        self.assertEqual((user.username, user.role), ("r1", User.Role.RESIDENT))
        self.assertFalse(user.is_staff)
