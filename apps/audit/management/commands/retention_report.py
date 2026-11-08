"""Report potentially eligible HMS records for retention review (HMS-NF-005).

This command is report-only. It never deletes, archives, or anonymizes records.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.admissions.models import Allocation, Application
from apps.fees.models import Invoice, Payment, Receipt
from apps.gate.models import GateMovement, OutpassRequest
from apps.visitors.models import Visitor


class Command(BaseCommand):
    """Report records older than the configured retention period."""

    help = (
        "Report resident, fee and gate records older than the retention period "
        "without modifying any data."
    )

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            "--years",
            type=int,
            default=5,
            help="Age threshold in years (default: 5).",
        )

    def handle(self, *args, **options):
        """Report counts of potentially aged records without changing data."""
        years = options["years"]

        if years < 1:
            raise CommandError("--years must be at least 1.")

        today = date.today()
        try:
            cutoff = today.replace(year=today.year - years)
        except ValueError:  # 29 February in a non-leap year
            cutoff = today.replace(year=today.year - years, day=28)

        self.stdout.write(
            self.style.WARNING(
                f"REPORT ONLY - threshold date: {cutoff}; no records will be changed."
            )
        )

        checks = [
            ("Completed allocations", Allocation.objects.filter(ended_at__date__lt=cutoff)),
            ("Admission applications", Application.objects.filter(submitted_at__date__lt=cutoff)),
            ("Invoices", Invoice.objects.filter(issue_date__lt=cutoff)),
            ("Payments", Payment.objects.filter(created_at__date__lt=cutoff)),
            ("Receipts", Receipt.objects.filter(issued_at__date__lt=cutoff)),
            ("Gate movements", GateMovement.objects.filter(occurred_at__date__lt=cutoff)),
            ("Outpass requests", OutpassRequest.objects.filter(requested_at__date__lt=cutoff)),
            ("Visitor records", Visitor.objects.filter(created_at__date__lt=cutoff)),
        ]
        for label, records in checks:
            self.stdout.write(f"{label}: {records.count()}")

        self.stdout.write(
            self.style.WARNING(
                "These counts identify records for review only. "
                "They do not authorize deletion or anonymization."
            )
        )
