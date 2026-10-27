
import base64
import csv
import secrets
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Create isolated Warden accounts for authenticated Locust load tests."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=200)

    @transaction.atomic
    def handle(self, *args, **options):
        count = options["count"]

        if not settings.DEBUG:
            raise CommandError(
                "This command is for development testing only."
            )

        if connection.vendor != "postgresql":
            raise CommandError("This command requires PostgreSQL.")

        if connection.settings_dict["NAME"] != "hms_perf_test":
            raise CommandError(
                "Safety check failed: connect to hms_perf_test first."
            )

        if count < 1 or count > 200:
            raise CommandError("Count must be between 1 and 200.")

        output_path = Path.cwd() / "locust_users.csv"
        credentials = []

        for index in range(1, count + 1):
            username = f"perfwarden{index:03d}"
            password = secrets.token_urlsafe(18)

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": "Performance",
                    "last_name": f"Warden {index}",
                    "email": f"{username}@example.invalid",
                    "role": User.Role.WARDEN,
                },
            )

            if not created and user.role != User.Role.WARDEN:
                raise CommandError(
                    f"Existing account '{username}' is not a Warden. "
                    "Refusing to reset its password."
                )

            user.set_password(password)
            user.save()

            device = TOTPDevice.objects.filter(
                user=user,
                name="Locust performance authenticator",
            ).first()

            if device is None:
                device = TOTPDevice.objects.create(
                    user=user,
                    name="Locust performance authenticator",
                    key=secrets.token_hex(20),
                    confirmed=True,
                )
            elif not device.confirmed:
                device.confirmed = True
                device.save(update_fields=["confirmed"])

            # Convert the hexadecimal device key to Base32 for pyotp.
            secret_base32 = base64.b32encode(
                bytes.fromhex(device.key)
            ).decode("ascii").rstrip("=")

            credentials.append(
                {
                    "username": username,
                    "password": password,
                    "totp_secret": secret_base32,
                }
            )

        with output_path.open(
            "w", newline="", encoding="utf-8"
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["username", "password", "totp_secret"],
            )
            writer.writeheader()
            writer.writerows(credentials)

        self.stdout.write(
            self.style.SUCCESS(
                f"Prepared {len(credentials)} performance accounts. "
                f"Credentials saved to {output_path}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "Keep locust_users.csv private. Do not commit or share it."
            )
        )
