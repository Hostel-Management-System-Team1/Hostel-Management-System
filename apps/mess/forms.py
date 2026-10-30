
from django import forms

from .models import MessMenuItem


class MessMenuForm(forms.ModelForm):

    class Meta:
        model = MessMenuItem

        fields = [
            "menu_date",
            "meal_datetime",
            "meal_type",
            "description",
        ]

        widgets = {
            "menu_date": forms.DateInput(
                attrs={"type": "date"}
            ),
            "meal_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "description": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()

        menu_date = cleaned_data.get("menu_date")
        meal_datetime = cleaned_data.get("meal_datetime")

        if menu_date and meal_datetime:
            if menu_date != meal_datetime.date():
                self.add_error(
                    "meal_datetime",
                    "Meal date and scheduled date must match.",
                )

        if meal_datetime:
            from django.utils import timezone

            if meal_datetime <= timezone.now():
                self.add_error(
                    "meal_datetime",
                    "Meal date and time must be in the future.",
                )

        return cleaned_data
