"""REST API and scheduled-job tests for the gate module (HMS-F-020 to F-023).

These cover the paths the main gate tests do not reach: validation errors, role checks,
the outpass and attendance endpoints, and the two scheduled commands.
"""

from datetime import time, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.admissions.testutils import allocated_resident

from .models import CurfewConfiguration, OutpassRequest

User = get_user_model()
R = User.Role


class GateApiBase(TestCase):
    def setUp(self):
        self.allocation = allocated_resident("extra_resident")
        self.resident = self.allocation.resident
        self.guard = User.objects.create_user("extra_guard", password="x", role=R.SECURITY_GUARD)
        self.warden = User.objects.create_user("extra_warden", password="x", role=R.WARDEN)
        self.api = APIClient()

    def as_user(self, user):
        self.api.force_authenticate(user=user)

    def submit_outpass(self, **overrides):
        body = {
            "destination": "Mysuru",
            "contact_number": "9876543210",
            "expected_return_at": (timezone.now() + timedelta(days=1)).isoformat(),
        }
        return self.api.post("/api/v1/outpasses", {**body, **overrides}, format="json")


class DeviceEndpointErrorTests(GateApiBase):
    body = {"direction": "IN", "capture_method": "RFID", "external_event_id": "E-1"}

    def post(self, key="secret", **extra):
        body = {
            **self.body,
            "occurred_at": timezone.now().isoformat(),
            "resident_id": self.resident.pk,
            **extra,
        }
        headers = {"HTTP_X_GATE_DEVICE_KEY": key} if key else {}
        return self.api.post("/api/v1/gate/movements/device", body, format="json", **headers)

    @override_settings(GATE_DEVICE_API_KEY="")
    def test_endpoint_is_closed_until_a_device_key_is_configured(self):
        self.assertEqual(self.post().status_code, 503)

    @override_settings(GATE_DEVICE_API_KEY="secret")
    def test_unknown_resident_is_404(self):
        self.assertEqual(self.post(resident_id=999999).status_code, 404)

    @override_settings(GATE_DEVICE_API_KEY="secret")
    def test_malformed_event_is_400(self):
        self.assertEqual(self.post(direction="SIDEWAYS").status_code, 400)

    @override_settings(GATE_DEVICE_API_KEY="secret")
    def test_resident_without_a_bed_is_refused(self):
        outsider = User.objects.create_user("no_bed", password="x", role=R.RESIDENT)
        self.assertEqual(self.post(resident_id=outsider.pk).status_code, 400)

    @override_settings(GATE_DEVICE_API_KEY="secret")
    def test_repeated_event_is_accepted_without_a_second_record(self):
        self.post()
        self.post()
        self.assertEqual(self.resident.gate_movements.count(), 1)


