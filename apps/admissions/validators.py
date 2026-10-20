"""Input validation for admission data (HMS-SR-006); shared validators are in hms.validators."""

import re
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from hms.validators import person_name, phone_number, plain_text  # noqa: F401  (re-exported)

enrolment_format = RegexValidator(
    r"^[A-Za-z0-9]{6,20}$", "An enrolment number is 6 to 20 letters and digits."
)


def past_birth_date(value):
    today = date.today()
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if value >= today or age < 15 or age > 60:
        raise ValidationError("Enter a valid date of birth (age 15 to 60).")


def normalise_enrolment(value):
    return re.sub(r"\s+", "", value).upper()
