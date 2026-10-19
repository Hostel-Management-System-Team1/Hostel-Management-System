from django.core.management.base import BaseCommand

from apps.admissions.models import Allocation
from apps.fees.models import Invoice
from apps.fees.services import generate_invoice


class Command(BaseCommand):
    help = (
        "Raise the invoice for active allocations that have none, for example after the "
        "administrator added a fee structure for a room type."
    )

    def handle(self, *args, **options):
        raised = 0
        missing = Allocation.objects.filter(status=Allocation.Status.ACTIVE).exclude(
            invoices__kind=Invoice.Kind.ALLOCATION)
        for allocation in missing:
            if generate_invoice(allocation):
                raised += 1
        self.stdout.write(f"{raised} invoices raised.")
