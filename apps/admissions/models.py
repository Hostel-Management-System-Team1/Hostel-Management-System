"""Admission & Allocation Service — HMS-F-001 to HMS-F-003 (issues #1, #2, #6)."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from . import validators


class Gender(models.TextChoices):
    MALE = "M", "Male"
    FEMALE = "F", "Female"


class RoomType(models.TextChoices):
    SINGLE = "SINGLE", "Single"
    DOUBLE = "DOUBLE", "Double sharing"
    TRIPLE = "TRIPLE", "Triple sharing"


class Block(models.Model):
    """A hostel building. Hostels are gender-segregated, so a block has exactly one gender."""

    name = models.CharField(max_length=30, unique=True)
    gender = models.CharField(max_length=1, choices=Gender.choices)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_gender_display()})"


ROOM_TYPE_CAPACITY = {RoomType.SINGLE: 1, RoomType.DOUBLE: 2, RoomType.TRIPLE: 3}


class Room(models.Model):
    """A room in a block. Its beds are created from ``bed_capacity`` (HMS-F-061)."""

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        BLOCKED = "BLOCKED", "Blocked (out of service)"

    block = models.ForeignKey(Block, on_delete=models.PROTECT, related_name="rooms")
    floor = models.PositiveSmallIntegerField(default=0, help_text="0 is the ground floor.")
    number = models.CharField(max_length=10)
    room_type = models.CharField(max_length=10, choices=RoomType.choices)
    bed_capacity = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(8)],
        help_text="Leave blank to use the usual capacity for the room type.",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE)

    class Meta:
        ordering = ["block__name", "floor", "number"]
        constraints = [
            models.UniqueConstraint(fields=["block", "number"], name="unique_room_number_in_block")
        ]

    def __str__(self):
        return f"{self.block.name} · {self.number}"

    def clean(self):
        super().clean()
        capacity = self.bed_capacity or ROOM_TYPE_CAPACITY.get(self.room_type)
        if self.pk and capacity:
            keep = self.beds.filter(models.Q(status=Bed.Status.OCCUPIED) | models.Q(
                allocations__isnull=False)).distinct().count()
            if capacity < keep:
                raise ValidationError(
                    {"bed_capacity": f"{keep} beds in this room are occupied or have a history of "
                     "residents, so the capacity cannot be lowered below that."}
                )

    def save(self, *args, **kwargs):
        if not self.bed_capacity:
            self.bed_capacity = ROOM_TYPE_CAPACITY.get(self.room_type, 1)
        super().save(*args, **kwargs)
        self.sync_beds()

    def sync_beds(self):
        """Create the beds a new capacity needs; drop unused spare beds when it shrinks."""
        existing = {bed.label: bed for bed in self.beds.all()}
        wanted = [chr(ord("A") + i) for i in range(self.bed_capacity)]
        for label in wanted:
            if label not in existing:
                Bed.objects.create(room=self, label=label)
        for label, bed in existing.items():
            if label not in wanted and not bed.allocations.exists():
                bed.delete()

    @property
    def occupied_count(self):
        return self.beds.filter(status=Bed.Status.OCCUPIED).count()


class Bed(models.Model):
    """The smallest allocatable unit. A bed is Occupied only through an active Allocation."""

    class Status(models.TextChoices):
        VACANT = "VACANT", "Vacant"
        OCCUPIED = "OCCUPIED", "Occupied"
        BLOCKED = "BLOCKED", "Blocked"

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="beds")
    label = models.CharField(max_length=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.VACANT)

    class Meta:
        ordering = ["room", "label"]
        constraints = [
            models.UniqueConstraint(fields=["room", "label"], name="unique_bed_label_in_room")
        ]

    def __str__(self):
        return f"{self.room} · bed {self.label}"


@receiver(pre_delete, sender=Room)
def refuse_to_delete_a_room_with_occupied_beds(sender, instance, **kwargs):
    """A room cannot be deleted while any bed in it is occupied (HMS-F-061)."""
    if instance.beds.filter(status=Bed.Status.OCCUPIED).exists():
        raise ProtectedError(f"{instance} has occupied beds and cannot be deleted.", {instance})


class AllocationPolicy(models.Model):
    """How applicants are ranked when beds are allocated; set by the administrator (HMS-F-002)."""

    class Ranking(models.TextChoices):
        MERIT = "MERIT", "Merit (highest CGPA first)"
        SENIORITY = "SENIORITY", "Seniority (senior years first, then CGPA)"
        FIRST_COME = "FIRST_COME", "First come, first served"

    ranking = models.CharField(max_length=12, choices=Ranking.choices, default=Ranking.MERIT)

    class Meta:
        verbose_name_plural = "allocation policy"

    def __str__(self):
        return f"Allocation order: {self.get_ranking_display()}"

    def save(self, *args, **kwargs):
        self.pk = 1  # a single settings row
        super().save(*args, **kwargs)

    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]


class Application(models.Model):
    """A hostel admission application (HMS-F-001)."""

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        ALLOCATED = "ALLOCATED", "Bed allocated"

    class BloodGroup(models.TextChoices):
        UNKNOWN = "", "Not known"
        A_POS = "A+", "A+"
        A_NEG = "A-", "A−"
        B_POS = "B+", "B+"
        B_NEG = "B-", "B−"
        AB_POS = "AB+", "AB+"
        AB_NEG = "AB-", "AB−"
        O_POS = "O+", "O+"
        O_NEG = "O-", "O−"

    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="applications"
    )
    application_number = models.CharField(max_length=24, unique=True, editable=False)
    academic_session = models.CharField(max_length=9)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED)
    submitted_at = models.DateTimeField(auto_now_add=True)

    # Personal
    enrolment_number = models.CharField(
        max_length=20, validators=[validators.enrolment_format],
        help_text="Your student enrolment number, for example PES2UG24CS582.",
    )
    full_name = models.CharField(max_length=100, validators=[validators.person_name])
    date_of_birth = models.DateField(validators=[validators.past_birth_date])
    gender = models.CharField(max_length=1, choices=Gender.choices)
    phone = models.CharField(max_length=16, validators=[validators.phone_number])
    email = models.EmailField()
    address = models.TextField(max_length=300, validators=[validators.plain_text])

    # Academic
    programme = models.CharField(
        max_length=80, validators=[validators.plain_text],
        help_text="For example B.Tech Computer Science.",
    )
    year_of_study = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    cgpa = models.DecimalField(
        "CGPA", max_digits=4, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text="Used to rank applicants when beds are allocated by merit.",
    )

    # Guardian
    guardian_name = models.CharField(max_length=100, validators=[validators.person_name])
    guardian_relation = models.CharField(max_length=30, validators=[validators.person_name])
    guardian_phone = models.CharField(max_length=16, validators=[validators.phone_number])
    guardian_email = models.EmailField(
        blank=True, help_text="Fee and outpass notices are sent here as well."
    )

    # Medical (visible to the applicant and the warden only)
    blood_group = models.CharField(max_length=3, choices=BloodGroup.choices, blank=True)
    medical_conditions = models.TextField(
        max_length=500, blank=True, validators=[validators.plain_text],
        help_text="Allergies, chronic conditions or regular medication. Leave blank if none.",
    )

    # Preferences
    preferred_block = models.ForeignKey(
        Block, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="Only blocks for your gender can be chosen.",
    )
    room_type = models.CharField(max_length=10, choices=RoomType.choices)

    # Decision
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["enrolment_number", "academic_session"],
                name="one_application_per_enrolment_and_session",
            ),
            models.UniqueConstraint(
                fields=["applicant", "academic_session"],
                name="one_application_per_applicant_and_session",
            ),
        ]

    def __str__(self):
        return f"{self.application_number} — {self.full_name}"

    def clean(self):
        super().clean()
        block = self.preferred_block
        if block and self.gender and block.gender != self.gender:
            raise ValidationError(
                {"preferred_block": "That block is not for your gender. Pick a block for "
                 f"{self.get_gender_display().lower()} residents or leave it blank."}
            )

    def save(self, *args, **kwargs):
        self.enrolment_number = validators.normalise_enrolment(self.enrolment_number)
        if self.application_number:
            return super().save(*args, **kwargs)
        # The number is derived from the row id, so it is unique without a counter table.
        self.application_number = f"TMP-{uuid.uuid4().hex[:16]}"
        super().save(*args, **kwargs)
        year = self.academic_session.split("-")[0]
        self.application_number = f"HMS-{year}-{self.pk:05d}"
        type(self).objects.filter(pk=self.pk).update(application_number=self.application_number)


class Allocation(models.Model):
    """A resident's bed (HMS-F-002). Transfers move the allocation to another bed (HMS-F-003)."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ENDED = "ENDED", "Ended"

    application = models.OneToOneField(
        Application, on_delete=models.PROTECT, related_name="allocation"
    )
    resident = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="allocations"
    )
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="allocations")
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.ACTIVE)
    allocated_at = models.DateTimeField(auto_now_add=True)
    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-allocated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["bed"], condition=models.Q(status="ACTIVE"),
                name="one_active_allocation_per_bed",
            ),
            models.UniqueConstraint(
                fields=["resident"], condition=models.Q(status="ACTIVE"),
                name="one_active_allocation_per_resident",
            ),
        ]

    def __str__(self):
        return f"{self.resident} → {self.bed}"

    def save(self, *args, **kwargs):
        # Gender-segregated hostels are a hard rule, enforced here as well as in the queries
        # that offer beds, so no code path can place a resident in the other gender's block.
        if self.bed.room.block.gender != self.application.gender:
            raise ValidationError("A resident cannot be placed in a block for the other gender.")
        super().save(*args, **kwargs)


