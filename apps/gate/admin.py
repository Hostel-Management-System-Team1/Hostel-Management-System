from django.contrib import admin

from .models import CurfewAlert, CurfewConfiguration, GateMovement, NightAttendance, OutpassRequest


@admin.register(GateMovement)
class GateMovementAdmin(admin.ModelAdmin):
    """Gate movements are evidence: they can be read and filtered but not edited."""

    list_display = ("occurred_at", "resident", "direction", "capture_method", "recorded_by")
    list_filter = ("occurred_at", "direction", "capture_method")
    search_fields = ("resident__username", "resident__first_name", "resident__last_name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CurfewAlert)
class CurfewAlertAdmin(admin.ModelAdmin):
    list_display = ("curfew_date", "resident", "block", "detected_at", "notified_at")
    list_filter = ("curfew_date", "block")
    search_fields = ("resident__username", "resident__first_name", "resident__last_name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CurfewConfiguration)
class CurfewConfigurationAdmin(admin.ModelAdmin):
    list_display = ("block", "curfew_time", "is_active")


@admin.register(OutpassRequest)
class OutpassRequestAdmin(admin.ModelAdmin):
    list_display = (
        "resident",
        "destination",
        "expected_return_at",
        "status",
        "decided_by",
        "returned_at",
    )
    list_filter = ("status",)
    search_fields = (
        "resident__username",
        "resident__first_name",
        "resident__last_name",
        "destination",
    )

    # Outpasses are requested, decided and closed in the portal; the record is evidence.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NightAttendance)
class NightAttendanceAdmin(admin.ModelAdmin):
    list_display = ("attendance_date", "resident", "room", "status")
    list_filter = ("attendance_date", "status")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
