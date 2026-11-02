"""Acceptance tests for the Software Test Plan's Sprint 2 cases (issue #18).

Each test is named after its Test Plan case and drives the feature through the pages the
users actually use. Sprint 1 cases are covered by the module test suites; the mapping from
every TC-ID to its tests is in docs/qa/TEST_SUMMARY.md.
"""

import tempfile
from datetime import datetime, time, timedelta
from io import BytesIO

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from PIL import Image

from apps.accounts.models import User
from apps.accounts.testutils import PASSWORD, sign_in
from apps.admissions.testutils import allocated_resident, make_block, make_room
from apps.complaints.models import Complaint
from apps.fees.models import Invoice
from apps.gate import services as gate
from apps.gate.models import CurfewAlert, CurfewConfiguration, NightAttendance, OutpassRequest
from apps.mess.models import MealOptOut, MessActivity, MessMenuItem
from apps.visitors.models import VisitingHours, Visitor

R = User.Role


def person(username, role, **extra):
    return User.objects.create_user(username=username, password=PASSWORD, role=role, **extra)


class HousedResidentTestCase(TestCase):
    """A warden, a guard and a resident with a bed (and a guardian email on the application)."""

    def setUp(self):
        mail.outbox = []
        self.warden = person("warden1", R.WARDEN, email="warden@example.edu")
        self.guard = person("guard1", R.SECURITY_GUARD)
        self.room = make_room(make_block("Block A", "M"), "101")
        self.allocation = allocated_resident("res1", room=self.room)
        self.resident = self.allocation.resident

    def as_user(self, user):
        self.client.logout()
        sign_in(self.client, user)


class TS3GateOutpassAttendance(HousedResidentTestCase):
    def test_tc_gate_01_reader_and_manual_entries_create_timestamped_records(self):
        self.as_user(self.guard)
        self.client.post(reverse("gate:log"), {"resident": self.resident.pk, "direction": "OUT"})
        self.client.post(reverse("gate:log"), {"resident": self.resident.pk, "direction": "IN"})
        moves = self.resident.gate_movements.order_by("occurred_at", "pk")
        self.assertEqual([m.direction for m in moves], ["OUT", "IN"])
        self.assertTrue(all(m.occurred_at and m.recorded_by == self.guard for m in moves))

    def test_tc_out_01_outpass_pending_approved_returned_with_guardian_notices(self):
        self.as_user(self.resident)
        back = timezone.localtime() + timedelta(days=2)
        self.client.post(reverse("gate:outpasses"), {
            "destination": "Home", "contact_number": "9876500000",
            "expected_return_at": back.strftime("%Y-%m-%dT%H:%M")})
        outpass = OutpassRequest.objects.get()
        self.assertEqual(outpass.status, "PENDING")

        self.as_user(self.warden)
        self.client.post(reverse("gate:warden_outpasses"),
                         {"outpass_id": outpass.pk, "decision": "APPROVED", "reason": "OK"})
        outpass.refresh_from_db()
        self.assertEqual(outpass.status, "APPROVED")
        self.assertEqual(len(mail.outbox), 1)

        self.as_user(self.guard)
        self.client.post(reverse("gate:returns"), {"outpass_id": outpass.pk})
        outpass.refresh_from_db()
        self.assertIsNotNone(outpass.returned_at)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].to, [outpass.allocation.application.guardian_email])

    def test_tc_out_01_rejected_outpass_sends_no_approval_notice(self):
        outpass = gate.submit_outpass(self.resident, "Home", "9876500000",
                                      timezone.now() + timedelta(days=1))
        self.as_user(self.warden)
        self.client.post(reverse("gate:warden_outpasses"),
                         {"outpass_id": outpass.pk, "decision": "REJECTED", "reason": "Exams"})
        outpass.refresh_from_db()
        self.assertEqual(outpass.status, "REJECTED")
        self.assertEqual(mail.outbox, [])

    def test_tc_gate_02_curfew_alert_reaches_the_warden_dashboard_and_email(self):
        CurfewConfiguration.objects.create(block=self.room.block, curfew_time=time(22, 0))
        today = timezone.localdate()
        curfew = timezone.make_aware(datetime.combine(today, time(22, 0)))
        gate.record_movement(self.resident, "OUT", "RFID", occurred_at=curfew - timedelta(hours=2))
        gate.process_curfew_alerts(now=curfew + timedelta(minutes=31))
        self.assertEqual(CurfewAlert.objects.count(), 1)
        self.assertEqual(mail.outbox[0].to, ["warden@example.edu"])
        self.as_user(self.warden)
        self.assertContains(self.client.get(reverse("home")), "Curfew alerts")

    def test_tc_att_01_register_lists_each_resident_room_by_room(self):
        CurfewConfiguration.objects.create(block=self.room.block, curfew_time=time(22, 0))
        night = timezone.localdate() - timedelta(days=1)
        self.as_user(self.warden)
        self.client.post(reverse("gate:attendance"), {"attendance_date": night.isoformat()})
        record = NightAttendance.objects.get(resident=self.resident)
        self.assertEqual(record.room, self.room)
        response = self.client.get(reverse("gate:attendance"), {"date": night.isoformat()})
        self.assertContains(response, record.get_status_display())


