
from django.core.management.base import BaseCommand

from apps.gate.services import process_curfew_alerts


class Command(BaseCommand):
    help = "Detect residents who have not returned after curfew and notify wardens."

    def handle(self, *args, **options):
        result = process_curfew_alerts()

        self.stdout.write(
            self.style.SUCCESS(
                "Curfew processing complete: "
                f"{result['alerts_created']} alerts created, "
                f"{result['notifications_sent']} notifications sent, "
                f"{result['notifications_failed']} notifications failed."
            )
        )
