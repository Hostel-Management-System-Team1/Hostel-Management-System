
from django.contrib import admin

from .models import MessActivity


@admin.register(MessActivity)
class MessActivityAdmin(admin.ModelAdmin):
    list_display = (
        "activity_date",
        "meal_type",
        "meals_served",
        "recorded_by",
    )
    list_filter = ("activity_date", "meal_type")
    search_fields = ("notes", "recorded_by__username")
    readonly_fields = ("created_at",)