class Transfer(models.Model):
    """A resident moved from one bed to another, with who, when and why (HMS-F-003)."""

    allocation = models.ForeignKey(Allocation, on_delete=models.PROTECT, related_name="transfers")
    from_bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="+")
    to_bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=300)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-performed_at"]

    def __str__(self):
        return f"{self.allocation.resident}: {self.from_bed} → {self.to_bed}"
class VacatingRequest(models.Model):
    """A resident's request to vacate their currently allocated bed (HMS-F-062)."""

    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Requested"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        COMPLETED = "COMPLETED", "Completed"

    allocation = models.ForeignKey(
        Allocation,
        on_delete=models.PROTECT,
        related_name="vacating_requests",
    )
    resident = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="vacating_requests",
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.REQUESTED,
    )
    reason = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approved_vacating_requests",
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    vacated_at = models.DateTimeField(null=True, blank=True)

    security_deposit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default="0.00",
    )
    outstanding_dues = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default="0.00",
    )
    damage_deduction = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default="0.00",
    )
    refund_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default="0.00",
    )
    staff_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["allocation"],
                condition=models.Q(status__in=["REQUESTED", "APPROVED"]),
                name="one_open_vacating_request_per_allocation",
            )
        ]

    def __str__(self):
        return f"Vacating request #{self.pk} - {self.resident}"


