from django import forms

from hms.forms import BootstrapFormMixin

from .models import Complaint


class ComplaintForm(BootstrapFormMixin, forms.ModelForm):
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
                attrs={"placeholder": "e.g. Tap leaking in room A-101"}
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "What is wrong, where, and since when",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The SRS sets the priority from the category (HMS-F-040); say so where it is chosen.
        self.fields["category"].help_text = (
            "Sets the priority: Maintenance is High (fixed within 48 hours), Cleaning is "
            "Medium (96 hours), Noise and Other are Low."
        )
        self.fields["category"].widget.attrs["aria-describedby"] = "id_category_help"

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")

        if photo and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError(
                "Photo size must not exceed 5 MB."
            )

        return photo
