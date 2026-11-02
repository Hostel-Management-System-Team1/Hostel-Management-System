"""Anonymise personal data once the retention period has passed (HMS-NF-005).

Records are kept, so a five-year-old allocation, invoice or gate movement can still be
retrieved; only the personal details on them are blanked. Without --apply the command
only reports what it would change.
"""

from datetime import date

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import CharField, Max, Q, Value
from django.db.models.functions import Cast, Concat

from apps.accounts.models import User
from apps.admissions.models import Application
from apps.audit import service as audit
from apps.gate.models import OutpassRequest
from apps.visitors.models import Visitor


def cutoff_for(years):
    today = date.today()
    try:
        return today.replace(year=today.year - years)
    except ValueError:  # 29 February
        return today.replace(year=today.year - years, day=28)


class Command(BaseCommand):
    help = "Anonymise residents, visitors and outpass contacts older than the retention period."

    def add_arguments(self, parser):
        parser.add_argument("--years", type=int, default=5, help="Retention period (default 5).")
        parser.add_argument("--apply", action="store_true", help="Make the changes.")

    def handle(self, *args, **options):
        if options["years"] < 1:
            raise CommandError("--years must be at least 1.")
        cutoff = cutoff_for(options["years"])

        # Former residents: no current bed, and their last bed ended before the cutoff.
        residents = (
            User.objects.filter(role=User.Role.RESIDENT, allocations__isnull=False)
            .exclude(allocations__ended_at__isnull=True)
            .exclude(username__startswith="former-")
            .annotate(last_left=Max("allocations__ended_at"))
            .filter(last_left__date__lt=cutoff)
        )
        visitors = Visitor.objects.filter(created_at__date__lt=cutoff).exclude(
            visitor_name="Visitor")
        outpasses = OutpassRequest.objects.filter(requested_at__date__lt=cutoff).exclude(
            Q(contact_number="") & Q(destination="Withheld"))

        counts = {
            "residents": residents.count(),
            "visitors": visitors.count(),
            "outpasses": outpasses.count(),
        }
        mode = "Anonymised" if options["apply"] else "Would anonymise (dry run, add --apply)"
        self.stdout.write(f"Cutoff {cutoff}. {mode}: " + ", ".join(
            f"{n} {label}" for label, n in counts.items()))
        if not options["apply"] or not any(counts.values()):
            return

        with transaction.atomic():
            ids = list(residents.values_list("pk", flat=True))
            for pk in ids:
                User.objects.filter(pk=pk).update(
                    username=f"former-{pk}", first_name="Former", last_name="resident",
                    email="", phone="", is_active=False, password=make_password(None),
                )
            Application.objects.filter(applicant_id__in=ids).update(
                full_name="Former resident",
                enrolment_number=Concat(Value("ANON"), Cast("pk", CharField())), phone="", email="",
                address="", date_of_birth=date(1900, 1, 1), guardian_name="",
                guardian_relation="", guardian_phone="", guardian_email="", blood_group="",
                medical_conditions="",
            )
            visitors.update(visitor_name="Visitor", phone="", id_proof_type="", id_proof_number="")
            outpasses.update(contact_number="", destination="Withheld")
            audit.record("retention.anonymised", actor=None, detail={
                "cutoff": str(cutoff), **counts,
            })
