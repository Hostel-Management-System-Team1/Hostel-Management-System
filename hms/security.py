"""Response headers that limit what a page can do (HMS-SR-006, defence against XSS)."""

from django.db import DataError
from django.http import HttpResponseBadRequest

# Scripts only from this site and the Bootstrap CDN, never inline. Inline styles stay allowed
# because some admin widgets size bars with style attributes.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
    "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


class InputGuardMiddleware:
    """Turn input the database cannot store (NUL characters) into a 400, not a server error."""

    FORM_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if "%00" in request.META.get("QUERY_STRING", "").lower():
            return HttpResponseBadRequest("Invalid input.")
        if request.method == "POST" and request.content_type in self.FORM_TYPES:
            if any("\x00" in value for value in request.POST.values()):
                return HttpResponseBadRequest("Invalid input.")
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, DataError):
            return HttpResponseBadRequest("Invalid input.")
        return None


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", CSP)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            # Signed-in pages are not cached, so Back after signing out shows nothing private.
            response["Cache-Control"] = "no-store"
        return response
