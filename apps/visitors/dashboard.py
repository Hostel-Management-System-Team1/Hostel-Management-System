from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from hms.dashboard import empty, provider, table_panel

from .models import Visitor

R = User.Role


@provider
def panels(user):
    if user.role != R.SECURITY_GUARD:
        return []
    inside = Visitor.objects.filter(status=Visitor.Status.INSIDE).select_related("resident")
    url = reverse("visitors:list")
    return [table_panel(
        "Visitors inside", ["Visitor", "Visiting", "Since"],
        [(url, [v.visitor_name, v.resident.get_full_name() or v.resident.username,
                timezone.localtime(v.entry_time).strftime("%H:%M")]) for v in inside[:6]],
        link=("Visitors", url),
        empty=empty("bi-person-badge", "No visitors inside",
                    "Visitors you let in appear here until you record their exit."),
    )]
