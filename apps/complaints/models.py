"""Complaint Service — HMS-F-040 to HMS-F-042 (issue #11)."""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Complaint(models.Model):

    class Category(models.TextChoices):
        MAINTENANCE = "MAINTENANCE", "Maintenance"
        CLEANING = "CLEANING", "Cleaning"
        NOISE = "NOISE", "Noise"
        OTHER = "OTHER", "Other"

    class Priority(models.TextChoices):
        HIGH = "HIGH", "High"
        MEDIUM = "MEDIUM", "Medium"
        LOW = "LOW", "Low"

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

    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.LOW,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )

    photo = models.ImageField(
        upload_to="complaints/",
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="hostel_complaints",
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_complaints",
    )

    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    resolution_confirmed = models.BooleanField(default=False)
    escalated_at = models.DateTimeField(null=True, blank=True)

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
        end = self.resolved_at or timezone.now()
        return max(0, (end - self.created_at).days)

    @property
    def sla_deadline(self):
        hours = {
            self.Priority.HIGH: 48,
            self.Priority.MEDIUM: 96,
        }.get(self.priority)

        if hours is None:
            return None

        return self.created_at + timedelta(hours=hours)

    @property
    def is_sla_overdue(self):
        deadline = self.sla_deadline
        return (
            self.is_open
            and deadline is not None
            and timezone.now() >= deadline
        )

    def save(self, *args, **kwargs):
        priority_by_category = {
            self.Category.MAINTENANCE: self.Priority.HIGH,
            self.Category.CLEANING: self.Priority.MEDIUM,
            self.Category.NOISE: self.Priority.LOW,
            self.Category.OTHER: self.Priority.LOW,
        }

        self.priority = priority_by_category.get(
            self.category,
            self.Priority.LOW,
        )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"