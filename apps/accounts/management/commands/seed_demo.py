from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.admissions.models import Block

PASSWORD = "demo-pass-123"
# Fixed authenticator key so the demo accounts' codes can be read with `manage.py totp_code`.
DEMO_TOTP_KEY = "3132333435363738393031323334353637383930"

PEOPLE = [
    ("admin", "Asha", "Menon", User.Role.ADMINISTRATOR),
    ("warden", "Wendy", "Rao", User.Role.WARDEN),
    ("guard", "Gopal", "Singh", User.Role.SECURITY_GUARD),
    ("maintenance", "Manoj", "Kumar", User.Role.MAINTENANCE_STAFF),
    ("mess", "Meera", "Nair", User.Role.MESS_MANAGER),
    ("aarav", "Aarav", "Sharma", User.Role.RESIDENT),
    ("diya", "Diya", "Patel", User.Role.RESIDENT),
    # Two residents who have not applied yet, for trying the application form.
    ("neha", "Neha", "Kapoor", User.Role.RESIDENT),
    ("omar", "Omar", "Sheikh", User.Role.RESIDENT),
]


class Command(BaseCommand):
    help = "Create demo accounts (one per role) and sample data. Development only; safe to re-run."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs in development (DJANGO_DEBUG=true).")
        for username, first, last, role in PEOPLE:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "role": role,
                          "email": f"{username}@example.edu", "phone": "9876543210"},
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            if role in {User.Role.WARDEN, User.Role.ADMINISTRATOR}:
                TOTPDevice.objects.get_or_create(
                    user=user, name="Demo authenticator",
                    defaults={"key": DEMO_TOTP_KEY, "confirmed": True},
                )
        Block.objects.get_or_create(name="Block A", defaults={"gender": "M"})
        Block.objects.get_or_create(name="Block B", defaults={"gender": "F"})
        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready. Sign in as admin, warden, guard, maintenance, mess, aarav, "
            f"diya, neha or omar with password {PASSWORD}. For admin and warden the "
            f"second-step code comes from: python manage.py totp_code <username>"
        ))