class TS4Mess(HousedResidentTestCase):
    def setUp(self):
        super().setUp()
        self.manager = person("mess1", R.MESS_MANAGER)

    def test_tc_mess_01_published_menu_is_visible_to_residents(self):
        self.as_user(self.manager)
        when = timezone.localtime() + timedelta(days=3)
        self.client.post(reverse("mess:meal_save"), {
            "menu_date": when.date().isoformat(), "meal_type": "LUNCH",
            "time": "13:00", "description": "Veg biryani"})
        self.assertTrue(MessMenuItem.objects.get().is_published)
        self.as_user(self.resident)
        week = (when.date() - (timezone.localdate()
                - timedelta(days=timezone.localdate().weekday()))).days // 7
        self.assertContains(self.client.get(reverse("mess:home"), {"week": week}), "Veg biryani")

    def test_tc_mess_01_manager_plans_the_week(self):
        self.as_user(self.manager)
        when = timezone.localtime() + timedelta(days=2)
        data = {"menu_date": when.date().isoformat(), "meal_type": "DINNER", "time": "20:00"}
        self.client.post(reverse("mess:meal_save"), {**data, "description": "Dal"})
        self.client.post(reverse("mess:meal_save"), {**data, "description": "Paneer"})  # edit
        meal = MessMenuItem.objects.get()
        self.assertEqual(meal.description, "Paneer")

        self.client.post(reverse("mess:copy_week"), {"week": 0})
        self.assertTrue(MessMenuItem.objects.filter(
            menu_date=meal.menu_date + timedelta(weeks=1), description="Paneer").exists())

        past = self.meal(timezone.now() - timedelta(hours=3))
        self.client.post(reverse("mess:record_served", args=[past.pk]), {"served": "4"})
        self.assertEqual(MessActivity.objects.get(meal_type="LUNCH").meals_served, 4)
        self.client.post(reverse("mess:meal_delete", args=[past.pk]))
        self.assertTrue(MessMenuItem.objects.filter(pk=past.pk).exists())  # served meals stay

    def meal(self, when, meal_type="LUNCH"):
        return MessMenuItem.objects.create(
            menu_date=timezone.localtime(when).date(), meal_datetime=when, meal_type=meal_type,
            description="Rice", is_published=True, published_by=self.manager)

    def test_tc_mess_02_opt_out_needs_24_hours_notice(self):
        soon = self.meal(timezone.now() + timedelta(hours=10), "DINNER")
        later = self.meal(timezone.now() + timedelta(days=3))
        self.as_user(self.resident)
        self.client.post(reverse("mess:home"), {"menu_item_id": soon.pk})
        self.client.post(reverse("mess:home"), {"menu_item_id": later.pk})
        self.assertEqual(list(MealOptOut.objects.values_list("menu_item", flat=True)), [later.pk])

        self.client.post(reverse("mess:home"), {"menu_item_id": later.pk, "action": "undo"})
        self.assertFalse(MealOptOut.objects.exists())  # a skip can be taken back in time

        day = self.meal(timezone.now() + timedelta(days=3, hours=1), "BREAKFAST")
        day_date = timezone.localtime(day.meal_datetime).date()
        self.client.post(reverse("mess:home"), {"action": "skip_day", "day": day_date})
        self.assertTrue(MealOptOut.objects.filter(menu_item=day).exists())

    def test_tc_mess_02_bill_counts_only_meals_eaten_by_housed_residents(self):
        last_month_day = timezone.localdate().replace(day=1) - timedelta(days=1)
        noon = timezone.make_aware(datetime.combine(last_month_day, time(13, 0)))
        away = allocated_resident("res2", room=self.room).resident  # skips every meal
        type(self.allocation).objects.update(
            allocated_at=noon - timedelta(days=40))  # both housed for the whole month
        meals = [self.meal(noon - timedelta(days=d)) for d in range(3)]
        MealOptOut.objects.create(resident=self.resident, menu_item=meals[0])
        for meal in meals:
            MealOptOut.objects.create(resident=away, menu_item=meal)
        unhoused = person("neha", R.RESIDENT)
        self.as_user(self.manager)
        for _ in range(2):  # a second run must not bill twice
            self.client.post(reverse("mess:home"), {
                "action": "generate_bills", "month": last_month_day.month,
                "year": last_month_day.year})
        bill = Invoice.objects.get(resident=self.resident, kind=Invoice.Kind.MESS)
        self.assertEqual(bill.total, 2 * 50)
        self.assertFalse(Invoice.objects.filter(resident=unhoused).exists())
        self.assertFalse(Invoice.objects.filter(resident=away, kind=Invoice.Kind.MESS).exists())

    def test_tc_mess_02_a_month_still_running_cannot_be_billed(self):
        self.as_user(self.manager)
        today = timezone.localdate()
        response = self.client.post(reverse("mess:home"), {
            "action": "generate_bills", "month": today.month, "year": today.year}, follow=True)
        self.assertContains(response, "only after it has ended")
        self.assertFalse(Invoice.objects.filter(kind=Invoice.Kind.MESS).exists())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="hms-test-media-"))
