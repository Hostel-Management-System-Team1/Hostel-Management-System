from django.contrib import admin

from .models import VisitingHours, Visitor


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = (
        "visitor_name",
        "phone",
        "resident",
        "status",
        "entry_time",
        "exit_time",
    )
    list_filter = ("status", "created_at")
    search_fields = ("visitor_name", "phone", "resident__username")
    readonly_fields = ("created_at", "updated_at")


@admin.register(VisitingHours)
class VisitingHoursAdmin(admin.ModelAdmin):
    list_display = ("start_time", "end_time", "is_active", "updated_at")