class ManualEndpointErrorTests(GateApiBase):
    def test_unknown_resident_is_404(self):
        self.as_user(self.guard)
        response = self.api.post(
            "/api/v1/gate/movements/manual",
            {"resident_id": 999999, "direction": "IN"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_malformed_body_is_400(self):
        self.as_user(self.guard)
        response = self.api.post(
            "/api/v1/gate/movements/manual", {"direction": "IN"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_resident_without_a_bed_is_400(self):
        outsider = User.objects.create_user("no_bed2", password="x", role=R.RESIDENT)
        self.as_user(self.guard)
        response = self.api.post(
            "/api/v1/gate/movements/manual",
            {"resident_id": outsider.pk, "direction": "OUT"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class OutpassApiTests(GateApiBase):
    def test_resident_submits_and_sees_only_their_own_outpass(self):
        self.as_user(self.resident)
        self.assertEqual(self.submit_outpass().status_code, 201)
        listing = self.api.get("/api/v1/outpasses")
        self.assertEqual([row["destination"] for row in listing.data], ["Mysuru"])

    def test_warden_lists_all_and_guard_is_refused(self):
        self.as_user(self.resident)
        self.submit_outpass()
        self.as_user(self.warden)
        self.assertEqual(len(self.api.get("/api/v1/outpasses").data), 1)
        self.as_user(self.guard)
        self.assertEqual(self.api.get("/api/v1/outpasses").status_code, 403)

    def test_only_residents_may_submit(self):
        self.as_user(self.warden)
        self.assertEqual(self.submit_outpass().status_code, 403)

    def test_return_time_in_the_past_is_400(self):
        self.as_user(self.resident)
        past = (timezone.now() - timedelta(hours=1)).isoformat()
        self.assertEqual(self.submit_outpass(expected_return_at=past).status_code, 400)

    def test_warden_decides_once_then_conflict(self):
        self.as_user(self.resident)
        pk = self.submit_outpass().data["id"]
        self.as_user(self.warden)
        url = f"/api/v1/outpasses/{pk}/decision"
        approved = self.api.patch(url, {"decision": "APPROVED"}, format="json")
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["status"], OutpassRequest.Status.APPROVED)
        self.assertEqual(
            self.api.patch(url, {"decision": "REJECTED"}, format="json").status_code, 409
        )

    def test_deciding_a_missing_outpass_is_404_and_a_bad_decision_is_400(self):
        self.as_user(self.warden)
        missing = self.api.patch(
            "/api/v1/outpasses/999999/decision", {"decision": "APPROVED"}, format="json"
        )
        self.assertEqual(missing.status_code, 404)
        bad = self.api.patch("/api/v1/outpasses/1/decision", {"decision": "MAYBE"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_resident_cannot_decide(self):
        self.as_user(self.resident)
        pk = self.submit_outpass().data["id"]
        response = self.api.patch(
            f"/api/v1/outpasses/{pk}/decision", {"decision": "APPROVED"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_guard_records_return_once(self):
        self.as_user(self.resident)
        pk = self.submit_outpass().data["id"]
        self.as_user(self.warden)
        self.api.patch(f"/api/v1/outpasses/{pk}/decision", {"decision": "APPROVED"}, format="json")
        self.as_user(self.guard)
        self.assertEqual(self.api.post(f"/api/v1/outpasses/{pk}/return").status_code, 200)
        self.assertEqual(self.api.post(f"/api/v1/outpasses/{pk}/return").status_code, 409)

    def test_return_of_a_missing_outpass_is_404(self):
        self.as_user(self.guard)
        self.assertEqual(self.api.post("/api/v1/outpasses/999999/return").status_code, 404)


class AttendanceApiTests(GateApiBase):
    def test_warden_generates_then_reads_the_register(self):
        night = (timezone.localdate() - timedelta(days=1)).isoformat()
        CurfewConfiguration.objects.create(
            block=self.allocation.bed.room.block, curfew_time=time(22, 0)
        )
        self.as_user(self.warden)
        generated = self.api.post("/api/v1/attendance", {"attendance_date": night}, format="json")
        self.assertEqual(generated.status_code, 200)
        rows = self.api.get("/api/v1/attendance", {"date": night})
        self.assertEqual([row["resident"] for row in rows.data], [self.resident.pk])
        block = self.allocation.bed.room.block_id
        self.assertEqual(
            len(self.api.get("/api/v1/attendance", {"date": night, "block": block}).data), 1
        )
        self.assertEqual(
            len(self.api.get("/api/v1/attendance", {"date": night, "block": block + 99}).data), 0
        )

    def test_missing_date_is_400_and_guard_is_refused(self):
        self.as_user(self.warden)
        self.assertEqual(self.api.post("/api/v1/attendance", {}, format="json").status_code, 400)
        self.as_user(self.guard)
        self.assertEqual(self.api.get("/api/v1/attendance").status_code, 403)


class ScheduledCommandTests(TestCase):
    def test_curfew_command_reports_its_counts(self):
        out = StringIO()
        call_command("process_curfew_alerts", stdout=out)
        self.assertIn("Curfew processing complete: 0 alerts created", out.getvalue())

    def test_overdue_command_reports_its_counts(self):
        out = StringIO()
        call_command("process_overdue_invoices", stdout=out)
        self.assertIn("Overdue invoice processing complete: 0 marked overdue", out.getvalue())
