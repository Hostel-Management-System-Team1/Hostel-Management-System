from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashWidget, UserChangeForm, UserCreationForm

from .models import User


class PasswordStatusWidget(ReadOnlyPasswordHashWidget):
    """Shows whether a password is set, not the hash algorithm and salt."""

    template_name = "accounts/widgets/password_status.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["is_set"] = bool(value) and not value.startswith("!")
        return context


class HMSUserCreationForm(UserCreationForm):
    """Add-user form: every account gets a password (no single-sign-on option)."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "role", "phone")


class HMSUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        password = self.fields.get("password")
        if password:
            password.widget = PasswordStatusWidget()
            password.help_text = (
                "Passwords are stored encrypted, so nobody can read them, only reset them."
            )


class ProfileForm(forms.ModelForm):
    """What people may change about themselves in the portal.

    Username and role are managed by the Hostel Administrator.
    """

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone")
        labels = {"phone": "Phone number"}
