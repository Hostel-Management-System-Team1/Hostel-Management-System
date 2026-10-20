from decimal import Decimal

from django.db.models import Sum
from django.urls import reverse

from apps.accounts.models import User
from hms.dashboard import facts_panel, provider

from .models import Invoice


@provider
def panels(user):
    if user.role != User.Role.RESIDENT:
        return []
    invoices = Invoice.objects.filter(resident=user)
    if not invoices.exists():
        return []
    owed = invoices.exclude(status=Invoice.Status.PAID)
    total = owed.aggregate(total=Sum("total"))["total"] or Decimal("0.00")
    next_due = owed.order_by("due_date").first()
    facts = [("Outstanding", f"₹{total:,.2f}")]
    if next_due:
        facts.append(("Next due", next_due.due_date.strftime("%d %b %Y")))
        if next_due.status == Invoice.Status.OVERDUE:
            facts.append(("Status", "Overdue"))
    else:
        facts.append(("Status", "All paid"))
    return [facts_panel("Fees", facts, link=("View invoices", reverse("fees:invoice_list")))]
