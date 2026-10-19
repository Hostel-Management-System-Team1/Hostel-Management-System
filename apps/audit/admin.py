from django.contrib import admin

from . import service
from .models import AuditEntry


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    """The audit log, read-only: nobody can add, edit or delete an entry here (HMS-SR-004)."""

    list_display = ("seq", "timestamp", "who", "action", "what", "outcome")
    list_filter = ("category", "outcome", "action")
    search_fields = ("actor_label", "action", "target_repr", "target_id")
    date_hierarchy = "timestamp"
    ordering = ("-seq",)
    list_per_page = 50
    actions = None

    @admin.display(description="Who", ordering="actor_label")
    def who(self, obj):
        return obj.actor_label

    @admin.display(description="What", ordering="target_repr")
    def what(self, obj):
        return obj.target_repr

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        checked, problems = service.verify_chain()
        context = {"chain_checked": checked, "chain_problems": problems, "title": "Audit log",
                   **(extra_context or {})}
        return super().changelist_view(request, context)
