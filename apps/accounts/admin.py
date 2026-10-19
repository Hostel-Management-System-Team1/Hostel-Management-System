from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.db.models import Count
from django.utils.html import format_html
from django.utils.timesince import timesince

from hms.navigation import initials

from .forms import HMSUserChangeForm, HMSUserCreationForm
from .models import User

# Access is decided by User.role, so Django's permission groups are not used.
admin.site.unregister(Group)


def list_url(request, **changes):
    """The current change-list URL with some query parameters set (or removed when None)."""
    params = request.GET.copy()
    params.pop("p", None)  # back to the first page
    for key, value in changes.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    query = params.urlencode()
    return f"{request.path}?{query}" if query else request.path


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # templates/admin/accounts/user/change_list.html shows these filters as role tabs
    # and an Active/Inactive switch instead of Django's filter sidebar.
    list_display = ("person", "email_address", "role_badge", "status_badge", "last_seen")
    list_display_links = ("person",)
    list_filter = ("role", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
    list_per_page = 25
    # No bulk actions (Django's only one is "delete selected"); delete from a user's own page.
    actions = None
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email", "phone")}),
        ("Role and access", {"fields": ("role", "is_active")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    form = HMSUserChangeForm
    add_form = HMSUserCreationForm
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "role", "phone", "password1", "password2"),
        }),
    )

    @admin.display(description="Name", ordering="first_name")
    def person(self, obj):
        return format_html(
            '<span class="hms-person"><span class="hms-person__avatar">{}</span>'
            '<span class="hms-person__text"><strong>{}</strong><small>@{}</small></span></span>',
            initials(obj),
            obj.get_full_name() or obj.username,
            obj.username,
        )

    @admin.display(description="Email", ordering="email")
    def email_address(self, obj):
        return obj.email or format_html('<span class="hms-quiet">Not set</span>')

    @admin.display(description="Role", ordering="role")
    def role_badge(self, obj):
        return format_html(
            '<span class="hms-badge hms-badge--{}">{}</span>',
            obj.role.lower().replace("_", "-"),
            obj.get_role_display(),
        )

    @admin.display(description="Status", ordering="is_active")
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span class="hms-status hms-status--on">Active</span>')
        return format_html('<span class="hms-status">Inactive</span>')

    @admin.display(description="Last sign-in", ordering="last_login")
    def last_seen(self, obj):
        if not obj.last_login:
            return format_html('<span class="hms-quiet">Never</span>')
        return f"{timesince(obj.last_login).split(',')[0]} ago"

    def changelist_view(self, request, extra_context=None):
        counts = dict(User.objects.values_list("role").annotate(n=Count("id")))
        role = request.GET.get("role__exact", "")
        active = request.GET.get("is_active__exact", "")
        role_tabs = [
            {
                "label": "All",
                "count": sum(counts.values()),
                "url": list_url(request, role__exact=None),
                "active": not role,
            }
        ] + [
            {
                "label": label,
                "count": counts.get(value, 0),
                "url": list_url(request, role__exact=value),
                "active": role == value,
            }
            for value, label in User.Role.choices
        ]
        status_tabs = [
            {"label": "All", "url": list_url(request, is_active__exact=None), "active": not active},
            {"label": "Active", "url": list_url(request, is_active__exact="1"),
             "active": active == "1"},
            {"label": "Inactive", "url": list_url(request, is_active__exact="0"),
             "active": active == "0"},
        ]
        context = {
            "title": "Users & roles",
            "role_tabs": role_tabs,
            "status_tabs": status_tabs,
            **(extra_context or {}),
        }
        return super().changelist_view(request, context)
