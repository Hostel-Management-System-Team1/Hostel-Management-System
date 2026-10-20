from django.urls import reverse

from apps.accounts.models import User
from hms.dashboard import empty, facts_panel, provider, table_panel

from .models import Application

R = User.Role

STATUS_BADGE = {"SUBMITTED": "pending", "APPROVED": "paid", "REJECTED": "high"}


@provider
def panels(user):
    if user.role == R.RESIDENT:
        application = Application.objects.filter(applicant=user).first()
        link = ("View", reverse("admissions:my_application"))
        if application is None:
            return [table_panel("Your application", [], [], empty=empty(
                "bi-file-earmark-text", "No application yet",
                "Apply for a hostel room. The warden reviews it and allocates a bed.",
                action=("Apply for a room", reverse("admissions:apply")),
            ))]
        return [facts_panel("Your application", [
            ("Application number", application.application_number),
            ("Submitted", application.submitted_at.strftime("%d %b %Y")),
            ("Status", application.get_status_display()),
        ], link=link)]
    if user.role == R.WARDEN:
        waiting = Application.objects.filter(status=Application.Status.SUBMITTED)
        rows = [
            (
                reverse("admissions:application_detail", args=[a.pk]),
                [a.full_name, a.enrolment_number, a.get_room_type_display(),
                 a.submitted_at.strftime("%d %b")],
            )
            for a in waiting.order_by("submitted_at")[:5]
        ]
        return [table_panel(
            "Pending applications", ["Applicant", "Enrolment", "Room type", "Applied"], rows,
            link=(f"All {waiting.count()}", reverse("admissions:application_list")),
            empty=empty("bi-inbox", "No applications waiting",
                        "New hostel applications will appear here for review and bed allocation."),
        )]
    return []
