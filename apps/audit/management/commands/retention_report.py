
"""Report potentially eligible HMS records for retention review.

This command is report-only. It never deletes, archives, or anonymizes records.
"""

from datetime import date

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    """Report records older than the configured retention period."""

    help = (
        "Report potentially aged admissions and fee records "
        "without modifying any data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--years",
            type=int,
            default=5,
            help="Age threshold in years (default: 5).",
        )

    def handle(self, *args, **options):
        years = options["years"]
        if years < 1:
            self.stderr.write("--years must be at least 1.")
            return

        cutoff = date.today() - relativedelta(years=years)
        self.stdout.write(
            self.style.WARNING(
                f"REPORT ONLY — threshold date: {cutoff}; "
                "no records will be changed."
            )
        )

        checks = [
            (
                "Completed allocations",
                """
                SELECT COUNT(*)
                FROM admissions_allocation
                WHERE ended_at IS NOT NULL
                  AND ended_at < %s
                """,
            ),
            (
                "Admission applications",
                """
                SELECT COUNT(*)
                FROM admissions_application
                WHERE submitted_at < %s
                """,
            ),
            (
                "Invoices",
                """
                SELECT COUNT(*)
                FROM fees_invoice
                WHERE issue_date < %s
                """,
            ),
            (
                "Payments",
                """
                SELECT COUNT(*)
                FROM fees_payment
                WHERE created_at < %s
                """,
            ),
            (
                "Receipts",
                """
                SELECT COUNT(*)
                FROM fees_receipt
                WHERE issued_at < %s
                """,
            ),
        ]

        with connection.cursor() as cursor:
            for label, query in checks:
                cursor.execute(query, [cutoff])
                count = cursor.fetchone()[0]
                self.stdout.write(f"{label}: {count}")

        self.stdout.write(
            self.style.WARNING(
                "These counts identify records for review only. "
                "They do not authorize deletion or anonymization."
            )
        )
        self.stdout.write(
            "Gate and visitor retention cannot be reported because "
            "their database tables are not currently present."
        )