class TS5Complaints(HousedResidentTestCase):
    def setUp(self):
        super().setUp()
        self.staff = person("fixer", R.MAINTENANCE_STAFF)

    def submit(self, **extra):
        self.as_user(self.resident)
        data = {"title": "Tap leaking", "category": "MAINTENANCE", "description": "Drips"}
        data.update(extra)
        return self.client.post(reverse("complaints:submit_complaint"), data, follow=True)

    def test_tc_cmp_01_complaint_gets_a_ticket_and_priority_from_category(self):
        png = BytesIO()
        Image.new("RGB", (4, 4), "white").save(png, "PNG")
        photo = SimpleUploadedFile("tap.png", png.getvalue(), content_type="image/png")
        response = self.submit(photo=photo)
        complaint = Complaint.objects.get()
        self.assertContains(response, f"Complaint #{complaint.pk} submitted")
        self.assertEqual(complaint.priority, Complaint.Priority.HIGH)
        self.as_user(self.warden)
        self.assertContains(self.client.get(reverse("complaints:manage_complaints")), "Tap leaking")

    def test_tc_cmp_01_photo_over_5_mb_is_refused(self):
        big = SimpleUploadedFile("big.gif", b"GIF89a" + b"0" * (5 * 1024 * 1024 + 1),
                                 content_type="image/gif")
        self.submit(photo=big)
        self.assertFalse(Complaint.objects.exists())

    def test_tc_cmp_02_lifecycle_open_in_progress_resolved_closed(self):
        self.submit()
        complaint = Complaint.objects.get()
        self.assertEqual(complaint.status, "OPEN")

        self.as_user(self.resident)  # closure needs the work to be resolved first
        self.client.post(reverse("complaints:confirm_resolution", args=[complaint.pk]))
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, "OPEN")

        self.as_user(self.warden)
        self.client.post(reverse("complaints:assign_complaint", args=[complaint.pk]),
                         {"assigned_to": self.staff.pk})
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, "IN_PROGRESS")

        self.as_user(self.staff)
        self.client.post(reverse("complaints:update_complaint_status", args=[complaint.pk]),
                         {"status": "RESOLVED"})
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, "RESOLVED")

        self.as_user(self.resident)
        self.client.post(reverse("complaints:confirm_resolution", args=[complaint.pk]))
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, "CLOSED")
        self.assertTrue(complaint.resolution_confirmed)


