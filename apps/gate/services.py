"""Gate movement recording and processing (HMS-F-020)."""

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.admissions.models import Allocation
from apps.audit import service as audit

from .models import (
    CurfewAlert,
    CurfewConfiguration,
    GateMovement,
    NightAttendance,
    OutpassRequest,
)


class InvalidGateMovement(Exception):
    """A gate movement does not satisfy the HMS rules."""


def record_movement(
    resident,
    direction,
    capture_method,
    *,
    occurred_at=None,
    recorded_by=None,
    external_event_id=None,
):
    """Record a resident's entry or exit, preserving the source event time."""

    if direction not in GateMovement.Direction.values:
        raise InvalidGateMovement("Invalid movement direction.")

    if capture_method not in GateMovement.CaptureMethod.values:
        raise InvalidGateMovement("Invalid capture method.")

    if not Allocation.objects.filter(
        resident=resident,
        status=Allocation.Status.ACTIVE,
    ).exists():
        raise InvalidGateMovement("Resident has no active hostel allocation.")

    if capture_method == GateMovement.CaptureMethod.MANUAL:
        if not recorded_by or recorded_by.role != User.Role.SECURITY_GUARD:
            raise InvalidGateMovement(
                "Manual movements must be recorded by a security guard."
            )
    elif recorded_by is not None:
        raise InvalidGateMovement(
            "Device-originated movements cannot specify a recording guard."
        )

    occurred_at = occurred_at or timezone.now()

    try:
        with transaction.atomic():
            movement = GateMovement.objects.create(
                resident=resident,
                direction=direction,
                capture_method=capture_method,
                occurred_at=occurred_at,
                recorded_by=recorded_by,
                external_event_id=external_event_id or None,
            )
    except IntegrityError:
        if external_event_id and GateMovement.objects.filter(
            external_event_id=external_event_id
        ).exists():
            return GateMovement.objects.get(
                external_event_id=external_event_id
            )
        raise

    audit.record(
        "gate.movement_recorded",
        target=movement,
        actor=recorded_by,
        detail={
            "direction": direction,
            "capture_method": capture_method,
        },
    )

    return movement


logger = logging.getLogger(__name__)

CURFEW_GRACE_MINUTES = 30


def _curfew_threshold(configuration, curfew_date):
    """Return the timezone-aware 30-minute curfew threshold."""
    local_curfew = datetime.combine(
        curfew_date,
        configuration.curfew_time,
    )
    aware_curfew = timezone.make_aware(
        local_curfew,
        timezone.get_current_timezone(),
    )
    return aware_curfew + timedelta(minutes=CURFEW_GRACE_MINUTES)


def _resident_was_out_at_threshold(resident, threshold):
    """Check the resident's last recorded movement at or before the threshold."""
    last_movement = GateMovement.objects.filter(
        resident=resident,
        occurred_at__lte=threshold,
    ).order_by("-occurred_at", "-pk").first()

    return (
        last_movement is not None
        and last_movement.direction == GateMovement.Direction.OUT
    )


