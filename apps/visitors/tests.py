from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import VisitingHours, Visitor

User = get_user_model()


class VisitorModelTests(TestCase):
    def setUp(self):
        self.guard = User.objects.create_user(
            username="test_guard",
            password="testpass123",
            role="SECURITY_GUARD",
        )
        self.resident = User.objects.create_user(
            username="test_resident",
            password="testpass123",
            role="RESIDENT",
        )

    def test_visitor_creation(self):
        visitor = Visitor.objects.create(
            visitor_name="Test Visitor",
            phone="9876543210",
            resident=self.resident,
            purpose="Personal visit",
            registered_by=self.guard,
        )
        self.assertEqual(visitor.status, Visitor.Status.REGISTERED)
        self.assertEqual(visitor.resident, self.resident)

    def test_visitor_entry_and_exit_fields(self):
        visitor = Visitor.objects.create(
            visitor_name="Test Visitor",
            phone="9876543210",
            resident=self.resident,
            purpose="Personal visit",
            registered_by=self.guard,
        )
        visitor.entry_time = timezone.now()
        visitor.status = Visitor.Status.INSIDE
        visitor.save()

        visitor.exit_time = timezone.now()
        visitor.status = Visitor.Status.EXITED
        visitor.save()

        visitor.refresh_from_db()
        self.assertIsNotNone(visitor.entry_time)
        self.assertIsNotNone(visitor.exit_time)
        self.assertEqual(visitor.status, Visitor.Status.EXITED)

    def test_visiting_hours_defaults(self):
        hours = VisitingHours.objects.create()
        self.assertEqual(hours.start_time.strftime("%H:%M"), "09:00")
        self.assertEqual(hours.end_time.strftime("%H:%M"), "18:00")
        self.assertTrue(hours.is_active)

@override_settings(
    MIDDLEWARE=[
        m for m in settings.MIDDLEWARE
        if m != "apps.accounts.middleware.MFARequiredMiddleware"
    ]
)
class VisitorPermissionTests(TestCase):
    def setUp(self):
        self.guard = User.objects.create_user(
            username="guard_test",
            password="testpass123",
            role="SECURITY_GUARD",
        )
        self.resident = User.objects.create_user(
            username="resident_test",
            password="testpass123",
            role="RESIDENT",
        )
        self.warden = User.objects.create_user(
            username="warden_test",
            password="testpass123",
            role="WARDEN",
        )
        self.visitor = Visitor.objects.create(
            visitor_name="Permission Test Visitor",
            phone="9876543210",
            resident=self.resident,
            purpose="Testing",
            registered_by=self.guard,
        )

    def test_resident_cannot_register_visitor(self):
        self.client.force_login(self.resident)
        response = self.client.get("/visitors/register/")
        self.assertEqual(response.status_code, 403)

    def test_guard_cannot_open_warden_override(self):
        self.client.force_login(self.guard)
        response = self.client.get(
            f"/visitors/{self.visitor.pk}/override/"
        )
        self.assertEqual(response.status_code, 403)

    def test_warden_can_open_override(self):
        self.client.force_login(self.warden)
        response = self.client.get(
            f"/visitors/{self.visitor.pk}/override/"
        )
        self.assertEqual(response.status_code, 200)

    def test_entry_outside_visiting_hours_is_blocked(self):
        VisitingHours.objects.create(
            start_time="09:00",
            end_time="18:00",
        )
        self.client.force_login(self.guard)

        from datetime import time
        from unittest.mock import patch

        with patch("apps.visitors.views.timezone.localtime") as mock_time:
            mock_time.return_value.time.return_value = time(20, 0)
            response = self.client.post(f"/visitors/{self.visitor.pk}/entry/")

        self.assertEqual(response.status_code, 302)
        self.visitor.refresh_from_db()
        self.assertIsNone(self.visitor.entry_time)

    def test_warden_override_allows_entry_outside_hours(self):
        VisitingHours.objects.create(
            start_time="09:00",
            end_time="18:00",
        )
        self.visitor.overridden_by = self.warden
        self.visitor.override_reason = "Approved by warden for emergency visit"
        self.visitor.save()

        self.client.force_login(self.guard)

        from datetime import time
        from unittest.mock import patch

        with patch("apps.visitors.views.timezone.localtime") as mock_time:
            mock_time.return_value.time.return_value = time(20, 0)
            response = self.client.post(f"/visitors/{self.visitor.pk}/entry/")

        self.assertEqual(response.status_code, 302)
        self.visitor.refresh_from_db()
        self.assertIsNotNone(self.visitor.entry_time)
        self.assertEqual(self.visitor.status, Visitor.Status.INSIDE)

    def test_guard_can_record_visitor_exit(self):
        self.visitor.entry_time = timezone.now()
        self.visitor.status = Visitor.Status.INSIDE
        self.visitor.save()

        self.client.force_login(self.guard)
        response = self.client.post(f"/visitors/{self.visitor.pk}/exit/")

        self.assertEqual(response.status_code, 302)
        self.visitor.refresh_from_db()
        self.assertIsNotNone(self.visitor.exit_time)
        self.assertEqual(self.visitor.status, Visitor.Status.EXITED)