class TS6Visitors(HousedResidentTestCase):
    def test_tc_vis_01_out_of_hours_entry_needs_a_warden_override_with_reason(self):
        now = timezone.localtime()
        closed_from = (now + timedelta(hours=1)).time()
        closed_to = (now + timedelta(hours=2)).time()
        VisitingHours.objects.create(start_time=closed_from, end_time=closed_to)

        self.as_user(self.guard)
        self.client.post(reverse("visitors:register"), {
            "visitor_name": "Sunita Sharma", "phone": "9876500000", "id_proof_type": "Aadhaar",
            "id_proof_number": "1234", "resident": self.resident.pk, "purpose": "Visit"})
        visitor = Visitor.objects.get()
        self.client.post(reverse("visitors:entry", args=[visitor.pk]))
        visitor.refresh_from_db()
        self.assertIsNone(visitor.entry_time)

        self.as_user(self.warden)
        self.client.post(reverse("visitors:override", args=[visitor.pk]), {"reason": ""})
        visitor.refresh_from_db()
        self.assertIsNone(visitor.overridden_by)
        self.client.post(reverse("visitors:override", args=[visitor.pk]), {"reason": "Late train"})

        self.as_user(self.guard)
        self.client.post(reverse("visitors:entry", args=[visitor.pk]))
        self.client.post(reverse("visitors:exit", args=[visitor.pk]))
        visitor.refresh_from_db()
        self.assertEqual(visitor.status, Visitor.Status.EXITED)
        self.assertIsNotNone(visitor.exit_time)
        self.assertEqual(visitor.override_reason, "Late train")


class TS7Reports(HousedResidentTestCase):
    def test_tc_rpt_01_reports_reconcile_and_both_exports_open(self):
        Complaint.objects.create(title="Fan", description="Broken", category="MAINTENANCE",
                                 created_by=self.resident)
        self.as_user(self.warden)
        page = self.client.get(reverse("reporting:dashboard"))
        invoice = Invoice.objects.get(resident=self.resident)
        self.assertEqual(page.context["occupied_beds"], 1)
        self.assertEqual(page.context["outstanding_total"], invoice.total)
        self.assertEqual(page.context["open_complaints"], 1)

        xlsx = self.client.get(reverse("reporting:export_dues_xlsx"))
        rows = list(load_workbook(BytesIO(xlsx.content)).active.iter_rows(values_only=True))
        self.assertIn(invoice.number, [row[0] for row in rows])
        pdf = self.client.get(reverse("reporting:export_occupancy_pdf"))
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertTrue(pdf["Content-Disposition"].startswith("inline"))  # opens in the browser


class TS7Operations(HousedResidentTestCase):
    def test_tc_ops_02_retention_report_counts_old_records_and_changes_nothing(self):
        from io import StringIO

        from django.core.management import call_command

        from apps.admissions.models import Allocation

        old = timezone.now() - timedelta(days=6 * 366)
        Allocation.objects.filter(pk=self.allocation.pk).update(ended_at=old)
        gate.record_movement(self.resident, "OUT", "RFID", occurred_at=old)
        out = StringIO()
        call_command("retention_report", "--years", "5", stdout=out)
        self.assertIn("Completed allocations: 1", out.getvalue())
        self.assertIn("Gate movements: 1", out.getvalue())
        self.assertEqual(self.resident.gate_movements.count(), 1)
