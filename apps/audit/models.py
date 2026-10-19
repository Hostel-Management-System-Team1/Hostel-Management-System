"""Audit Service — HMS-SR-004 (issue #5).

The log is append-only and tamper-evident: every entry stores a SHA-256 hash of its own
fields chained to the hash of the entry before it, so editing or removing an entry breaks the
chain from that point on. The database also refuses UPDATE and DELETE on the table (a trigger
in migration 0002), and the application offers no way to edit it.
"""

import hashlib
import json

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

GENESIS_HASH = "0" * 64


class AuditImmutable(Exception):
    """An attempt to change or delete an audit entry."""


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AuditImmutable("Audit entries cannot be edited.")

    def delete(self):
        raise AuditImmutable("Audit entries cannot be deleted.")

    def bulk_update(self, *args, **kwargs):
        raise AuditImmutable("Audit entries cannot be edited.")


class AuditEntry(models.Model):
    class Outcome(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        FAILURE = "FAILURE", "Failure"
        DENIED = "DENIED", "Denied"

    seq = models.PositiveBigIntegerField(unique=True, editable=False)
    timestamp = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", editable=False,
    )
    actor_label = models.CharField(max_length=150, editable=False)
    action = models.CharField(max_length=60, editable=False, db_index=True)
    category = models.CharField(max_length=30, editable=False, db_index=True)
    target_type = models.CharField(max_length=60, blank=True, editable=False)
    target_id = models.CharField(max_length=40, blank=True, editable=False)
    target_repr = models.CharField(max_length=200, blank=True, editable=False)
    outcome = models.CharField(max_length=8, choices=Outcome.choices, editable=False)
    detail = models.JSONField(default=dict, blank=True, editable=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True, editable=False)
    prev_hash = models.CharField(max_length=64, editable=False)
    hash = models.CharField(max_length=64, editable=False)

    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ["-seq"]
        verbose_name = "audit entry"
        verbose_name_plural = "audit log"

    def __str__(self):
        return f"#{self.seq} {self.action} ({self.outcome})"

    def payload(self):
        """The fields the hash covers, in a form that survives a round trip through the database."""
        return {
            "seq": self.seq,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor_id,
            "actor_label": self.actor_label,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "target_repr": self.target_repr,
            "outcome": self.outcome,
            "detail": self.detail,
            "ip": self.ip_address,
        }

    def compute_hash(self):
        body = json.dumps(self.payload(), sort_keys=True, separators=(",", ":"),
                          cls=DjangoJSONEncoder)
        return hashlib.sha256(f"{self.prev_hash}|{body}".encode()).hexdigest()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditImmutable("Audit entries cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditImmutable("Audit entries cannot be deleted.")
