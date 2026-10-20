from django.contrib.admin.apps import AdminConfig


class HMSAdminConfig(AdminConfig):
    """Django's admin app, using the HMS admin site (hms/admin_site.py)."""

    default_site = "hms.admin_site.HMSAdminSite"
