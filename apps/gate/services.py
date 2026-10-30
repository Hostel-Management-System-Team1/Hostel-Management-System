
"""Gate movement recording and processing (HMS-F-020)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.admissions.models import Allocation
from apps.audit import service as audit

from .models import GateMovement


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


import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.admissions.models import Allocation

from .models import CurfewAlert, CurfewConfiguration, GateMovement

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
    every minute to meet the five-minute notification requirement.
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
