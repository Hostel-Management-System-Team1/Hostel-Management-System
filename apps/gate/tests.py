
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from .models import GateMovement
from . import services
from django.test import override_settings
from rest_framework.test import APIClient

from apps.admissions.testutils import allocated_resident

from . import services
from .models import GateMovement
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.gate.models import CurfewConfiguration, CurfewAlert

User = get_user_model()


class GateMovementServiceTests(TestCase):
    def setUp(self):
        self.allocation = allocated_resident("gate_resident")
        self.resident = self.allocation.resident
        self.guard = User.objects.create_user(
            username="gate_guard",
            password="test-password",
            role=User.Role.SECURITY_GUARD,
        )

    def test_records_rfid_entry(self):
        movement = services.record_movement(
            self.resident,
            GateMovement.Direction.IN,
            GateMovement.CaptureMethod.RFID,
        )

        self.assertEqual(movement.resident, self.resident)
        self.assertEqual(movement.direction, "IN")
        self.assertEqual(movement.capture_method, "RFID")
        self.assertIsNotNone(movement.occurred_at)

    def test_records_biometric_exit(self):
        movement = services.record_movement(
            self.resident,
            GateMovement.Direction.OUT,
            GateMovement.CaptureMethod.BIOMETRIC,
        )

        self.assertEqual(movement.direction, "OUT")
        self.assertEqual(movement.capture_method, "BIOMETRIC")

    def test_security_guard_can_record_manual_movement(self):
        movement = services.record_movement(
            self.resident,
            GateMovement.Direction.OUT,
            GateMovement.CaptureMethod.MANUAL,
            recorded_by=self.guard,
        )

        self.assertEqual(movement.recorded_by, self.guard)

    def test_manual_movement_requires_security_guard(self):
        with self.assertRaises(services.InvalidGateMovement):
            services.record_movement(
                self.resident,
                GateMovement.Direction.IN,
                GateMovement.CaptureMethod.MANUAL,
            )

    def test_duplicate_device_event_is_not_recorded_twice(self):
        first = services.record_movement(
            self.resident,
            GateMovement.Direction.IN,
            GateMovement.CaptureMethod.RFID,
            external_event_id="RFID-001",
        )

        second = services.record_movement(
            self.resident,
            GateMovement.Direction.IN,
            GateMovement.CaptureMethod.RFID,
            external_event_id="RFID-001",
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(GateMovement.objects.count(), 1)

    def test_buffered_event_preserves_original_timestamp(self):
        original_time = timezone.now()

        movement = services.record_movement(
            self.resident,
            GateMovement.Direction.IN,
            GateMovement.CaptureMethod.RFID,
            occurred_at=original_time,
            external_event_id="RFID-BUFFERED-001",
        )

        self.assertEqual(movement.occurred_at, original_time)

    def test_invalid_direction_is_rejected(self):
        with self.assertRaises(services.InvalidGateMovement):
            services.record_movement(
                self.resident,
                "INVALID",
                GateMovement.CaptureMethod.RFID,
            )

    def test_resident_without_active_allocation_is_rejected(self):
        self.allocation.status = "ENDED"
        self.allocation.save(update_fields=["status"])

        with self.assertRaises(services.InvalidGateMovement):
            services.record_movement(
                self.resident,
                GateMovement.Direction.IN,
                GateMovement.CaptureMethod.RFID,
            )


class CurfewAlertTests(TestCase):
    def setUp(self):
        self.allocation = allocated_resident("curfew_resident")
        self.resident = self.allocation.resident
        self.block = self.allocation.bed.room.block

        self.configuration = CurfewConfiguration.objects.create(
            block=self.block,
            curfew_time=time(22, 0),
        )

        self.curfew_date = timezone.localdate()
        self.threshold = timezone.make_aware(
            datetime.combine(self.curfew_date, time(22, 30)),
            timezone.get_current_timezone(),
        )

    def record(self, direction, occurred_at):
        return GateMovement.objects.create(
            resident=self.resident,
            direction=direction,
            capture_method=GateMovement.CaptureMethod.RFID,
            occurred_at=occurred_at,
        )

    @patch("apps.gate.services._notify_wardens", return_value=True)
    def test_resident_still_outside_gets_alert(self, notify):
        self.record(GateMovement.Direction.OUT, self.threshold - timedelta(hours=1))

        result = services.process_curfew_alerts(
            now=self.threshold + timedelta(minutes=1)
        )

        self.assertEqual(result["alerts_created"], 1)
        self.assertEqual(result["notifications_sent"], 1)
        self.assertEqual(CurfewAlert.objects.count(), 1)
        notify.assert_called_once()

    @patch("apps.gate.services._notify_wardens", return_value=True)
    def test_resident_who_returned_before_threshold_is_not_alerted(self, notify):
        self.record(GateMovement.Direction.OUT, self.threshold - timedelta(hours=1))
        self.record(GateMovement.Direction.IN, self.threshold - timedelta(minutes=5))

        services.process_curfew_alerts(
            now=self.threshold + timedelta(minutes=1)
        )

        self.assertEqual(CurfewAlert.objects.count(), 0)
        notify.assert_not_called()

    @patch("apps.gate.services._notify_wardens", return_value=True)
    def test_repeated_processing_does_not_duplicate_alert(self, notify):
        self.record(GateMovement.Direction.OUT, self.threshold - timedelta(hours=1))

        for _ in range(2):
            services.process_curfew_alerts(
                now=self.threshold + timedelta(minutes=1)
            )

        self.assertEqual(CurfewAlert.objects.count(), 1)
        self.assertEqual(notify.call_count, 1)

    @patch(
        "apps.gate.services._notify_wardens",
        side_effect=[False, True],
    )
    def test_failed_notification_is_retried(self, notify):
        self.record(GateMovement.Direction.OUT, self.threshold - timedelta(hours=1))

        first = services.process_curfew_alerts(
            now=self.threshold + timedelta(minutes=1)
        )
        second = services.process_curfew_alerts(
            now=self.threshold + timedelta(minutes=2)
        )

        self.assertEqual(first["notifications_failed"], 1)
        self.assertEqual(second["notifications_sent"], 1)

        alert = CurfewAlert.objects.get(resident=self.resident)
        self.assertIsNotNone(alert.notified_at)
        self.assertEqual(notify.call_count, 2)


    @patch("apps.gate.services._notify_wardens", return_value=True)
    def test_previous_nights_violation_is_detected_after_midnight(self, notify):
        previous_date = self.curfew_date - timedelta(days=1)

        previous_threshold = timezone.make_aware(
            datetime.combine(previous_date, time(22, 30)),
            timezone.get_current_timezone(),
        )

        # The resident exited before curfew and remained outside.
        self.record(
            GateMovement.Direction.OUT,
            previous_threshold - timedelta(hours=1),
        )

        # Simulate the scheduled command running at 12:30 AM.
        now = previous_threshold + timedelta(hours=2)

        result = services.process_curfew_alerts(now=now)

        self.assertEqual(result["alerts_created"], 1)
        self.assertEqual(result["notifications_sent"], 1)

        alert = CurfewAlert.objects.get(resident=self.resident)

        self.assertEqual(alert.curfew_date, previous_date)
        self.assertIsNotNone(alert.notified_at)
        notify.assert_called_once()




class GateAPITests(TestCase):
    def setUp(self):
        self.allocation = allocated_resident("api_gate_resident")
        self.resident = self.allocation.resident

        self.guard = User.objects.create_user(
            username="api_gate_guard",
            password="test-password",
            role=User.Role.SECURITY_GUARD,
        )
        self.warden = User.objects.create_user(
            username="api_gate_warden",
            password="test-password",
            role=User.Role.WARDEN,
        )

        self.client = APIClient()

    def test_guard_can_record_manual_entry(self):
        self.client.force_authenticate(user=self.guard)

        response = self.client.post(
            "/api/v1/gate/movements/manual",
            {
                "resident_id": self.resident.pk,
                "direction": "IN",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["captureMethod"], "MANUAL")

    def test_resident_cannot_record_manual_entry(self):
        self.client.force_authenticate(user=self.resident)

        response = self.client.post(
            "/api/v1/gate/movements/manual",
            {
                "resident_id": self.resident.pk,
                "direction": "IN",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_user_cannot_record_manual_entry(self):
        response = self.client.post(
            "/api/v1/gate/movements/manual",
            {
                "resident_id": self.resident.pk,
                "direction": "IN",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    @override_settings(GATE_DEVICE_API_KEY="test-device-secret")
    def test_device_with_valid_key_can_record_event(self):
        response = self.client.post(
            "/api/v1/gate/movements/device",
            {
                "resident_id": self.resident.pk,
                "direction": "OUT",
                "capture_method": "RFID",
                "occurred_at": timezone.now().isoformat(),
                "external_event_id": "DEVICE-TEST-001",
            },
            format="json",
            HTTP_X_GATE_DEVICE_KEY="test-device-secret",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["captureMethod"], "RFID")

    @override_settings(GATE_DEVICE_API_KEY="test-device-secret")
    def test_device_without_valid_key_is_rejected(self):
        response = self.client.post(
            "/api/v1/gate/movements/device",
            {
                "resident_id": self.resident.pk,
                "direction": "OUT",
                "capture_method": "RFID",
                "occurred_at": timezone.now().isoformat(),
                "external_event_id": "DEVICE-TEST-002",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_warden_can_view_curfew_alerts(self):
        from .models import CurfewAlert

        CurfewAlert.objects.create(
            resident=self.resident,
            block=self.allocation.bed.room.block,
            curfew_date=timezone.localdate(),
        )

        self.client.force_authenticate(user=self.warden)

        response = self.client.get("/api/v1/gate/curfew-alerts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_security_guard_cannot_view_curfew_alerts(self):
        self.client.force_authenticate(user=self.guard)

        response = self.client.get("/api/v1/gate/curfew-alerts")

        self.assertEqual(response.status_code, 403)
