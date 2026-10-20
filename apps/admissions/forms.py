from django import forms

from hms.forms import BootstrapFormMixin

from .models import Application, Block, Gender, RoomType

SECTIONS = [
    ("Personal details", ["enrolment_number", "full_name", "date_of_birth", "gender",
                          "phone", "email", "address"]),
    ("Academic details", ["programme", "year_of_study", "cgpa"]),
    ("Guardian details", ["guardian_name", "guardian_relation", "guardian_phone",
                          "guardian_email"]),
    ("Medical details", ["blood_group", "medical_conditions"]),
    ("Room preference", ["preferred_block", "room_type"]),
]


class ApplicationForm(BootstrapFormMixin, forms.ModelForm):
    """The resident's admission application, laid out in the sections above."""

    class Meta:
        model = Application
        fields = [name for _, names in SECTIONS for name in names]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "address": forms.Textarea(attrs={"rows": 3}),
            "medical_conditions": forms.Textarea(attrs={"rows": 3}),
            "phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
            "guardian_phone": forms.TextInput(attrs={"type": "tel"}),
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["preferred_block"].queryset = Block.objects.all()
        self.fields["preferred_block"].empty_label = "No preference"
        self.fields["gender"].choices = [("", "Select")] + list(Gender.choices)
        self.fields["room_type"].choices = [("", "Select")] + list(RoomType.choices)

    def section_fields(self):
        return [(title, [self[name] for name in names]) for title, names in SECTIONS]


class DecisionForm(BootstrapFormMixin, forms.Form):
    note = forms.CharField(
        label="Reason (required when rejecting)", required=False, max_length=300,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
