import base64
import io

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from .forms import OTPTokenForm
from .middleware import MFA_ROLES


def qr_svg(data):
    """The QR code for ``data`` as inline SVG markup."""
    image = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    buffer = io.BytesIO()
    image.save(buffer)
    return mark_safe(buffer.getvalue().decode().split("?>", 1)[-1])


def secret_groups(device):
    """The device secret as base32 in groups of four, for typing into an authenticator app."""
    key = base64.b32encode(device.bin_key).decode().rstrip("=")
    return " ".join(key[i : i + 4] for i in range(0, len(key), 4))


@login_required
def mfa(request):
    """Second step of sign-in for Warden and Administrator accounts.

    A first-time user links an authenticator app (scan the QR code, type the code it shows);
    everyone after that just types the current code.
    """
    user = request.user
    target = request.GET.get("next") or request.POST.get("next") or ""
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = ""
    if user.role not in MFA_ROLES or user.is_verified():
        return redirect(target or "home")

    device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    enrolling = device is None
    if enrolling:
        device = TOTPDevice.objects.filter(user=user, confirmed=False).first() or (
            TOTPDevice.objects.create(user=user, name="Authenticator app", confirmed=False)
        )

    form = OTPTokenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if device.verify_token(form.cleaned_data["token"]):
            if enrolling:
                device.confirmed = True
                device.save(update_fields=["confirmed"])
                messages.success(request, "Authenticator app linked.")
            otp_login(request, device)
            return redirect(target or "home")
        form.add_error("token", "That code is not right, or it has expired. Try the next one.")

    context = {"form": form, "enrolling": enrolling, "next": target}
    if enrolling:
        context["qr"] = qr_svg(device.config_url)
        context["secret"] = secret_groups(device)
    return render(request, "registration/mfa.html", context)
