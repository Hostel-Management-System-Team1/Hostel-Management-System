"""Business rules for admission, shared by the portal views and the REST API."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import service as audit

from . import erp
from .models import Application


class DuplicateApplication(Exception):
    """A second application for the same enrolment number in the same session (HMS-F-001)."""


class DecisionError(Exception):
    """The application cannot be decided (already decided, or a rejection without a reason)."""


def submit_application(applicant, **fields):
    """Validate and store an application, returning it with its number issued.

    An application number is issued only when every mandatory field passes validation.
    Raises ValidationError for bad data and DuplicateApplication for a repeat application.
    """
    session = settings.ACADEMIC_SESSION
    application = Application(applicant=applicant, academic_session=session, **fields)
    application.enrolment_number = (application.enrolment_number or "").replace(" ", "").upper()

    existing = Application.objects.filter(
        academic_session=session, enrolment_number=application.enrolment_number
    ).first() or Application.objects.filter(applicant=applicant, academic_session=session).first()
    if existing:
        raise DuplicateApplication(
            f"An application for enrolment number {existing.enrolment_number} already exists for "
            f"{session} (application {existing.application_number}). Only one application per "
            "student per session is accepted."
        )

    # Field validators and the gender/block rule; the unique constraints are checked above.
    application.full_clean(validate_unique=False)
    if erp.lookup(application.enrolment_number) is None:
        raise ValidationError(
            {"enrolment_number": "This enrolment number was not found in the student records."}
        )
    try:
        with transaction.atomic():
            application.save()
    except IntegrityError as error:  # two submissions racing past the check above
        raise DuplicateApplication(
            "An application for this student already exists for this session."
        ) from error
    return application


@transaction.atomic
def decide(application, actor, approve, note=""):
    """Approve or reject a submitted application. A rejection needs a reason."""
    application = Application.objects.select_for_update().get(pk=application.pk)
    if application.status != Application.Status.SUBMITTED:
        status = application.get_status_display().lower()
        raise DecisionError(f"This application was already {status}.")
    note = (note or "").strip()
    if not approve and not note:
        raise DecisionError("Give a reason when rejecting an application.")
    application.status = Application.Status.APPROVED if approve else Application.Status.REJECTED
    application.decided_by = actor
    application.decided_at = timezone.now()
    application.decision_note = note
    application.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
    audit.record(
        "application.approved" if approve else "application.rejected",
        target=application, actor=actor, detail={"application": application.application_number},
    )
    return application
