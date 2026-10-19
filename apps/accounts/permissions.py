"""Role-based access control (HMS-SR-002).

Every restricted view declares the roles allowed to use it, in one of three ways:

* ``@role_required(Role.WARDEN, ...)`` on a function view,
* ``RoleRequiredMixin`` with ``allowed_roles`` on a class-based view,
* ``permission_classes = [roles(Role.WARDEN, ...)]`` on a DRF view.

Anonymous visitors are sent to the sign-in page; a signed-in user whose role is not listed
gets HTTP 403. The access-matrix test (test_rbac.py) finds these declarations in the URL
configuration and checks every other role is refused, so a new restricted view is covered
as soon as it declares its roles.
"""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from rest_framework import permissions

from apps.audit import service as audit


def log_denied(request):
    """Record a refused request in the audit log (HMS-SR-004)."""
    audit.record(
        "access.denied", outcome=audit.AuditEntry.Outcome.DENIED,
        detail={"path": request.path, "method": request.method},
    )


def role_required(*roles):
    allowed = frozenset(roles)

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role not in allowed:
                log_denied(request)
                raise PermissionDenied
            return view(request, *args, **kwargs)

        wrapper.allowed_roles = allowed
        return wrapper

    return decorator


class RoleRequiredMixin:
    """For class-based views: set ``allowed_roles`` to a tuple of roles."""

    allowed_roles = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if request.user.role not in self.allowed_roles:
            log_denied(request)
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def roles(*allowed):
    """DRF permission class: the user must be signed in and have one of these roles."""

    class HasRole(permissions.BasePermission):
        allowed_roles = frozenset(allowed)

        def has_permission(self, request, view):
            user = request.user
            allowed = bool(user and user.is_authenticated and user.role in self.allowed_roles)
            if not allowed and user and user.is_authenticated:
                log_denied(request)
            return allowed

    return HasRole


def allowed_roles_of(callback):
    """The roles a resolved URL's view admits, or None when it declares none."""
    declared = getattr(callback, "allowed_roles", None)
    if declared is None:
        view_class = getattr(callback, "view_class", None)
        declared = getattr(view_class, "allowed_roles", None)
    if declared is None:
        for permission in getattr(getattr(callback, "cls", None), "permission_classes", ()):
            declared = getattr(permission, "allowed_roles", declared)
    return frozenset(declared) if declared else None
