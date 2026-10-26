"""Complaint Service — HMS-F-040 to HMS-F-042 (issue #11)."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Complaint(models.Model):
    """A hostel complaint used for complaint-ageing reports."""

    class Category(models.TextChoices):
        MAINTENANCE = "MAINTENANCE", "Maintenance"
        CLEANING = "CLEANING", "Cleaning"
        NOISE = "NOISE", "Noise"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    title = models.CharField(max_length=150)
    description = models.TextField()
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="hostel_complaints",
    )
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "created_at"]

    @property
    def is_open(self):
        return self.status in (
            self.Status.OPEN,
            self.Status.IN_PROGRESS,
        )

    @property
    def age_days(self):
        """Age in whole days; open complaints are measured until now."""
        end = self.resolved_at or timezone.now()
        return max(0, (end - self.created_at).days)

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
