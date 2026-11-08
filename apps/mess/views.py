"""Mess screens (HMS-F-030, F-031): the manager's week planner and the resident's meals."""

import calendar
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import role_required
from apps.admissions.models import Allocation
from apps.audit import service as audit
from apps.fees.services import MESS_MEAL_PRICE as MEAL_PRICE
from apps.fees.services import generate_mess_invoice

from .forms import MealForm
from .models import MealOptOut, MessActivity, MessMenuItem
from .services import (
    DEFAULT_TIMES,
    housed_resident_count,
    month_so_far,
    publish_menu,
    week_grid,
    week_offset,
    week_start,
)

R = User.Role


def _week_url(offset):
    return f"{reverse('mess:home')}?week={offset}" if offset else reverse("mess:home")


def _back(request):
    """Return to the week the form was sent from."""
    week = request.POST.get("week", "")
    return redirect(_week_url(int(week)) if week.lstrip("-").isdigit() else "mess:home")


@login_required
def mess_home(request):
    if request.user.role == R.MESS_MANAGER:
        if request.method == "POST" and request.POST.get("action") == "generate_bills":
            _generate_bills(request)
            return redirect("mess:home")
        return _manager_week(request)
    if request.user.role == R.RESIDENT:
        if request.method == "POST":
            _resident_choice(request)
            return _back(request)
        return _resident_week(request)
    return HttpResponseForbidden("You cannot access the Mess module.")


# ---------------------------------------------------------------- mess manager


def _manager_week(request, form=None):
    offset = week_offset(request, -8, 8)
    monday = week_start(offset)
    items = list(
        MessMenuItem.objects.filter(
            menu_date__range=(monday, monday + timedelta(days=6))
        ).prefetch_related("opt_outs__resident")
    )
    served = {
        (a.activity_date, a.meal_type): a.meals_served
        for a in MessActivity.objects.filter(activity_date__range=(monday, monday + timedelta(6)))
    }
    housed = housed_resident_count()
    now = timezone.now()
    for item in items:
        item.skipping = [o.resident for o in item.opt_outs.all()]
        item.eating = max(housed - len(item.skipping), 0)
        item.is_past = bool(item.meal_datetime and item.meal_datetime <= now)
        item.served = served.get((item.menu_date, item.meal_type))
    meal_types, days = week_grid(monday, items)

    if form is None:
        form = _prefilled_form(request)
    last_month = timezone.localdate().replace(day=1) - timedelta(days=1)
    return render(
        request,
        "mess/manager_menu.html",
        {
            "form": form,
            "editing": request.GET.get("edit"),
            "meal_types": meal_types,
            "days": days,
            "today": timezone.localdate(),
            "now": now,
            "offset": offset,
            "monday": monday,
            "sunday": monday + timedelta(days=6),
            "housed": housed,
            "planned": len(items),
            "skips": sum(len(item.skipping) for item in items),
            "months": list(enumerate(calendar.month_name))[1:],
            "bill_month": last_month.month,
            "bill_year": last_month.year,
            "meal_price": MEAL_PRICE,
        },
    )


def _prefilled_form(request):
    """The meal form, filled for "+ Add" on an empty slot or "Edit" on a meal."""
    if request.GET.get("edit"):
        item = MessMenuItem.objects.filter(pk=request.GET["edit"]).first()
        if item and item.meal_datetime:
            local = timezone.localtime(item.meal_datetime)
            return MealForm(
                initial={
                    "menu_date": item.menu_date,
                    "meal_type": item.meal_type,
                    "time": local.time(),
                    "description": item.description,
                }
            )
    meal_type = request.GET.get("meal", "LUNCH")
    return MealForm(
        initial={
            "menu_date": request.GET.get("date") or timezone.localdate() + timedelta(days=1),
            "meal_type": meal_type,
            "time": DEFAULT_TIMES.get(meal_type, DEFAULT_TIMES["LUNCH"]),
        }
    )


