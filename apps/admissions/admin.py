from django.contrib import admin

from .models import Application, Block


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
