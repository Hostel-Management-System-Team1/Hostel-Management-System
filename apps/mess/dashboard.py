from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from hms.dashboard import empty, provider, table_panel

from .models import MessMenuItem
from .services import housed_resident_count

R = User.Role


@provider
def panels(user):
    if user.role not in (R.RESIDENT, R.MESS_MANAGER):
        return []
    upcoming = MessMenuItem.objects.filter(
        is_published=True, menu_date__gte=timezone.localdate()
    ).prefetch_related("opt_outs").order_by("menu_date", "meal_datetime")
    url = reverse("mess:home")

    if user.role == R.RESIDENT:
        if not user.allocations.filter(status="ACTIVE").exists():
            return []  # no bed, no mess
        items = list(upcoming[:4])
        if not items:
            return []
        skipped = set(user.mess_opt_outs.filter(menu_item__in=items).values_list(
            "menu_item_id", flat=True))
        return [table_panel(
            "Next meals", ["Meal", "When", "Menu"],
            [(url, [m.get_meal_type_display(), m.menu_date.strftime("%a %d %b"),
                    "Skipping" if m.pk in skipped else m.description]) for m in items],
            link=("Menu", url), empty={},
        )]

    # The manager's home answers "how many do we cook for?"; the menu is on Menu & bills.
    housed = housed_resident_count()
    coming = upcoming.filter(meal_datetime__gte=timezone.now())[:6]
    rows = []
    for m in coming:
        skipping = len(m.opt_outs.all())
        when = timezone.localtime(m.meal_datetime).strftime("%a %d %b, %H:%M")
        rows.append((url, [m.get_meal_type_display(), when, str(max(housed - skipping, 0)),
                           str(skipping)]))
    return [table_panel(
        "Headcount for the next meals", ["Meal", "When", "Eating", "Skipping"], rows,
        link=("Menu & bills", url),
        empty=empty("bi-cup-hot", "No meals coming up",
                    "Publish the week’s menu; residents’ opt-outs then show here as headcounts.",
                    action=("Publish a meal", url)),
    )]
