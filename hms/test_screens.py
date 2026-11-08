"""Sprint 2 screens: every sidebar link opens a real page, and the pages behave per role."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.testutils import PASSWORD, sign_in
from apps.admissions.testutils import allocated_resident
from apps.audit.models import AuditEntry
from apps.complaints.models import Complaint
from apps.gate.models import GateMovement
from apps.visitors.models import Visitor

from .navigation import ADMIN_NAV, NAV

R = User.Role


def person(username, role):
    return User.objects.create_user(username=username, password=PASSWORD, role=role)


class NavigationCompleteTests(TestCase):
    def test_no_sidebar_item_is_a_placeholder(self):
        """Sprint 2 is done: no role's menu should lead to a "coming soon" page."""
        groups = [g for role_groups in NAV.values() for g in role_groups] + ADMIN_NAV
        for _, items in groups:
            for entry in items:
                self.assertTrue(entry["url_name"], f"{entry['label']} has no page")
                self.assertIsNone(entry["sprint"], entry["label"])

    def test_every_role_opens_every_page_in_its_menu(self):
        for role, groups in NAV.items():
            user = person(f"u-{role.lower()}", role)
            sign_in(self.client, user)
            for _, items in groups:
                for entry in items:
                    url = reverse(entry["url_name"])
                    response = self.client.get(url, follow=True)
                    self.assertEqual(response.status_code, 200, f"{role} {url}")
            self.client.logout()


class GateLogTests(TestCase):
    def setUp(self):
        self.resident = allocated_resident("gate_res").resident
        self.guard = person("guard1", R.SECURITY_GUARD)

    def test_guard_records_exit_then_entry(self):
        sign_in(self.client, self.guard)
        url = reverse("gate:log")
        self.client.post(url, {"resident": self.resident.pk, "direction": "OUT"})
        response = self.client.get(url)
        self.assertContains(response, "Record entry")
        self.client.post(url, {"resident": self.resident.pk, "direction": "IN"})
        moves = list(
            GateMovement.objects.order_by("occurred_at", "pk").values_list(
                "direction", "capture_method", "recorded_by"
            )
        )
        self.assertEqual(moves, [("OUT", "MANUAL", self.guard.pk), ("IN", "MANUAL", self.guard.pk)])

    def test_warden_sees_log_but_cannot_record(self):
        sign_in(self.client, person("warden1", R.WARDEN))
        url = reverse("gate:log")
        self.assertContains(self.client.get(url), "Curfew alerts")
        self.client.post(url, {"resident": self.resident.pk, "direction": "OUT"})
        self.assertFalse(GateMovement.objects.exists())

    def test_resident_is_refused(self):
        sign_in(self.client, self.resident)
        self.assertEqual(self.client.get(reverse("gate:log")).status_code, 403)


class ComplaintScreenTests(TestCase):
    def setUp(self):
        self.resident = person("res1", R.RESIDENT)
        self.staff = person("fixer", R.MAINTENANCE_STAFF)
        self.other_staff = person("fixer2", R.MAINTENANCE_STAFF)
        self.mine = Complaint.objects.create(
            title="Tap leaking",
            description="Drips",
            category="MAINTENANCE",
            created_by=self.resident,
            assigned_to=self.staff,
            status="IN_PROGRESS",
        )
        self.theirs = Complaint.objects.create(
            title="Fan broken",
            description="Stopped",
            category="MAINTENANCE",
            created_by=self.resident,
            assigned_to=self.other_staff,
            status="IN_PROGRESS",
        )

    def test_maintenance_staff_see_only_their_complaints(self):
        sign_in(self.client, self.staff)
        response = self.client.get(reverse("complaints:manage_complaints"))
        self.assertContains(response, "Tap leaking")
        self.assertNotContains(response, "Fan broken")

    def test_assigned_staff_resolve_and_it_is_audited(self):
        sign_in(self.client, self.staff)
        self.client.post(
            reverse("complaints:update_complaint_status", args=[self.mine.pk]),
            {"status": "RESOLVED"},
        )
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, Complaint.Status.RESOLVED)
        self.assertTrue(AuditEntry.objects.filter(action="complaint.status_changed").exists())

    def test_warden_assignment_is_audited(self):
        sign_in(self.client, person("warden1", R.WARDEN))
        complaint = Complaint.objects.create(
            title="Light out",
            description="Corridor",
            category="MAINTENANCE",
            created_by=self.resident,
        )
        self.client.post(
            reverse("complaints:assign_complaint", args=[complaint.pk]),
            {"assigned_to": self.staff.pk},
        )
        complaint.refresh_from_db()
        self.assertEqual(complaint.assigned_to, self.staff)
        entry = AuditEntry.objects.get(action="complaint.assigned")
        self.assertEqual(entry.detail["assigned_to"], "fixer")


