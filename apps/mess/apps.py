from django.apps import AppConfig


class MessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mess"
    verbose_name = "Mess Service"

    def ready(self):
        from . import dashboard  # noqa: F401  (registers the dashboard panels)
