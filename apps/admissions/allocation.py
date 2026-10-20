"""Bed allocation (HMS-F-002): automatic in ranked order, or the warden's own choice."""

from django.db import transaction
from django.utils import timezone

from .models import Allocation, AllocationPolicy, Application, Bed, Room
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
