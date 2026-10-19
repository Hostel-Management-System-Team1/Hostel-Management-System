"""Fee & Payment Service — HMS-F-010 to HMS-F-013 (issues #3, #7)."""

import uuid
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.admissions.models import RoomType


def new_session_id():
    return uuid.uuid4().hex


class FeeHead(models.Model):
    """One line of the fee structure for a room type (for example room rent for a double room)."""

    name = models.CharField(max_length=60)
    room_type = models.CharField(max_length=10, choices=RoomType.choices)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    refundable = models.BooleanField(
        default=False, help_text="Refundable when the resident vacates (the security deposit)."
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["room_type", "id"]
        constraints = [
            models.UniqueConstraint(fields=["name", "room_type"], name="unique_fee_head_per_type")
        ]

    def __str__(self):
        return f"{self.name} — {self.get_room_type_display()}"


class Invoice(models.Model):
    """An itemised invoice (HMS-F-010). Its total is the sum of its items."""

    class Kind(models.TextChoices):
        ALLOCATION = "ALLOCATION", "Hostel fees"
        MESS = "MESS", "Mess bill"

    class Status(models.TextChoices):
        UNPAID = "UNPAID", "Unpaid"
        PAID = "PAID", "Paid"
        OVERDUE = "OVERDUE", "Overdue"

    number = models.CharField(max_length=24, unique=True, editable=False)
    resident = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="invoices"
    )
    allocation = models.ForeignKey(
        "admissions.Allocation", null=True, blank=True, on_delete=models.PROTECT,
        related_name="invoices",
    )
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.ALLOCATION)
    description = models.CharField(max_length=120)
    issue_date = models.DateField(default=date.today)
    due_date = models.DateField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.UNPAID)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issue_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["allocation"],
                condition=models.Q(kind="ALLOCATION") & models.Q(allocation__isnull=False),
                name="one_hostel_fee_invoice_per_allocation",
            )
        ]

    def __str__(self):
        return f"{self.number} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if self.number:
            return super().save(*args, **kwargs)
        self.number = f"TMP-{uuid.uuid4().hex[:16]}"
        super().save(*args, **kwargs)
        self.number = f"INV-{self.issue_date.year}-{self.pk:06d}"
        type(self).objects.filter(pk=self.pk).update(number=self.number)

    @property
    def is_payable(self):
        return self.status != self.Status.PAID

    @property
    def refundable_total(self):
        return sum((i.amount for i in self.items.all() if i.refundable), Decimal("0.00"))


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=80)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    refundable = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.description}: {self.amount}"


class Payment(models.Model):
    """One attempt to pay an invoice through the gateway (HMS-F-011).

    Only the method's name and the gateway's reference are kept. Card numbers, CVV and bank
    credentials never reach the HMS (HMS-SR-005): they are typed on the gateway's own page.
    """

    class Status(models.TextChoices):
        INITIATED = "INITIATED", "Started"
        SUCCESS = "SUCCESS", "Successful"
        FAILED = "FAILED", "Failed"
        ABANDONED = "ABANDONED", "Abandoned"
        DUPLICATE = "DUPLICATE", "Duplicate (invoice already paid)"

    class Method(models.TextChoices):
        CARD = "CARD", "Card"
        UPI = "UPI", "UPI"
        NETBANKING = "NETBANKING", "Net banking"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    session_id = models.CharField(max_length=32, unique=True, default=new_session_id)
    method = models.CharField(max_length=12, choices=Method.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.INITIATED)
    gateway_ref = models.CharField(max_length=60, blank=True)
    return_url = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.invoice.number} · {self.get_status_display()}"


class Receipt(models.Model):
    """Issued once per successful payment, with a unique number (HMS-F-012)."""

    number = models.CharField(max_length=24, unique=True, editable=False)
    invoice = models.OneToOneField(Invoice, on_delete=models.PROTECT, related_name="receipt")
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="receipt")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if self.number:
            return super().save(*args, **kwargs)
        self.number = f"TMP-{uuid.uuid4().hex[:16]}"
        super().save(*args, **kwargs)
        self.number = f"RCT-{self.issued_at.year}-{self.pk:06d}"
        type(self).objects.filter(pk=self.pk).update(number=self.number)
