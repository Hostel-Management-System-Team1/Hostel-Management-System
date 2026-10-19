"""Who is acting, for code (such as model signals) that has no request to hand."""

from contextvars import ContextVar

_request = ContextVar("audit_request", default=None)


def current_request():
    return _request.get()


def current_actor():
    request = _request.get()
    user = getattr(request, "user", None)
    return user if user is not None and user.is_authenticated else None


class AuditContextMiddleware:
    """Remember the request while it is being handled."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request.set(request)
        try:
            return self.get_response(request)
        finally:
            _request.reset(token)
