from django.apps import AppConfig


class FeesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fees"
    verbose_name = "Fee & Payment Service"

    def ready(self):
        from apps.admissions.models import Allocation
        from apps.admissions.signals import allocation_confirmed

        from . import dashboard  # noqa: F401  (registers the dashboard panels)
        from .services import generate_invoice

        def raise_invoice(sender, allocation, **kwargs):
            generate_invoice(allocation)

        # weak=False: raise_invoice is a local function, so a weak reference would let it be
        # garbage-collected and the invoice would silently stop being raised.
        allocation_confirmed.connect(
            raise_invoice, sender=Allocation, weak=False, dispatch_uid="fees.raise_invoice"
        )
