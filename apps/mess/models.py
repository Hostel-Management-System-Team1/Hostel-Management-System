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
