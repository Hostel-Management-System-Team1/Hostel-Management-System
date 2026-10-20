from django.contrib import admin

from hms.templatetags.hms_extras import inr


def money(field, label=None):
    """An admin column (or read-only field) that shows ``field`` as rupees and still sorts."""

    @admin.display(description=label or field.replace("_", " ").capitalize(), ordering=field)
    def column(self, obj):
        return inr(getattr(obj, field))

    column.__name__ = f"{field}_inr"
    return column
