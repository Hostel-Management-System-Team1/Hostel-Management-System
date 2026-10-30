
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.fees.services import generate_mess_invoice

from .forms import MessMenuForm
from .models import MealOptOut, MessMenuItem
from .services import publish_menu


@login_required
def mess_home(request):

    # MESS MANAGER
    if request.user.role == User.Role.MESS_MANAGER:

        if request.method == "POST":

            # Generate monthly mess bills
            if request.POST.get("action") == "generate_bills":
                try:
                    year = int(request.POST.get("year"))
                    month = int(request.POST.get("month"))

                    if month < 1 or month > 12:
                        raise ValueError

                    if year < 2020 or year > 2100:
                        raise ValueError

                    residents = User.objects.filter(
                        role=User.Role.RESIDENT
                    )

                    generated_count = 0

                    for resident in residents:
                        generate_mess_invoice(
                            resident,
                            year,
                            month,
                        )
                        generated_count += 1

                    messages.success(
                        request,
                        f"Monthly mess bills processed for "
                        f"{generated_count} residents.",
                    )

                except (ValueError, TypeError):
                    messages.error(
                        request,
                        "Please enter a valid month and year.",
                    )

                return redirect("mess:home")

            # Publish a menu item
            form = MessMenuForm(request.POST)

            if form.is_valid():
                menu_item = form.save(commit=False)

                publish_menu(menu_item, request.user)

                messages.success(
                    request,
                    "Menu published successfully!",
                )

                return redirect("mess:home")

        else:
            form = MessMenuForm()

        menu_items = MessMenuItem.objects.all().prefetch_related(
            "opt_outs__resident"
        )

        return render(
            request,
            "mess/manager_menu.html",
            {
                "form": form,
                "menu_items": menu_items,
            },
        )

    # RESIDENT
    if request.user.role == User.Role.RESIDENT:

        menu_items = MessMenuItem.objects.filter(
            is_published=True,
            menu_date__gte=timezone.localdate(),
        ).order_by("meal_datetime", "menu_date")

        if request.method == "POST":

            menu_item_id = request.POST.get("menu_item_id")

            try:
                with transaction.atomic():

                    menu_item = (
                        menu_items.select_for_update()
                        .get(id=menu_item_id)
                    )

                    # Reject old menu records without a scheduled time.
                    if menu_item.meal_datetime is None:
                        messages.error(
                            request,
                            "The meal schedule is not available. "
                            "Please contact the Mess Manager.",
                        )

                    # Require strictly more than 24 hours' notice.
                    elif menu_item.meal_datetime <= (
                        timezone.now() + timedelta(hours=24)
                    ):
                        messages.error(
                            request,
                            "Meal opt-outs must be submitted "
                            "more than 24 hours before the meal.",
                        )

                    else:
                        _, created = MealOptOut.objects.get_or_create(
                            resident=request.user,
                            menu_item=menu_item,
                        )

                        if created:
                            messages.success(
                                request,
                                "Your meal opt-out request has been recorded.",
                            )
                        else:
                            messages.info(
                                request,
                                "You have already opted out of this meal.",
                            )

            except (
                MessMenuItem.DoesNotExist,
                ValueError,
                TypeError,
            ):
                messages.error(
                    request,
                    "Invalid meal selection.",
                )

            return redirect("mess:home")

        opted_out_ids = MealOptOut.objects.filter(
            resident=request.user,
            menu_item__in=menu_items,
        ).values_list("menu_item_id", flat=True)

        return render(
            request,
            "mess/resident_menu.html",
            {
                "menu_items": menu_items,
                "opted_out_ids": list(opted_out_ids),
            },
        )

    return HttpResponseForbidden(
        "You cannot access the Mess module."
    )
