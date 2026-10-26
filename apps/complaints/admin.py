
from django.contrib import admin

from .models import Complaint


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "status",
        "created_by",
        "created_at",
        "resolved_at",
    )
    list_filter = ("category", "status", "created_at")
    search_fields = ("title", "description", "created_by__username")
    readonly_fields = ("created_at",)
