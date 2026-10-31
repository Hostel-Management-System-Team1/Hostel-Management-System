from django.contrib import admin

from .models import Complaint


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "priority",
        "status",
        "created_by",
        "assigned_to",
        "resolution_confirmed",
        "is_sla_overdue",
        "created_at",
        "resolved_at",
    )

    list_filter = (
        "category",
        "priority",
        "status",
        "resolution_confirmed",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
        "created_by__username",
        "assigned_to__username",
    )

    readonly_fields = (
        "created_at",
        "escalated_at",
    )
