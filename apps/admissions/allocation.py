"""Bed allocation (HMS-F-002): automatic in ranked order, or the warden's own choice."""

from django.db import transaction
from django.utils import timezone

from .models import Allocation, AllocationPolicy, Application, Bed, Room, Transfer
from .signals import allocation_confirmed


class AllocationError(Exception):
    """The application cannot be allocated a bed (wrong state, or the chosen bed is unsuitable)."""


class NoVacantBed(AllocationError):
    """No vacant bed matches the applicant's gender, block and room type (HTTP 409 in the API)."""


def vacant_beds(gender):
    """Every vacant, in-service bed in a block for this gender."""
    return Bed.objects.filter(
        status=Bed.Status.VACANT,
        room__status=Room.Status.AVAILABLE,
        room__block__gender=gender,
    ).select_related("room__block")


def candidate_beds(application):
    """Beds that match the applicant's gender, room type and, if given, preferred block."""
    beds = vacant_beds(application.gender).filter(room__room_type=application.room_type)
    if application.preferred_block_id:
        beds = beds.filter(room__block_id=application.preferred_block_id)
    return beds.order_by("room__block__name", "room__floor", "room__number", "label")


def ranked_waiting_applications():
    """Approved applications still without a bed, best-ranked first under the current policy."""
    waiting = Application.objects.filter(status=Application.Status.APPROVED)
    ranking = AllocationPolicy.current().ranking
    if ranking == AllocationPolicy.Ranking.MERIT:
        order = ["-cgpa", "submitted_at"]
    elif ranking == AllocationPolicy.Ranking.SENIORITY:
        order = ["-year_of_study", "-cgpa", "submitted_at"]
    else:
        order = ["submitted_at"]
    return waiting.order_by(*order, "pk").select_related("preferred_block")


@transaction.atomic
def allocate(application, actor, bed=None):
    """Give an approved application a bed and confirm the allocation.

    Without ``bed`` the first matching vacant bed is used. With ``bed`` the warden's own choice
    is used, which must still be vacant and in a block for the applicant's gender.
    """
    application = Application.objects.select_for_update().get(pk=application.pk)
    if application.status != Application.Status.APPROVED:
        raise AllocationError("Only an approved application without a bed can be allocated.")
    if bed is None:
        chosen = candidate_beds(application).select_for_update(of=("self",)).first()
        if chosen is None:
            raise NoVacantBed(
                "No vacant bed matches this applicant's gender, block and room type."
            )
    else:
        chosen = vacant_beds(application.gender).select_for_update(of=("self",)).filter(
            pk=bed.pk).first()
        if chosen is None:
            raise AllocationError("That bed is not vacant or is not in a block for this gender.")

    allocation = Allocation.objects.create(
        application=application, resident=application.applicant, bed=chosen, allocated_by=actor
    )
    chosen.status = Bed.Status.OCCUPIED
    chosen.save(update_fields=["status"])
    application.status = Application.Status.ALLOCATED
    application.save(update_fields=["status"])
    allocation_confirmed.send(sender=Allocation, allocation=allocation)
    return allocation


def allocate_all(actor):
    """Allocate every waiting approved application in ranked order.

    Returns (allocations, skipped) where skipped holds (application, reason) pairs for the
    applications no bed could be found for.
    """
    allocations, skipped = [], []
    for application in ranked_waiting_applications():
        try:
            allocations.append(allocate(application, actor))
        except AllocationError as error:
            skipped.append((application, str(error)))
    return allocations, skipped


def end_allocation(allocation):
    """Release the bed of an allocation (used when a resident vacates)."""
    with transaction.atomic():
        allocation.status = Allocation.Status.ENDED
        allocation.ended_at = timezone.now()
        allocation.save(update_fields=["status", "ended_at"])
        allocation.bed.status = Bed.Status.VACANT
        allocation.bed.save(update_fields=["status"])


class TransferError(Exception):
    """The transfer cannot be made (no reason, bed unsuitable, or the resident has no bed)."""


@transaction.atomic
def transfer(allocation, to_bed, reason, actor):
    """Move a resident to another bed (HMS-F-003).

    The source bed becomes vacant, the target bed occupied and the transfer is recorded with
    its reason, actor and time, all in one database transaction: if any step fails, none of
    them happen.
    """
    reason = (reason or "").strip()
    if not reason:
        raise TransferError("Give a reason for the transfer.")
    allocation = Allocation.objects.select_for_update().select_related(
        "application", "bed").get(pk=allocation.pk)
    if allocation.status != Allocation.Status.ACTIVE:
        raise TransferError("This resident no longer has a bed.")
    # Lock both beds in a fixed order so two simultaneous transfers cannot deadlock.
    ids = sorted({allocation.bed_id, to_bed.pk})
    beds = {b.pk: b for b in Bed.objects.select_for_update().filter(pk__in=ids)}
    source, target = beds[allocation.bed_id], beds.get(to_bed.pk)
    if target is None or target.pk == source.pk:
        raise TransferError("Choose a different bed.")
    suitable = vacant_beds(allocation.application.gender).filter(pk=target.pk).exists()
    if not suitable:
        raise TransferError("That bed is not vacant or is not in a block for this gender.")

    source.status = Bed.Status.VACANT
    source.save(update_fields=["status"])
    target.status = Bed.Status.OCCUPIED
    target.save(update_fields=["status"])
    allocation.bed = target
    allocation.save(update_fields=["bed"])
    return Transfer.objects.create(
        allocation=allocation, from_bed=source, to_bed=target, reason=reason, performed_by=actor
    )
