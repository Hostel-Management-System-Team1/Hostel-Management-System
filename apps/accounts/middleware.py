from urllib.parse import urlencode

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from hms.api import error_body

from .models import User

# Warden and Administrator sign-ins need a second factor (HMS-SR-003).
MFA_ROLES = {User.Role.WARDEN, User.Role.ADMINISTRATOR}


class MFARequiredMiddleware:
    """Keep a Warden or Administrator who has typed only a password out of everything else."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (
            user.is_authenticated
            and user.role in MFA_ROLES
            and not user.is_verified()
            and not self.exempt(request.path)
        ):
            if request.path.startswith("/api/"):
                body = error_body(request, 403, "Multi-factor verification required.")
                return JsonResponse(body, status=403)
            query = urlencode({"next": request.get_full_path()})
            return redirect(f"{reverse('mfa')}?{query}")
        return self.get_response(request)

    @staticmethod
    def exempt(path):
        return path in {reverse("mfa"), reverse("logout")} or path.startswith(settings.STATIC_URL)
