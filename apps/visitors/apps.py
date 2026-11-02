from django.apps import AppConfig


class VisitorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.visitors"
    verbose_name = "Visitor Service"

    def ready(self):
        from . import dashboard  # noqa: F401  (registers the dashboard panels)
