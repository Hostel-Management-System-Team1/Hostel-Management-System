from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditEntry

from .models import Complaint

User = get_user_model()


class ComplaintSLATests(TestCase):
    def setUp(self):
        self.resident = User.objects.create_user(
            username="resident_test",
            password="test12345",
        )
        User.objects.create_user(
            username="admin_test",
            password="test12345",
            role=User.Role.ADMINISTRATOR,
            email="admin@example.edu",
        )

    @patch("apps.complaints.management.commands.escalate_complaints.send_mail")
    def test_high_priority_escalates_after_48_hours(self, mock_email):
        complaint = Complaint.objects.create(
            title="Broken water pipe",
            description="Water pipe is leaking.",
            category=Complaint.Category.MAINTENANCE,
            created_by=self.resident,
            created_at=timezone.now() - timedelta(hours=49),
        )

        call_command("escalate_complaints", stdout=StringIO())

        complaint.refresh_from_db()

        self.assertIsNotNone(complaint.escalated_at)
        mock_email.assert_called_once()
        self.assertEqual(mock_email.call_args.args[3], ["admin@example.edu"])
        self.assertTrue(AuditEntry.objects.filter(action="complaint.escalated").exists())

    @patch("apps.complaints.management.commands.escalate_complaints.send_mail")
    def test_medium_priority_escalates_after_96_hours(self, mock_email):
        complaint = Complaint.objects.create(
            title="Room cleaning",
            description="Room needs cleaning.",
            category=Complaint.Category.CLEANING,
            created_by=self.resident,
            created_at=timezone.now() - timedelta(hours=97),
        )

        call_command("escalate_complaints", stdout=StringIO())

        complaint.refresh_from_db()

        self.assertIsNotNone(complaint.escalated_at)
        mock_email.assert_called_once()

    @patch("apps.complaints.management.commands.escalate_complaints.send_mail")
    def test_not_overdue_complaint_is_not_escalated(self, mock_email):
        complaint = Complaint.objects.create(
            title="Broken light",
            description="Light is not working.",
            category=Complaint.Category.MAINTENANCE,
            created_by=self.resident,
        )

        call_command("escalate_complaints", stdout=StringIO())

        complaint.refresh_from_db()

        self.assertIsNone(complaint.escalated_at)
        mock_email.assert_not_called()
