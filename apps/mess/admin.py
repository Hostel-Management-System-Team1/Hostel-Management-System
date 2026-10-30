
from django.contrib import admin

from .models import MealOptOut, MessActivity, MessMenuItem


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


@admin.register(MessMenuItem)
class MessMenuItemAdmin(admin.ModelAdmin):
    list_display = (
        "menu_date",
        "meal_type",
        "description",
        "is_published",
        "published_by",
    )
    list_filter = ("menu_date", "meal_type", "is_published")
    search_fields = ("description", "published_by__username")
    readonly_fields = ("created_at",)
    date_hierarchy = "menu_date"


@admin.register(MealOptOut)
class MealOptOutAdmin(admin.ModelAdmin):
    list_display = (
        "resident",
        "menu_item",
        "requested_at",
        "reason",
    )
    list_filter = ("requested_at", "menu_item__meal_type")
    search_fields = (
        "resident__username",
        "menu_item__description",
        "reason",
    )
    readonly_fields = ("requested_at",)
