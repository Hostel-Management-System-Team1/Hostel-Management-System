from django.apps import AppConfig


class AdmissionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.admissions"
    verbose_name = "Admission & Allocation Service"

    def ready(self):
        from . import dashboard  # noqa: F401  (registers the dashboard panels)
