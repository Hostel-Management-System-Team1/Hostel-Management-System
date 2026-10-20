from django.core.management.base import BaseCommand, CommandError

from apps.audit import service
from apps.audit.models import AuditEntry


class Command(BaseCommand):
    help = (
        "Check the audit log's hash chain. Exits with an error if any entry was changed or "
        "removed. Run it on a schedule and keep the printed head hash somewhere else: it also "
        "exposes entries cut off the end of the log."
    )

    def handle(self, *args, **options):
        checked, problems = service.verify_chain()
        if problems:
            for problem in problems:
                self.stderr.write(problem)
            raise CommandError(f"Audit log failed verification ({len(problems)} problems).")
        head = AuditEntry.objects.order_by("-seq").first()
        message = f"{checked} audit entries verified."
        if head:
            message += f" Head: #{head.seq} {head.hash}"
        self.stdout.write(message)
