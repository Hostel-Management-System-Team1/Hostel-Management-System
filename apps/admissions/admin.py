from django import forms
from django.contrib import admin
from django.db.models import ProtectedError

from .models import Allocation, AllocationPolicy, Application, Bed, Block, Room


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("name", "gender")
    list_filter = ("gender",)
    search_fields = ("name",)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    """Administrators can look applications up; the warden decides them in the portal.

    Medical details are left out: only the applicant and the warden need them (SO-1).
    """

    list_display = ("application_number", "full_name", "enrolment_number", "gender",
                    "room_type", "status", "submitted_at")
    list_filter = ("status", "gender", "room_type", "academic_session")
    search_fields = ("application_number", "full_name", "enrolment_number")
    actions = None
    fieldsets = (
        (None, {"fields": ("application_number", "academic_session", "status", "submitted_at")}),
        ("Applicant", {"fields": ("enrolment_number", "full_name", "date_of_birth", "gender",
                                  "phone", "email", "address")}),
        ("Academic", {"fields": ("programme", "year_of_study", "cgpa")}),
        ("Guardian", {"fields": ("guardian_name", "guardian_relation", "guardian_phone",
                                 "guardian_email")}),
        ("Preference", {"fields": ("preferred_block", "room_type")}),
        ("Decision", {"fields": ("decided_by", "decided_at", "decision_note")}),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class BedInlineForm(forms.ModelForm):
    """Beds are Occupied or Vacant through allocations; here they can only be blocked or freed."""

    class Meta:
        model = Bed
        fields = ("status",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.status == Bed.Status.OCCUPIED:
            self.fields["status"].disabled = True
        else:
            self.fields["status"].choices = [
                (Bed.Status.VACANT, "Vacant"), (Bed.Status.BLOCKED, "Blocked")]


class BedInline(admin.TabularInline):
    model = Bed
    form = BedInlineForm
    extra = 0
    can_delete = False
    readonly_fields = ("label",)
    fields = ("label", "status")

    def has_add_permission(self, request, obj=None):
        return False  # beds follow the room's bed capacity


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("__str__", "floor", "room_type", "bed_capacity", "occupancy", "status")
    list_filter = ("block", "room_type", "status", "floor")
    search_fields = ("number", "block__name")
    inlines = [BedInline]
    actions = None

    @admin.display(description="Occupied")
    def occupancy(self, obj):
        return f"{obj.occupied_count} of {obj.bed_capacity}"

    def has_delete_permission(self, request, obj=None):
        # A room with an occupied bed cannot be deleted (HMS-F-061).
        if obj is not None and obj.beds.filter(status=Bed.Status.OCCUPIED).exists():
            return False
        return super().has_delete_permission(request, obj)

    def delete_model(self, request, obj):
        try:
            super().delete_model(request, obj)
        except ProtectedError:
            self.message_user(request, "This room has history that must be kept.", level="error")


@admin.register(AllocationPolicy)
class AllocationPolicyAdmin(admin.ModelAdmin):
    """The order applicants are ranked in when beds are allocated (HMS-F-002)."""

    fields = ("ranking",)

    def has_add_permission(self, request):
        return not AllocationPolicy.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect

        policy = AllocationPolicy.current()
        return redirect("admin:admissions_allocationpolicy_change", policy.pk)


@admin.register(Allocation)
class AllocationAdmin(admin.ModelAdmin):
    list_display = ("resident", "bed", "status", "allocated_at", "allocated_by")
    list_filter = ("status", "bed__room__block")
    search_fields = ("resident__username", "resident__first_name", "resident__last_name")
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
