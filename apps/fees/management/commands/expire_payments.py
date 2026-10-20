from django.core.management.base import BaseCommand

from apps.fees.services import abandon_stale_payments


class Command(BaseCommand):
    help = "Mark payment sessions that were started but never finished as Abandoned."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=30)

    def handle(self, *args, minutes, **options):
        count = abandon_stale_payments(minutes)
        self.stdout.write(f"{count} stale payment sessions marked Abandoned.")
