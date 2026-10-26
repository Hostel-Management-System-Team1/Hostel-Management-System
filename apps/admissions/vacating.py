"""Business rules for the hostel vacating workflow (HMS-F-062)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit import service as audit
from apps.fees.models import Invoice

from .models import (
    Allocation,
    Bed,
    DamageCharge,
    NoDuesClearance,
    VacatingRequest,
)

REQUIRED_DEPARTMENTS = (
    NoDuesClearance.Department.HOSTEL,
    NoDuesClearance.Department.MESS,
    NoDuesClearance.Department.MAINTENANCE,
)


@transaction.atomic
def submit_vacating_request(resident, reason=""):
    """Create a vacating request for the resident's active allocation."""
    allocation = (
        Allocation.objects.select_for_update()
        .filter(resident=resident, status=Allocation.Status.ACTIVE)
        .select_related("bed")
        .first()
    )

    if allocation is None:
        raise ValidationError("You do not have an active bed allocation to vacate.")

    if VacatingRequest.objects.filter(
        allocation=allocation,
        status__in=[
            VacatingRequest.Status.REQUESTED,
            VacatingRequest.Status.APPROVED,
        ],
    ).exists():
        raise ValidationError("A vacating request is already open for this allocation.")

    request = VacatingRequest.objects.create(
        allocation=allocation,
        resident=resident,
        reason=(reason or "").strip(),
    )

    NoDuesClearance.objects.bulk_create(
        [
            NoDuesClearance(
                vacating_request=request,
                department=department,
            )
            for department in REQUIRED_DEPARTMENTS
        ]
    )

    audit.record(
        "vacating.requested",
        target=request,
        actor=resident,
        detail={"allocation_id": allocation.pk},
    )

    return request


@transaction.atomic
def record_clearance(vacating_request, department, actor, cleared, notes=""):
    """Record a departmental no-dues clearance."""
    request = VacatingRequest.objects.select_for_update().get(pk=vacating_request.pk)

    if request.status != VacatingRequest.Status.REQUESTED:
        raise ValidationError(
            "Clearances can only be changed while the request is awaiting approval."
        )

    if department not in REQUIRED_DEPARTMENTS:
        raise ValidationError("Unknown clearance department.")

    clearance = NoDuesClearance.objects.select_for_update().get(
        vacating_request=request,
        department=department,
    )

    if cleared and department in (
        NoDuesClearance.Department.HOSTEL,
        NoDuesClearance.Department.MESS,
    ):
        unpaid_invoices = Invoice.objects.filter(
            resident=request.resident,
            status__in=[
                Invoice.Status.UNPAID,
                Invoice.Status.OVERDUE,
            ],
        )

        if department == NoDuesClearance.Department.HOSTEL:
            unpaid_invoices = unpaid_invoices.filter(
                kind=Invoice.Kind.ALLOCATION,
                allocation=request.allocation,
            )
        else:
            unpaid_invoices = unpaid_invoices.filter(
                kind=Invoice.Kind.MESS,
            )

        if unpaid_invoices.exists():
            raise ValidationError(
                f"{clearance.get_department_display()} clearance cannot be "
                "marked cleared while related invoices remain unpaid or overdue."
            )

    clearance.status = NoDuesClearance.Status.CLEARED if cleared else NoDuesClearance.Status.PENDING
    clearance.cleared_by = actor if cleared else None
    clearance.cleared_at = timezone.now() if cleared else None
    clearance.notes = (notes or "").strip()
    clearance.save(
        update_fields=[
            "status",
            "cleared_by",
            "cleared_at",
            "notes",
        ]
    )

    audit.record(
        "vacating.clearance_updated",
        target=request,
        actor=actor,
        detail={
            "department": department,
            "cleared": cleared,
        },
    )

    return clearance


@transaction.atomic
def add_damage_charge(vacating_request, actor, description, amount):
    """Record a damage deduction assessed by staff."""
    request = VacatingRequest.objects.select_for_update().get(pk=vacating_request.pk)

    if request.status != VacatingRequest.Status.REQUESTED:
        raise ValidationError("Damage charges can only be changed before approval.")

    description = (description or "").strip()

    try:
        amount = Decimal(str(amount))
    except (TypeError, ValueError, ArithmeticError):
        raise ValidationError("Enter a valid damage charge amount.")

    if not amount.is_finite():
        raise ValidationError("Damage charge must be a finite amount.")

    if not description:
        raise ValidationError("Enter a description for the damage charge.")

    if amount < 0:
        raise ValidationError("Damage charges cannot be negative.")

    charge = DamageCharge.objects.create(
        vacating_request=request,
        assessed_by=actor,
        description=description,
        amount=amount,
    )

    audit.record(
        "vacating.damage_assessed",
        target=request,
        actor=actor,
        detail={
            "description": description,
            "amount": str(amount),
        },
    )

    return charge


