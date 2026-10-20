"""The admin site is the Hostel Administrator's portal (SAD 3.6).

Administrators sign in straight to it. It adds an HMS dashboard with live
counts, HMS navigation in the sidebar (templates/admin/nav_sidebar.html), and
"coming in Sprint N" pages for administrator screens not built yet.
"""

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.views import redirect_to_login
from django.db.models import Count
from django.http import Http404
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.accounts.models import User

from .navigation import find_item, nav_for


class HMSAdminSite(admin.AdminSite):
    site_header = "Hostel Management System"
    site_title = "HMS Admin"
    index_title = "Administration"
    # registration/password_change_*.html are the portal's versions; the admin keeps its own.
    password_change_template = "admin/hms_password_change_form.html"
    password_change_done_template = "admin/hms_password_change_done.html"

    def login(self, request, extra_context=None):
        """Everyone signs in on the portal's page; administrators land back here afterwards."""
        if request.user.is_authenticated:
            # Signed in, but not an administrator: the portal is their place.
            return redirect("home")
        next_url = request.GET.get("next", reverse("admin:index"))
        return redirect_to_login(next_url, settings.LOGIN_URL)

    def app_index(self, request, app_label, extra_context=None):
        """No per-app overview pages: the HMS sidebar replaces them.

        An app with a single list (e.g. Auth & RBAC Service → Users) opens that list;
        anything else goes to the dashboard.
        """
        app_list = self.get_app_list(request, app_label)
        models = app_list[0]["models"] if app_list else []
        if len(models) == 1 and models[0].get("admin_url"):
            return redirect(models[0]["admin_url"])
        return redirect("admin:index")

    def get_urls(self):
        return [
            path("m/<slug:slug>/", self.admin_view(self.module_view), name="hms_module"),
        ] + super().get_urls()

    def index(self, request, extra_context=None):
        counts = dict(User.objects.values_list("role").annotate(n=Count("id")))
        users_url = reverse("admin:accounts_user_changelist")
        total = sum(counts.values())
        context = {
            "stats": {
                "total": total,
                "residents": counts.get(User.Role.RESIDENT, 0),
                "staff": total - counts.get(User.Role.RESIDENT, 0),
                "inactive": User.objects.filter(is_active=False).count(),
            },
            "role_rows": [
                {
                    "label": label,
                    "count": counts.get(value, 0),
                    "url": f"{users_url}?role__exact={value}",
                }
                for value, label in User.Role.choices
            ],
            "users_url": users_url,
            "recent_actions": LogEntry.objects.select_related("user", "content_type")[:8],
            "modules": [
                entry
                for _, items in nav_for(request.user, admin=True)
                for entry in items
                if entry["url_name"] != "admin:index"
            ],
            **(extra_context or {}),
        }
        return super().index(request, context)

    def module_view(self, request, slug):
        entry = find_item(request.user, slug, admin=True)
        if entry is None:
            raise Http404("No such page")
        context = {**self.each_context(request), "title": entry["label"], "entry": entry}
        return TemplateResponse(request, "admin/hms_module.html", context)
