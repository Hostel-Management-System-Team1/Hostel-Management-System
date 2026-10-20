"""Helpers for tests that sign people in."""

from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from .middleware import MFA_ROLES
from .models import User

PASSWORD = "x-Strong-pass-1"


def verify_mfa(client, user):
    """Mark the client's session as having passed the second step, if the user's role needs it."""
    if user.role in MFA_ROLES:
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first() or (
            TOTPDevice.objects.create(user=user, name="test", confirmed=True)
        )
        session = client.session
        session[DEVICE_ID_SESSION_KEY] = device.persistent_id
        session.save()


def login(client, username, password=PASSWORD):
    """Sign in with a password and, for Warden and Administrator, pass the second step."""
    assert client.login(username=username, password=password), "login failed"
    verify_mfa(client, User.objects.get(username=username))


def sign_in(client, user):
    """Sign `user` in without a password (and through MFA when their role needs it)."""
    client.force_login(user)
    verify_mfa(client, user)
