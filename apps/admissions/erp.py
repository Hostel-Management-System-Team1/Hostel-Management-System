"""Adapter for the institutional student-records system (SRS 3.3, SAD 3.7).

The ERP is the authority on who is a student; the HMS reads it and never writes to it. This
repository has no ERP sandbox, so the default adapter only checks the enrolment number's
format. Point ``HMS_ERP_ADAPTER`` at a class with the same ``lookup`` method to use a real
read-only HTTPS/JSON client (see DEVIATIONS.md).
"""

import re

from django.conf import settings
from django.utils.module_loading import import_string


class StubERP:
    """Accepts any well-formed enrolment number and returns no further details."""

    def lookup(self, enrolment_number):
        """Return a dict of student details, or None if the number is unknown."""
        if re.fullmatch(r"[A-Z0-9]{6,20}", enrolment_number):
            return {}
        return None


def lookup(enrolment_number):
    adapter = import_string(settings.HMS_ERP_ADAPTER)()
    return adapter.lookup(enrolment_number)
