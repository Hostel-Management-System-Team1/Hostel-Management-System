from django import forms

from .models import Complaint


class ComplaintForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = (
            "title",
            "category",
            "description",
            "photo",
        )

        widgets = {
            "title": forms.TextInput(
                attrs={"placeholder": "Enter complaint title"}
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Describe your complaint",
                }
            ),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")

        if photo and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError(
                "Photo size must not exceed 5 MB."
            )

        return photo