
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
        return (
            f"{self.resident} - "
            f"{self.get_direction_display()} at {self.occurred_at}"
        )


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


class OutpassRequest(models.Model):
    """Resident leave request and warden decision (HMS-F-021)."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    resident = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="outpass_requests",
    )
    allocation = models.ForeignKey(
        "admissions.Allocation",
        on_delete=models.PROTECT,
        related_name="outpass_requests",
    )
    destination = models.CharField(max_length=200)
    contact_number = models.CharField(max_length=16)
    expected_return_at = models.DateTimeField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="decided_outpasses",
        null=True,
        blank=True,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.CharField(max_length=300, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["status", "expected_return_at"]),
            models.Index(fields=["resident", "status"]),
        ]

    def __str__(self):
        return f"Outpass #{self.pk} - {self.resident} ({self.status})"


class NightAttendance(models.Model):
    """Room-wise daily night attendance (HMS-F-023)."""

    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        ON_LEAVE = "ON_LEAVE", "On-leave"
        ABSENT = "ABSENT", "Absent"

    resident = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="night_attendance",
    )
    room = models.ForeignKey(
        "admissions.Room",
        on_delete=models.PROTECT,
        related_name="night_attendance",
    )
    attendance_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_night_attendance",
        null=True,
        blank=True,
    )
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = [
            "room__block__name",
            "room__number",
            "resident__username",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["resident", "attendance_date"],
                name="unique_resident_night_attendance",
            )
        ]
        indexes = [
            models.Index(fields=["attendance_date", "room"]),
        ]

    def __str__(self):
        return (
            f"{self.resident} - {self.attendance_date} "
            f"({self.get_status_display()})"
        )