@role_required(R.MESS_MANAGER)
@require_POST
def meal_save(request):
    """Publish a meal, or change the one already planned for that day and meal."""
    form = MealForm(request.POST)
    if not form.is_valid():
        return _manager_week(request, form=form)
    data = form.cleaned_data
    item = MessMenuItem.objects.filter(
        menu_date=data["menu_date"], meal_type=data["meal_type"]
    ).first()
    changed = item is not None
    if changed and item.meal_datetime and item.meal_datetime <= timezone.now():
        messages.error(request, "That meal has already been served and cannot be changed.")
        return redirect("mess:home")
    item = item or MessMenuItem(menu_date=data["menu_date"], meal_type=data["meal_type"])
    item.meal_datetime = data["meal_datetime"]
    item.description = data["description"]
    publish_menu(item, request.user)
    audit.record(
        "mess.menu_changed" if changed else "mess.menu_published",
        target=item,
        detail={"date": str(item.menu_date), "meal": item.meal_type},
    )
    messages.success(
        request,
        f"{item.get_meal_type_display()} on {item.menu_date:%a %d %b} "
        f"{'updated' if changed else 'published'}.",
    )
    offset = (item.menu_date - week_start(0)).days // 7
    return redirect(_week_url(offset))


@role_required(R.MESS_MANAGER)
@require_POST
def meal_delete(request, pk):
    item = get_object_or_404(MessMenuItem, pk=pk)
    if item.meal_datetime and item.meal_datetime <= timezone.now():
        messages.error(request, "A meal that has been served stays on the record.")
    else:
        label = f"{item.get_meal_type_display()} on {item.menu_date:%a %d %b}"
        audit.record("mess.menu_removed", target=item, detail={"date": str(item.menu_date)})
        item.delete()
        messages.success(request, f"{label} removed; residents who skipped it are not affected.")
    return _back(request)


@role_required(R.MESS_MANAGER)
@require_POST
def copy_week(request):
    """Copy the shown week's menu to the following week, filling only empty slots."""
    try:
        offset = int(request.POST.get("week", 0))
    except ValueError:
        offset = 0
    monday = week_start(offset)
    copied = 0
    for item in MessMenuItem.objects.filter(menu_date__range=(monday, monday + timedelta(6))):
        target = item.menu_date + timedelta(weeks=1)
        when = item.meal_datetime + timedelta(weeks=1) if item.meal_datetime else None
        if when is None or when <= timezone.now():
            continue
        _, created = MessMenuItem.objects.get_or_create(
            menu_date=target,
            meal_type=item.meal_type,
            defaults={
                "meal_datetime": when,
                "description": item.description,
                "is_published": True,
                "published_by": request.user,
            },
        )
        copied += created
    messages.success(
        request,
        f"Copied {copied} meal{'s' if copied != 1 else ''} to the "
        f"week of {monday + timedelta(weeks=1):%d %b}.",
    )
    return redirect(_week_url(offset + 1))


@role_required(R.MESS_MANAGER)
@require_POST
def record_served(request, pk):
    """Record how many meals were actually served; the Reports page counts these."""
    item = get_object_or_404(MessMenuItem, pk=pk)
    try:
        count = int(request.POST.get("served", ""))
        if count < 0:
            raise ValueError
    except ValueError:
        messages.error(request, "Enter the number of meals served.")
        return _back(request)
    MessActivity.objects.update_or_create(
        activity_date=item.menu_date,
        meal_type=item.meal_type,
        defaults={"meals_served": count, "recorded_by": request.user},
    )
    messages.success(
        request,
        f"Recorded {count} served for {item.get_meal_type_display().lower()} "
        f"on {item.menu_date:%a %d %b}.",
    )
    return _back(request)


