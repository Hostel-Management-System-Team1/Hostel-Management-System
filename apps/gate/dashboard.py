from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from hms.dashboard import empty, facts_panel, provider, table_panel

from .models import CurfewAlert, GateMovement, OutpassRequest

R = User.Role


def _name(user):
    return user.get_full_name() or user.username


@provider
def panels(user):
    if user.role == R.RESIDENT:
        outpass = OutpassRequest.objects.filter(resident=user, returned_at__isnull=True).exclude(
            status=OutpassRequest.Status.REJECTED).order_by("-requested_at").first()
        if outpass is None:
            return []
        return [facts_panel("Outpass", [
            ("Destination", outpass.destination),
            ("Back by", timezone.localtime(outpass.expected_return_at).strftime("%d %b, %H:%M")),
            ("Status", outpass.get_status_display()),
        ], link=("View", reverse("gate:outpasses")))]

    if user.role == R.WARDEN:
        pending = OutpassRequest.objects.filter(
            status=OutpassRequest.Status.PENDING).select_related("resident")
        rows = [
            (reverse("gate:warden_outpasses"), [
                _name(o.resident), o.destination,
                timezone.localtime(o.expected_return_at).strftime("%d %b, %H:%M"),
            ])
            for o in pending.order_by("requested_at")[:5]
        ]
        panels = [table_panel(
            "Outpasses to decide", ["Resident", "Destination", "Back by"], rows,
            link=(f"All {pending.count()}", reverse("gate:warden_outpasses")),
            empty=empty("bi-box-arrow-up-right", "No outpasses waiting",
                        "Leave requests from residents appear here for your decision."),
        )]
        alerts = CurfewAlert.objects.filter(
            curfew_date__gte=timezone.localdate() - timedelta(days=1)
        ).select_related("resident", "block")
        if alerts:
            panels.append(table_panel(
                "Curfew alerts", ["Resident", "Block", "Night of"],
                [(reverse("gate:log"), [_name(a.resident), a.block.name,
                                        a.curfew_date.strftime("%d %b")]) for a in alerts[:5]],
                link=("Gate log", reverse("gate:log")), empty={}, alert=True,
            ))
        return panels

    if user.role == R.SECURITY_GUARD:
        moves = GateMovement.objects.select_related("resident")[:6]
        rows = [
            (None, [_name(m.resident), (m.get_direction_display(), m.direction.lower()),
                    timezone.localtime(m.occurred_at).strftime("%d %b, %H:%M")])
            for m in moves
        ]
        due = OutpassRequest.objects.filter(
            status=OutpassRequest.Status.APPROVED, returned_at__isnull=True
        ).select_related("resident").order_by("expected_return_at")
        return [
            table_panel(
                "Recent movements", ["Resident", "Movement", "When"], rows,
                link=("Gate log", reverse("gate:log")),
                empty=empty("bi-door-open", "No gate movements yet",
                            "Entries and exits recorded at the gate will appear here."),
            ),
            table_panel(
                "Due back from outpass", ["Resident", "Destination", "Back by"],
                [(reverse("gate:returns"), [
                    _name(o.resident), o.destination,
                    timezone.localtime(o.expected_return_at).strftime("%d %b, %H:%M"),
                ]) for o in due[:5]],
                link=(f"All {due.count()}", reverse("gate:returns")),
                empty=empty("bi-house-check", "Everyone is back",
                            "Residents away on an approved outpass appear here."),
            ),
        ]
    return []
