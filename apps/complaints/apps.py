from django.apps import AppConfig


class ComplaintsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.complaints"
    verbose_name = "Complaint Service"

    def ready(self):
        from . import dashboard  # noqa: F401  (registers the dashboard panels)