def _notify_wardens(alert):
    """Email active wardens about an outstanding curfew violation."""
    wardens = User.objects.filter(
        role=User.Role.WARDEN,
        is_active=True,
    ).exclude(email="")

    recipients = list(wardens.values_list("email", flat=True).distinct())

    if not recipients:
        logger.warning(
            "No warden email addresses available for curfew alert %s",
            alert.pk,
        )
        return False

    resident_name = (
        alert.resident.get_full_name()
        or alert.resident.username
    )

    message = EmailMessage(
        subject=f"Hostel curfew violation - {resident_name}",
        body=(
            f"Curfew violation detected.\n\n"
            f"Resident: {resident_name}\n"
            f"Hostel block: {alert.block.name}\n"
            f"Curfew date: {alert.curfew_date}\n"
            f"Detected at: {timezone.localtime(alert.detected_at)}\n\n"
            "Please follow up with the resident."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )

    return message.send(fail_silently=False) == 1


def process_curfew_alerts(now=None):
    """Detect residents still outside after curfew and notify wardens.

    Checks both today's and yesterday's curfew so overnight violations
    are not missed after midnight. The scheduled command should run
    every five minutes to meet the notification requirement.
    """
    now = timezone.localtime(now or timezone.now())
    today = now.date()

    result = {
        "alerts_created": 0,
        "notifications_sent": 0,
        "notifications_failed": 0,
    }

    configurations = CurfewConfiguration.objects.filter(
        is_active=True,
    ).select_related("block")

    for configuration in configurations:
        allocations = Allocation.objects.filter(
            status=Allocation.Status.ACTIVE,
            bed__room__block=configuration.block,
        ).select_related("resident")

        for curfew_date in (today - timedelta(days=1), today):
            threshold = _curfew_threshold(configuration, curfew_date)

            if now < threshold:
                continue

            for allocation in allocations:
                resident = allocation.resident

                if not _resident_was_out_at_threshold(resident, threshold):
                    continue

                alert, created = CurfewAlert.objects.get_or_create(
                    resident=resident,
                    curfew_date=curfew_date,
                    defaults={
                        "block": configuration.block,
                        "detected_at": now,
                    },
                )

                if created:
                    result["alerts_created"] += 1

                if alert.notified_at is not None:
                    continue

                try:
                    if _notify_wardens(alert):
                        alert.notified_at = timezone.now()
                        alert.save(update_fields=["notified_at"])
                        result["notifications_sent"] += 1
                    else:
                        result["notifications_failed"] += 1

                except Exception:
                    logger.exception(
                        "Could not send curfew notification for alert %s",
                        alert.pk,
                    )
                    result["notifications_failed"] += 1

    return result


class OutpassError(Exception):
    """An outpass operation violates the workflow rules."""



def _notify_guardian(outpass, event):
    """Send an outpass approval or return notice to the registered guardian."""
    try:
        application = outpass.allocation.application
        guardian_email = (application.guardian_email or "").strip()

        if not guardian_email:
            logger.warning(
                "No guardian email is registered for outpass %s",
                outpass.pk,
            )
            return False

        resident_name = (
            application.full_name
            or outpass.resident.get_full_name()
            or outpass.resident.username
        )

        if event == "approved":
            subject = f"Outpass approved - {resident_name}"
            body = (
                f"Dear {application.guardian_name},\n\n"
                f"The outpass request for {resident_name} has been approved.\n"
                f"Destination: {outpass.destination}\n"
                f"Expected return: "
                f"{timezone.localtime(outpass.expected_return_at)}\n\n"
                "Regards,\nHostel Management System"
            )
        elif event == "returned":
            subject = f"Resident returned - {resident_name}"
            body = (
                f"Dear {application.guardian_name},\n\n"
                f"{resident_name} has been recorded as returned to the hostel.\n"
                f"Return time: {timezone.localtime(outpass.returned_at)}\n\n"
                "Regards,\nHostel Management System"
            )
        else:
            raise ValueError("Unsupported guardian notification event.")

        message = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[guardian_email],
        )
        return message.send(fail_silently=False) == 1

    except Exception:
        # The approval/return has already been recorded. Do not make
        # the API report failure just because the email service is down.
        logger.exception(
            "Guardian notification failed for outpass %s (%s)",
            outpass.pk,
            event,
        )
        return False



def submit_outpass(
    resident,
    destination,
    contact_number,
    expected_return_at,
):
    """Create a Pending outpass request for a resident with an active allocation."""
    if resident.role != User.Role.RESIDENT:
        raise OutpassError("Only residents can submit outpass requests.")

    if expected_return_at <= timezone.now():
        raise OutpassError("Expected return time must be in the future.")

    allocation = Allocation.objects.filter(
        resident=resident,
        status=Allocation.Status.ACTIVE,
    ).select_related("application").first()

    if allocation is None:
        raise OutpassError("An active hostel allocation is required.")

    return OutpassRequest.objects.create(
        resident=resident,
        allocation=allocation,
        destination=destination.strip(),
        contact_number=contact_number.strip(),
        expected_return_at=expected_return_at,
    )


