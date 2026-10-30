from django.core.management.base import BaseCommand

from apps.fees.services import process_overdue_invoices


class Command(BaseCommand):
    help = "Mark past-due invoices Overdue and send resident/guardian reminders."

    def handle(self, *args, **options):
        result = process_overdue_invoices()
        self.stdout.write(
            "Overdue invoice processing complete: "
            f"{result['marked_overdue']} marked overdue, "
            f"{result['reminders_sent']} reminders sent, "
            f"{result['reminders_failed']} failed, "
            f"{result['reminders_skipped']} skipped (no email address)."
        )
