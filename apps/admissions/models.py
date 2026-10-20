"""Admission & Allocation Service — HMS-F-001 to HMS-F-003 (issues #1, #2, #6)."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

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


class Application(models.Model):
    """A hostel admission application (HMS-F-001)."""

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

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
