from datetime import time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User


def publish_menu(menu_item, actor):
    """Publish a menu item by an authorized Mess Manager."""

    if actor.role != User.Role.MESS_MANAGER:
        raise PermissionError("Only Mess Managers can publish the menu.")

    with transaction.atomic():
        menu_item.published_by = actor
        menu_item.is_published = True
        menu_item.save()

    return menu_item


def housed_resident_count():
    """Residents with a bed now: the people the mess cooks for."""
    from apps.admissions.models import Allocation

    return Allocation.objects.filter(status=Allocation.Status.ACTIVE).count()


def menu_grid(menu_items):
    """Arrange menu items as a week grid.

    Returns (meal types used, [(date, [(meal label, item or None), ...]), ...]).
    """
    from .models import MessMenuItem

    items = list(menu_items)
    used = {item.meal_type for item in items}
    meal_types = [(value, label) for value, label in MessMenuItem.MealType.choices if value in used]
    by_day = {}
    for item in items:
        by_day.setdefault(item.menu_date, {})[item.meal_type] = item
    days = [
        (day, [(label, by_day[day].get(value)) for value, label in meal_types])
        for day in sorted(by_day)
    ]
    return meal_types, days


# When each meal is usually served; the publish form starts from these.
DEFAULT_TIMES = {"BREAKFAST": time(8, 0), "LUNCH": time(13, 0), "SNACKS": time(17, 0),
                 "DINNER": time(20, 0)}


def week_start(offset=0):
    """Monday of the current week, moved by ``offset`` weeks."""
    today = timezone.localdate()
    return today - timedelta(days=today.weekday()) + timedelta(weeks=offset)


def week_offset(request, low, high):
    try:
        offset = int(request.GET.get("week", 0))
    except ValueError:
        offset = 0
    return max(low, min(high, offset))


def week_grid(monday, items):
    """Every day Monday–Sunday and every regular meal, filled with the items that exist."""
    from .models import MessMenuItem

    by_slot = {(item.menu_date, item.meal_type): item for item in items}
    types = [(v, label) for v, label in MessMenuItem.MealType.choices
             if v != "SNACKS" or any(t == "SNACKS" for _, t in by_slot)]
    days = []
    for n in range(7):
        day = monday + timedelta(days=n)
        days.append((day, [(value, label, by_slot.get((day, value))) for value, label in types]))
    return types, days


def month_so_far(resident):
    """Meals eaten and skipped by a resident this month, up to now, and the bill so far."""
    from apps.fees.services import MESS_MEAL_PRICE

    from .models import MessMenuItem

    now = timezone.now()
    served = MessMenuItem.objects.filter(
        is_published=True, meal_datetime__lte=now,
        menu_date__gte=timezone.localdate().replace(day=1),
    )
    skipped = served.filter(opt_outs__resident=resident).count()
    eaten = served.count() - skipped
    return {"eaten": eaten, "skipped": skipped, "cost": eaten * MESS_MEAL_PRICE}
