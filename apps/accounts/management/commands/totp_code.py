from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice


class Command(BaseCommand):
    help = (
        "Print the current authenticator code for a user. For demos and local testing only: "
        "it refuses to run unless DJANGO_DEBUG is on."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, username, **options):
        if not settings.DEBUG:
            raise CommandError("totp_code only runs in development (DJANGO_DEBUG=true).")
        device = TOTPDevice.objects.filter(user__username=username, confirmed=True).first()
        if device is None:
            raise CommandError(f"{username} has not linked an authenticator app yet.")
        token = TOTP(device.bin_key, device.step, device.t0, device.digits).token()
        self.stdout.write(f"{token:0{device.digits}d}")