class NoDuesClearance(models.Model):
    """Tracks required departmental clearances before a resident vacates."""

    class Department(models.TextChoices):
        HOSTEL = "HOSTEL", "Hostel fees"
        MESS = "MESS", "Mess dues"
        MAINTENANCE = "MAINTENANCE", "Maintenance dues"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CLEARED = "CLEARED", "Cleared"

    vacating_request = models.ForeignKey(
        VacatingRequest,
        on_delete=models.CASCADE,
        related_name="clearances",
    )
    department = models.CharField(
        max_length=12,
        choices=Department.choices,
    )
    status = models.CharField(
        max_length=8,
        choices=Status.choices,
        default=Status.PENDING,
    )
    cleared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="recorded_no_dues_clearances",
    )
    cleared_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["department"]
        constraints = [
            models.UniqueConstraint(
                fields=["vacating_request", "department"],
                name="unique_department_clearance_per_vacating",
            )
        ]

    def __str__(self):
        return (
            f"{self.get_department_display()} - "
            f"{self.get_status_display()}"
        )


class DamageCharge(models.Model):
    """An itemized damage charge assessed during the vacating process."""

    vacating_request = models.ForeignKey(
        VacatingRequest,
        on_delete=models.CASCADE,
        related_name="damage_charges",
    )
    description = models.CharField(max_length=200)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assessed_vacating_damages",
    )
    assessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["assessed_at", "pk"]

    def __str__(self):
        return f"{self.description}: {self.amount}"
