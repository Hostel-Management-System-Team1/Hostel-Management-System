
"""Mess Service — HMS-F-030, HMS-F-031 (issue #10)."""

from django.conf import settings
from django.db import models


class MessActivity(models.Model):
    """A recorded meal service for management activity reports."""

    class MealType(models.TextChoices):
        BREAKFAST = "BREAKFAST", "Breakfast"
        LUNCH = "LUNCH", "Lunch"
        SNACKS = "SNACKS", "Snacks"
        DINNER = "DINNER", "Dinner"

    activity_date = models.DateField()
    meal_type = models.CharField(
        max_length=12,
        choices=MealType.choices,
    )
    meals_served = models.PositiveIntegerField(default=0)
    notes = models.CharField(max_length=300, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_mess_activities",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-activity_date", "meal_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["activity_date", "meal_type"],
                name="unique_mess_activity_per_meal_date",
            )
        ]

    def __str__(self):
        return (
            f"{self.get_meal_type_display()} on "
            f"{self.activity_date}: {self.meals_served} meals"
        )


class MessMenuItem(models.Model):
    """A meal entry in the weekly mess menu."""

    class MealType(models.TextChoices):
        BREAKFAST = "BREAKFAST", "Breakfast"
        LUNCH = "LUNCH", "Lunch"
        SNACKS = "SNACKS", "Snacks"
        DINNER = "DINNER", "Dinner"

    menu_date = models.DateField()

    # Exact scheduled date and time of the meal.
    # Nullable temporarily to preserve existing menu records.
    meal_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Exact date and time when this meal will be served.",
    )

    meal_type = models.CharField(
        max_length=12,
        choices=MealType.choices,
    )
    description = models.CharField(max_length=500)
    is_published = models.BooleanField(default=False)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="published_mess_menus",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["menu_date", "meal_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["menu_date", "meal_type"],
                name="unique_mess_menu_per_meal_date",
            )
        ]

    def __str__(self):
        return f"{self.menu_date} - {self.meal_type}"


class MealOptOut(models.Model):
    """A resident's request to skip a scheduled meal."""

    resident = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mess_opt_outs",
    )
    menu_item = models.ForeignKey(
        MessMenuItem,
        on_delete=models.CASCADE,
        related_name="opt_outs",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["resident", "menu_item"],
                name="unique_resident_meal_opt_out",
            )
        ]

    def __str__(self):
        return f"{self.resident} opted out of {self.menu_item}"