def decide_outpass(outpass_id, warden, decision, reason=""):
    """Approve or reject a pending outpass and notify its guardian."""
    if warden.role != User.Role.WARDEN:
        raise PermissionDenied("Only wardens can decide outpass requests.")

    if decision not in (
        OutpassRequest.Status.APPROVED,
        OutpassRequest.Status.REJECTED,
    ):
        raise OutpassError("Decision must be Approved or Rejected.")

    with transaction.atomic():
        outpass = OutpassRequest.objects.select_for_update().get(pk=outpass_id)

        if outpass.status != OutpassRequest.Status.PENDING:
            raise OutpassError("This outpass has already been decided.")

        outpass.status = decision
        outpass.decided_by = warden
        outpass.decided_at = timezone.now()
        outpass.decision_reason = reason.strip()
        outpass.save(
            update_fields=[
                "status",
                "decided_by",
                "decided_at",
                "decision_reason",
            ]
        )

    if decision == OutpassRequest.Status.APPROVED:
        _notify_guardian(outpass, "approved")

    audit.record(
        "outpass.decided",
        target=outpass,
        actor=warden,
        detail={
            "decision": decision,
            "reason": reason.strip(),
        },
    )
    return outpass


def record_outpass_return(outpass_id, guard):
    """Record the resident's gate entry and notify the registered guardian."""
    if guard.role not in (User.Role.SECURITY_GUARD, User.Role.WARDEN):
        raise PermissionDenied("Only a guard or warden can record a return.")

    with transaction.atomic():
        outpass = (
            OutpassRequest.objects.select_for_update()
            .select_related("resident", "allocation__application")
            .get(pk=outpass_id)
        )

        if outpass.status != OutpassRequest.Status.APPROVED:
            raise OutpassError("Only an approved outpass can be marked returned.")

        if outpass.returned_at is not None:
            raise OutpassError("This resident's return has already been recorded.")

        movement = record_movement(
            resident=outpass.resident,
            direction=GateMovement.Direction.IN,
            capture_method=GateMovement.CaptureMethod.MANUAL,
            recorded_by=guard,
        )
        outpass.returned_at = movement.occurred_at
        outpass.save(update_fields=["returned_at"])

    _notify_guardian(outpass, "returned")

    audit.record(
        "outpass.returned",
        target=outpass,
        actor=guard,
        detail={"returned_at": outpass.returned_at.isoformat()},
    )
    return outpass


def generate_night_attendance(attendance_date):
    """Generate or refresh room-wise attendance using gate and approved outpass records."""
    configurations = CurfewConfiguration.objects.filter(
        is_active=True,
    ).select_related("block")

    created_count = 0
    updated_count = 0

    for configuration in configurations:
        threshold = _curfew_threshold(configuration, attendance_date)

        allocations = Allocation.objects.filter(
            status=Allocation.Status.ACTIVE,
            bed__room__block=configuration.block,
        ).select_related("resident", "bed__room")

        for allocation in allocations:
            resident = allocation.resident

            latest_movement = (
                GateMovement.objects.filter(
                    resident=resident,
                    occurred_at__lte=threshold,
                )
                .order_by("-occurred_at", "-pk")
                .first()
            )

            approved_leave = OutpassRequest.objects.filter(
                resident=resident,
                status=OutpassRequest.Status.APPROVED,
                requested_at__date__lte=attendance_date,
                expected_return_at__gt=threshold,
                returned_at__isnull=True,
            ).exists()

            if approved_leave:
                attendance_status = NightAttendance.Status.ON_LEAVE
            elif (
                latest_movement
                and latest_movement.direction == GateMovement.Direction.OUT
            ):
                attendance_status = NightAttendance.Status.ABSENT
            else:
                attendance_status = NightAttendance.Status.PRESENT

            _, created = NightAttendance.objects.update_or_create(
                resident=resident,
                attendance_date=attendance_date,
                defaults={
                    "room": allocation.bed.room,
                    "status": attendance_status,
                    "recorded_by": None,
                    "recorded_at": timezone.now(),
                },
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

    return {
        "created": created_count,
        "updated": updated_count,
    }
