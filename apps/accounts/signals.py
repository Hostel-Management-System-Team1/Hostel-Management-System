"""Account-management and sign-in events for the audit log (HMS-SR-004)."""

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.audit import service as audit

from .models import User


@receiver(post_save, sender=User, dispatch_uid="accounts.audit_user_saved")
def audit_user_saved(sender, instance, created, **kwargs):
    if created:
        audit.record("account.created", target=instance, detail={"role": instance.role})
    else:
        loaded = getattr(instance, "_loaded", {})
        changes = {
            field: [loaded[field], getattr(instance, field)]
            for field in ("role", "is_active")
            if field in loaded and loaded[field] != getattr(instance, field)
        }
        if changes:
            audit.record("account.updated", target=instance, detail={"changes": changes})
    if getattr(instance, "_password_changed", False):
        instance._password_changed = False
        if not created:
            audit.record("account.password_changed", target=instance)
    instance._loaded = {"role": instance.role, "is_active": instance.is_active}


@receiver(post_delete, sender=User, dispatch_uid="accounts.audit_user_deleted")
def audit_user_deleted(sender, instance, **kwargs):
    audit.record("account.deleted", detail={"username": instance.username, "role": instance.role})


@receiver(user_logged_in, dispatch_uid="accounts.audit_login")
def audit_login(sender, request, user, **kwargs):
    audit.record("auth.login", target=user, actor=user)


@receiver(user_logged_out, dispatch_uid="accounts.audit_logout")
def audit_logout(sender, request, user, **kwargs):
    if user is not None:
        audit.record("auth.logout", target=user, actor=user)


@receiver(user_login_failed, dispatch_uid="accounts.audit_login_failed")
def audit_login_failed(sender, credentials, request=None, **kwargs):
    audit.record(
        "auth.login_failed", actor=None, outcome=audit.AuditEntry.Outcome.FAILURE,
        label=str(credentials.get("username", ""))[:150],
        detail={"username": str(credentials.get("username", ""))[:150]},
    )
