"""Signals other modules listen to, so Admission & Allocation does not import them."""

from django.dispatch import Signal

# Sent inside the allocation transaction, once a bed is confirmed. Receivers get ``allocation``.
# Fee & Payment raises the invoice here (HMS-F-010).
allocation_confirmed = Signal()