def _outstanding_dues(resident):
    """Return the total balance of unpaid and overdue invoices."""
    return sum(
        Invoice.objects.filter(
            resident=resident,
            status__in=[
                Invoice.Status.UNPAID,
                Invoice.Status.OVERDUE,
            ],
        ).values_list("total", flat=True),
        Decimal("0.00"),
    )


def _paid_refundable_deposit(resident, allocation):
    """Sum refundable items on paid invoices for this allocation."""
    invoices = Invoice.objects.filter(
        resident=resident,
        allocation=allocation,
        status=Invoice.Status.PAID,
    )

    return sum(
        (invoice.refundable_total for invoice in invoices),
        Decimal("0.00"),
    )


@transaction.atomic
def approve_vacating_request(vacating_request, actor):
    """Approve a request after verifying clearances and outstanding dues."""
    request = (
        VacatingRequest.objects.select_for_update()
        .select_related(
            "allocation",
            "resident",
        )
        .get(pk=vacating_request.pk)
    )

    if request.status != VacatingRequest.Status.REQUESTED:
        raise ValidationError("Only a requested vacating request can be approved.")

    allocation = Allocation.objects.select_for_update().get(pk=request.allocation_id)

    if allocation.status != Allocation.Status.ACTIVE:
        raise ValidationError("The allocation is no longer active.")

    pending = request.clearances.exclude(status=NoDuesClearance.Status.CLEARED)

    if pending.exists():
        names = ", ".join(pending.values_list("department", flat=True))
        raise ValidationError(f"Cannot approve vacating. Pending clearances: {names}.")

    outstanding = _outstanding_dues(request.resident)

    if outstanding > 0:
        raise ValidationError(
            f"Cannot approve vacating: outstanding invoices total "
            f"{outstanding:.2f}. Settle them before approval."
        )

    request.status = VacatingRequest.Status.APPROVED
    request.approved_by = actor
    request.approved_at = timezone.now()
    request.save(
        update_fields=[
            "status",
            "approved_by",
            "approved_at",
        ]
    )

    audit.record(
        "vacating.approved",
        target=request,
        actor=actor,
        detail={"allocation_id": request.allocation_id},
    )

    return request


@transaction.atomic
def complete_vacating(vacating_request, actor, staff_notes=""):
    """Complete an approved request, calculate its refund, and release the bed."""
    request = (
        VacatingRequest.objects.select_for_update()
        .select_related(
            "allocation",
            "allocation__bed",
            "resident",
        )
        .get(pk=vacating_request.pk)
    )

    if request.status != VacatingRequest.Status.APPROVED:
        raise ValidationError("The vacating request must be approved before completion.")

    allocation = Allocation.objects.select_for_update().get(pk=request.allocation_id)

    if allocation.status != Allocation.Status.ACTIVE:
        raise ValidationError("The allocation is no longer active.")

    pending = request.clearances.exclude(status=NoDuesClearance.Status.CLEARED)

    if pending.exists():
        names = ", ".join(pending.values_list("department", flat=True))
        raise ValidationError(f"Vacating cannot be completed. Pending clearances: {names}.")

    outstanding = _outstanding_dues(request.resident)

    if outstanding > 0:
        raise ValidationError(
            f"Vacating cannot be completed: outstanding invoices total "
            f"{outstanding:.2f}. Settle them before completing vacating."
        )

    deposit = _paid_refundable_deposit(
        request.resident,
        allocation,
    )

    damage = sum(
        request.damage_charges.values_list("amount", flat=True),
        Decimal("0.00"),
    )

    refund = max(
        Decimal("0.00"),
        deposit - outstanding - damage,
    )

    now = timezone.now()

    request.security_deposit = deposit
    request.outstanding_dues = outstanding
    request.damage_deduction = damage
    request.refund_amount = refund
    request.status = VacatingRequest.Status.COMPLETED
    request.vacated_at = now
    request.staff_notes = (staff_notes or "").strip()

    request.save(
        update_fields=[
            "security_deposit",
            "outstanding_dues",
            "damage_deduction",
            "refund_amount",
            "status",
            "vacated_at",
            "staff_notes",
        ]
    )

    allocation.status = Allocation.Status.ENDED
    allocation.ended_at = now
    allocation.save(update_fields=["status", "ended_at"])

    bed = allocation.bed
    bed.status = Bed.Status.VACANT
    bed.save(update_fields=["status"])

    audit.record(
        "vacating.completed",
        target=request,
        actor=actor,
        detail={
            "refund_amount": str(refund),
            "damage_deduction": str(damage),
        },
    )

    return request
