from django.urls import reverse

from apps.accounts.models import User
from hms.dashboard import empty, provider, table_panel

from .models import Complaint

R = User.Role
OPEN = [Complaint.Status.OPEN, Complaint.Status.IN_PROGRESS]


def _rows(complaints, url, who):
    return [
        (
            url,
            [
                c.title,
                (c.get_priority_display(), c.priority.lower()),
                who(c),
                (c.get_status_display(), c.status.lower()),
            ],
        )
        for c in complaints
    ]


@provider
def panels(user):
    if user.role == R.RESIDENT:
        mine = Complaint.objects.filter(created_by=user).exclude(status=Complaint.Status.CLOSED)
        if not mine.exists():
            return []
        url = reverse("complaints:my_complaints")
        return [
            table_panel(
                "Your complaints",
                ["Complaint", "Priority", "Assigned to", "Status"],
                _rows(
                    mine.select_related("assigned_to").order_by("-created_at")[:5],
                    url,
                    lambda c: c.assigned_to.get_full_name() if c.assigned_to else "Not yet",
                ),
                link=("View all", url),
                empty={},
            )
        ]

    if user.role == R.WARDEN:
        complaints = Complaint.objects.filter(status__in=OPEN).select_related(
            "created_by", "assigned_to"
        )
        url = reverse("complaints:manage_complaints")
        overdue = [c for c in complaints if c.is_sla_overdue]
        return [
            table_panel(
                "Open complaints",
                ["Complaint", "Priority", "Reported by", "Status"],
                _rows(
                    complaints.order_by("created_at")[:5],
                    url,
                    lambda c: c.created_by.get_full_name() or c.created_by.username,
                ),
                link=(f"All {complaints.count()}", url),
                empty=empty(
                    "bi-tools",
                    "No open complaints",
                    "Complaints residents report appear here, oldest first.",
                ),
                alert=bool(overdue),
            )
        ]
    return []
