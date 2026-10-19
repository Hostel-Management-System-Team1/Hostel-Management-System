"""Input validators shared by every module (HMS-SR-006).

Free text is limited to the characters a real value needs, so markup and script never reach
the database; templates also escape everything they print.
"""

from django.core.validators import RegexValidator

person_name = RegexValidator(
    r"^[A-Za-z][A-Za-z .'-]{1,99}$",
    "Use letters, spaces, full stops, apostrophes and hyphens only.",
)
phone_number = RegexValidator(
    r"^\+?\d{10,15}$", "Enter 10 to 15 digits, with an optional leading +."
)
plain_text = RegexValidator(
    r"^[^<>]*$", "Angle brackets are not allowed.", code="no_markup"
)
