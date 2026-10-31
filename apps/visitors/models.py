from datetime import time

from django.conf import settings
from django.db import models


class Visitor(models.Model):
    class Status(models.TextChoices):
        REGISTERED = "REGISTERED", "Registered"
        INSIDE = "INSIDE", "Inside Hostel"
        EXITED = "EXITED", "Exited"

    visitor_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=15)
    id_proof_type = models.CharField(max_length=50, blank=True)
    id_proof_number = models.CharField(max_length=100, blank=True)

    resident = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="hostel_visitors",
        limit_choices_to={"role": "RESIDENT"},
    )

    purpose = models.CharField(max_length=255)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registered_visitors",
    )

    entry_time = models.DateTimeField(null=True, blank=True)
    exit_time = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REGISTERED,
    )

    override_reason = models.TextField(blank=True)
    overridden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="visitor_hour_overrides",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.visitor_name} visiting {self.resident}"


class VisitingHours(models.Model):
    start_time = models.TimeField(default=time(9, 0))
    end_time = models.TimeField(default=time(18, 0))
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Visiting hours: {self.start_time} - {self.end_time}"
