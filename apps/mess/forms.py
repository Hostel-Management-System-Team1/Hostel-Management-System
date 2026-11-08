from datetime import datetime

from django import forms
from django.utils import timezone

from hms.forms import BootstrapFormMixin

from .models import MessMenuItem


class MealForm(BootstrapFormMixin, forms.Form):
    """Publish or change one meal: the day, which meal, when it is served and what it is."""

    menu_date = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date"}))
    meal_type = forms.ChoiceField(label="Meal", choices=MessMenuItem.MealType.choices)
    time = forms.TimeField(
        label="Served at",
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        help_text="Residents can skip the meal until 24 hours before this time.",
    )
    description = forms.CharField(
        label="Menu",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean(self):
        data = super().clean()
        if data.get("menu_date") and data.get("time"):
            served = timezone.make_aware(datetime.combine(data["menu_date"], data["time"]))
            if served <= timezone.now():
                raise forms.ValidationError(
                    "A meal can be published or changed only before it is served."
                )
            data["meal_datetime"] = served
        return data
