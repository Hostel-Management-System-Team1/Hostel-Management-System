from django.apps import AppConfig


class GateConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.gate"
    verbose_name = "Gate & Outpass Service"

    def ready(self):
        from . import dashboard  # noqa: F401  (registers the dashboard panels)
