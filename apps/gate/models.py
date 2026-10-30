
from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.admissions.models import Block


class GateMovement(models.Model):
    """A resident's entry or exit at the hostel gate (HMS-F-020)."""

    class Direction(models.TextChoices):
        IN = "IN", "Entry"
        OUT = "OUT", "Exit"

    class CaptureMethod(models.TextChoices):
        RFID = "RFID", "RFID"
        BIOMETRIC = "BIOMETRIC", "Biometric"
        MANUAL = "MANUAL", "Manual"

    resident = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="gate_movements",
    )
    direction = models.CharField(max_length=3, choices=Direction.choices)
    capture_method = models.CharField(
        max_length=10,
        choices=CaptureMethod.choices,
    )
    occurred_at = models.DateTimeField(db_index=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_gate_movements",
        null=True,
        blank=True,
    )
    external_event_id = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
    )
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(
                fields=["resident", "-occurred_at"],
                name="gate_resident_time_idx",
            ),
        ]

    def __str__(self):
        return f"{self.resident} - {self.get_direction_display()} at {self.occurred_at}"


class CurfewConfiguration(models.Model):
    """The configured curfew time for a hostel block (HMS-F-022)."""

    block = models.OneToOneField(
        Block,
        on_delete=models.CASCADE,
        related_name="curfew_configuration",
    )
    curfew_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.block.name} - curfew {self.curfew_time}"


class CurfewAlert(models.Model):
    """Tracks a resident's curfew violation and warden notification (HMS-F-022)."""

    resident = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="curfew_alerts",
    )
    block = models.ForeignKey(
        Block,
        on_delete=models.PROTECT,
        related_name="curfew_alerts",
    )
    curfew_date = models.DateField()
    detected_at = models.DateTimeField(default=timezone.now)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["resident", "curfew_date"],
                name="unique_resident_curfew_alert",
            )
        ]
        ordering = ["-detected_at"]

    def __str__(self):
        return f"Curfew alert: {self.resident} ({self.curfew_date})"
