from decimal import Decimal

from django import template
from django.contrib.humanize.templatetags.humanize import intcomma

register = template.Library()


@register.filter
def inr(value):
    """Format an amount in rupees: 45000 -> ₹45,000.00."""
    if value in (None, ""):
        return ""
    amount = Decimal(value).quantize(Decimal("0.01"))
    return f"₹{intcomma(amount)}"
