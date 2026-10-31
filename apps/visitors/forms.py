from django import forms

from apps.accounts.models import User

from .models import Visitor


class VisitorRegistrationForm(forms.ModelForm):
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
            role=User.Role.RESIDENT
        )
