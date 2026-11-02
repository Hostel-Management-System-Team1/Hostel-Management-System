from django import forms

from apps.accounts.models import User
from hms.forms import BootstrapFormMixin

from .models import Visitor


class VisitorRegistrationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Visitor
        fields = (
            "visitor_name",
            "phone",
            "id_proof_type",
            "id_proof_number",
            "resident",
            "purpose",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["resident"].queryset = User.objects.filter(
            role=User.Role.RESIDENT, is_active=True
        ).order_by("first_name", "last_name")
        self.fields["resident"].label_from_instance = (
            lambda user: f"{user.get_full_name() or user.username} (@{user.username})"
        )
        self.fields["resident"].label = "Visiting resident"
        self.fields["id_proof_type"].widget.attrs["placeholder"] = "e.g. Aadhaar, driving licence"