def _generate_bills(request):
    try:
        year = int(request.POST.get("year"))
        month = int(request.POST.get("month"))
        if not (1 <= month <= 12 and 2020 <= year <= 2100):
            raise ValueError
    except (ValueError, TypeError):
        messages.error(request, "Please enter a valid month and year.")
        return
    today = timezone.localdate()
    if (year, month) >= (today.year, today.month):
        messages.error(request, "A month can be billed only after it has ended.")
        return
    # Residents who held a bed during that month.
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    residents = User.objects.filter(
        Q(allocations__ended_at__isnull=True) | Q(allocations__ended_at__date__gte=first_day),
        role=R.RESIDENT,
        allocations__allocated_at__date__lte=last_day,
    ).distinct()
    billed = sum(1 for resident in residents if generate_mess_invoice(resident, year, month))
    messages.success(
        request, f"Mess bills for {calendar.month_name[month]} {year}: {billed} resident(s) billed."
    )


# ---------------------------------------------------------------- resident


def _resident_week(request):
    offset = week_offset(request, 0, 1)
    monday = week_start(offset)
    items = MessMenuItem.objects.filter(
        is_published=True, menu_date__range=(monday, monday + timedelta(days=6))
    )
    skipped = set(
        MealOptOut.objects.filter(resident=request.user, menu_item__in=items).values_list(
            "menu_item_id", flat=True
        )
    )
    cutoff = timezone.now() + timedelta(hours=24)
    meal_types, days = week_grid(monday, items)
    rows = []
    for day, cells in days:
        open_ids = [i.pk for _, _, i in cells if i and i.meal_datetime and i.meal_datetime > cutoff]
        rows.append(
            {
                "day": day,
                "cells": cells,
                "can_skip_day": any(pk not in skipped for pk in open_ids),
                "can_undo_day": any(pk in skipped for pk in open_ids),
            }
        )
    return render(
        request,
        "mess/resident_menu.html",
        {
            "meal_types": meal_types,
            "rows": rows,
            "skipped": skipped,
            "cutoff": cutoff,
            "today": timezone.localdate(),
            "offset": offset,
            "monday": monday,
            "sunday": monday + timedelta(days=6),
            "housed": Allocation.objects.filter(
                resident=request.user, status=Allocation.Status.ACTIVE
            ).exists(),
            "month": month_so_far(request.user),
            "meal_price": MEAL_PRICE,
        },
    )


def _resident_choice(request):
    """Skip or un-skip one meal, or every meal of a day, until 24 hours before each."""
    if not Allocation.objects.filter(
        resident=request.user, status=Allocation.Status.ACTIVE
    ).exists():
        messages.error(request, "You can skip meals once you have a bed in the hostel.")
        return
    action = request.POST.get("action", "skip")
    cutoff = timezone.now() + timedelta(hours=24)
    published = MessMenuItem.objects.filter(is_published=True)
    if action in ("skip_day", "undo_day"):
        try:
            day = date.fromisoformat(request.POST.get("day", ""))
        except ValueError:
            messages.error(request, "Invalid day.")
            return
        meals = list(published.filter(menu_date=day, meal_datetime__gt=cutoff))
        undo = action == "undo_day"
    else:
        meals = list(published.filter(pk=request.POST.get("menu_item_id") or 0))
        undo = action == "undo"
        if not meals:
            messages.error(request, "Invalid meal selection.")
            return
        if meals[0].meal_datetime is None or meals[0].meal_datetime <= cutoff:
            messages.error(
                request,
                "Meals can be skipped or un-skipped only until 24 hours before they are served.",
            )
            return
    with transaction.atomic():
        for meal in meals:
            if undo:
                MealOptOut.objects.filter(resident=request.user, menu_item=meal).delete()
            else:
                MealOptOut.objects.get_or_create(resident=request.user, menu_item=meal)
    if not meals:
        messages.info(request, "No meals that day can still be changed.")
    elif len(meals) == 1:
        meal = meals[0]
        messages.success(
            request,
            f"{'Eating' if undo else 'Skipping'} "
            f"{meal.get_meal_type_display().lower()} on "
            f"{meal.menu_date:%a %d %b}.",
        )
    else:
        messages.success(
            request,
            f"{'Eating' if undo else 'Skipping'} {len(meals)} meals on "
            f"{meals[0].menu_date:%a %d %b}.",
        )