class VisitorScreenTests(TestCase):
    def test_warden_sees_visitors_and_can_allow_out_of_hours(self):
        resident = person("res1", R.RESIDENT)
        visitor = Visitor.objects.create(
            visitor_name="Sunita",
            phone="9876500000",
            resident=resident,
            purpose="Visit",
            registered_by=person("guard1", R.SECURITY_GUARD),
        )
        sign_in(self.client, person("warden1", R.WARDEN))
        response = self.client.get(reverse("visitors:list"))
        self.assertContains(response, "Sunita")
        self.assertContains(response, reverse("visitors:override", args=[visitor.pk]))
        self.assertNotContains(response, "Register visitor")
        self.client.post(reverse("visitors:override", args=[visitor.pk]), {"reason": "Late train"})
        self.assertTrue(AuditEntry.objects.filter(action="visitor.hours_override").exists())


class AdminReportsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin1", password=PASSWORD, role=R.ADMINISTRATOR, is_staff=True
        )
        sign_in(self.client, self.admin)

    def test_reports_open_inside_the_admin_site(self):
        response = self.client.get(reverse("admin:hms_reports"))
        self.assertContains(response, "Management reports")
        self.assertContains(response, "Account menu")  # the admin header, not the portal sidebar
        self.assertRedirects(
            self.client.get(reverse("reporting:dashboard")), reverse("admin:hms_reports")
        )

    def test_admin_menu_links_sprint2_modules(self):
        response = self.client.get(reverse("admin:index"))
        for name in (
            "admin:complaints_complaint_changelist",
            "admin:mess_messmenuitem_changelist",
            "admin:gate_gatemovement_changelist",
            "admin:visitors_visitor_changelist",
        ):
            self.assertContains(response, reverse(name))
        self.assertNotContains(response, "Sprint 2")

    def test_lists_have_no_bulk_actions_and_evidence_is_read_only(self):
        resident = person("res1", R.RESIDENT)
        visitor = Visitor.objects.create(
            visitor_name="Sunita",
            phone="9876500000",
            resident=resident,
            purpose="Visit",
            registered_by=person("guard1", R.SECURITY_GUARD),
        )
        for name in (
            "admin:visitors_visitor_changelist",
            "admin:complaints_complaint_changelist",
            "admin:mess_messmenuitem_changelist",
            "admin:gate_gatemovement_changelist",
        ):
            self.assertNotContains(self.client.get(reverse(name)), "action-checkbox")
        page = self.client.get(reverse("admin:visitors_visitor_change", args=[visitor.pk]))
        self.assertContains(page, "View visitor")
        self.assertNotContains(page, 'name="_save"')


class SeedDemoTests(TestCase):
    @override_settings(DEBUG=True)
    def test_demo_data_covers_sprint2_and_can_run_twice(self):
        call_command("seed_demo", stdout=StringIO())
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(Complaint.objects.count(), 4)
        self.assertEqual(Visitor.objects.count(), 3)
        self.assertTrue(GateMovement.objects.exists())
        self.assertEqual(
            User.objects.get(username="aarav").allocations.filter(status="ACTIVE").count(), 1
        )
