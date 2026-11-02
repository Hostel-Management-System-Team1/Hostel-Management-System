from django.contrib.admin.apps import AdminConfig


class HMSAdminConfig(AdminConfig):
    """Django's admin app, using the HMS admin site (hms/admin_site.py)."""

    default_site = "hms.admin_site.HMSAdminSite"

    def ready(self):
        # Before the ModelAdmins are registered (super().ready() runs autodiscover), swap
        # Django's calendar/clock pop-ups and "Today | Now" links for the browser's own
        # date and time pickers, which match the portal's forms.
        from django import forms
        from django.contrib.admin import options
        from django.db import models

        defaults = options.FORMFIELD_FOR_DBFIELD_DEFAULTS
        defaults[models.DateField] = {
            "widget": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
        }
        defaults[models.TimeField] = {
            "widget": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
        }
        defaults[models.DateTimeField] = {
            "form_class": forms.SplitDateTimeField,
            "widget": forms.SplitDateTimeWidget(
                date_attrs={"type": "date"}, time_attrs={"type": "time"},
                date_format="%Y-%m-%d", time_format="%H:%M",
            ),
        }
        super().ready()
