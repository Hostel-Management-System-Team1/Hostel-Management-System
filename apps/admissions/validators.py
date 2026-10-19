"""Input validation for admission data (HMS-SR-006).

Free text is limited to the characters a real value needs, so markup and script never reach
the database; templates also escape everything they print.
"""

import re
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

person_name = RegexValidator(
    r"^[A-Za-z][A-Za-z .'-]{1,99}$",
    "Use letters, spaces, full stops, apostrophes and hyphens only.",
)
phone_number = RegexValidator(
    r"^\+?\d{10,15}$", "Enter 10 to 15 digits, with an optional leading +."
)
enrolment_format = RegexValidator(
    r"^[A-Za-z0-9]{6,20}$", "An enrolment number is 6 to 20 letters and digits."
)
plain_text = RegexValidator(
    r"^[^<>]*$", "Angle brackets are not allowed.", code="no_markup"
)


def past_birth_date(value):
    today = date.today()
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if value >= today or age < 15 or age > 60:
        raise ValidationError("Enter a valid date of birth (age 15 to 60).")


def normalise_enrolment(value):
    return re.sub(r"\s+", "", value).upper()
