from django.contrib import admin

from .models import Complaint


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "priority",
        "status",
        "sla_overdue",
        "created_by",
        "assigned_to",
        "created_at",
    )

    list_filter = (
        "status",
        "priority",
        "category",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
        "created_by__username",
        "assigned_to__username",
    )

    # The administrator can reassign or change the state; what was reported stays as reported.
    readonly_fields = (
        "title",
        "description",
        "category",
        "photo",
        "created_by",
        "priority",
        "created_at",
        "resolved_at",
        "resolution_confirmed",
        "escalated_at",
    )

    @admin.display(boolean=True, description="Past SLA")
    def sla_overdue(self, obj):
        return obj.is_sla_overdue

    def has_add_permission(self, request):
        # Residents report complaints from the portal.
        return False
