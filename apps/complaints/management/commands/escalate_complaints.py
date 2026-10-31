import logging

from django.core.mail import mail_admins
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.complaints.models import Complaint


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Escalate overdue high and medium priority complaints."

    def handle(self, *args, **options):
        now = timezone.now()

        complaints = Complaint.objects.filter(
            escalated_at__isnull=True,
            status__in=[
                Complaint.Status.OPEN,
                Complaint.Status.IN_PROGRESS,
            ],
            priority__in=[
                Complaint.Priority.HIGH,
                Complaint.Priority.MEDIUM,
            ],
        ).select_related("created_by", "assigned_to")

        escalated_count = 0

        for complaint in complaints:
            deadline = complaint.sla_deadline

            if deadline is None or now < deadline:
                continue

            subject = (
                f"Complaint SLA escalation: {complaint.title}"
            )

            message = (
                f"Complaint: {complaint.title}\n"
                f"Category: {complaint.get_category_display()}\n"
                f"Priority: {complaint.get_priority_display()}\n"
                f"Status: {complaint.get_status_display()}\n"
                f"Submitted by: {complaint.created_by}\n"
                f"Assigned to: {complaint.assigned_to or 'Not assigned'}\n"
                f"Submitted on: {complaint.created_at}\n"
                f"SLA deadline: {deadline}\n"
            )

            try:
                mail_admins(
                    subject,
                    message,
                    fail_silently=False,
                )
            except Exception:
                logger.exception(
                    "Could not send escalation email for complaint %s",
                    complaint.pk,
                )
                continue

            complaint.escalated_at = now
            complaint.save(update_fields=["escalated_at"])

            escalated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Escalation check completed. "
                f"{escalated_count} complaint(s) escalated."
            )
        )