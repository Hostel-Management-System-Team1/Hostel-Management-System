"""Invoicing, payment and receipts (HMS-F-010 to HMS-F-012)."""

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from apps.audit import service as audit

from . import gateway
from .models import FeeHead, Invoice, InvoiceItem, Payment, Receipt

logger = logging.getLogger(__name__)


class InvoiceAlreadyPaid(Exception):
    """The invoice is already Paid (HTTP 409)."""


class UnknownPaymentSession(Exception):
    """A callback named a payment session we never created (HTTP 404)."""


class InvalidSignature(Exception):
    """A callback's signature does not match (HTTP 400)."""


def generate_invoice(allocation):
    """Raise the itemised invoice for a confirmed allocation (HMS-F-010).

    The items are the active fee heads for the room's type, so the total always equals their
    sum. Without a fee structure for the room type no invoice can be raised; the administrator
    adds fee heads and the invoice is raised by ``generate_missing_invoices``.
    """
    existing = Invoice.objects.filter(
        allocation=allocation, kind=Invoice.Kind.ALLOCATION
    ).first()
    if existing:
        return existing
    heads = list(FeeHead.objects.filter(
        room_type=allocation.bed.room.room_type, active=True).order_by("id"))
    if not heads:
        logger.warning("No fee structure for %s rooms; no invoice for allocation %s",
                       allocation.bed.room.room_type, allocation.pk)
        return None
    today = timezone.localdate()
    with transaction.atomic():
        invoice = Invoice.objects.create(
            resident=allocation.resident,
            allocation=allocation,
            kind=Invoice.Kind.ALLOCATION,
            description=f"Hostel fees — {allocation.bed.room}",
            issue_date=today,
            due_date=today + timedelta(days=settings.FEE_DUE_DAYS),
        )
        InvoiceItem.objects.bulk_create([
            InvoiceItem(invoice=invoice, description=head.name, amount=head.amount,
                        refundable=head.refundable)
            for head in heads
        ])
        invoice.total = sum((head.amount for head in heads), Decimal("0.00"))
        invoice.save(update_fields=["total"])
        audit.record(
            "invoice.raised", target=invoice, actor=allocation.allocated_by,
            detail={"invoice": invoice.number, "total": invoice.total},
        )
    return invoice


def start_payment(invoice, method, return_url=""):
    """Open a payment session and return (payment, gateway page URL). Invoice stays as it is."""
    if invoice.status == Invoice.Status.PAID:
        raise InvoiceAlreadyPaid("This invoice is already paid.")
    payment = Payment(invoice=invoice, method=method, amount=invoice.total,
                      return_url=return_url[:200])
    redirect_url = gateway.get_gateway().create_session(payment)  # may raise GatewayUnavailable
    payment.save()
    audit.record("payment.started", target=payment, detail={
        "invoice": invoice.number, "method": method, "amount": payment.amount})
    return payment, redirect_url


def handle_callback(payload):
    """Apply the gateway's signed callback to its payment (HMS-F-011).

    SUCCESS marks the invoice Paid and issues the receipt; FAILED and ABANDONED leave the
    invoice as it was. Repeating a callback changes nothing. A callback with a bad signature
    changes nothing and is written to the audit log.
    """
    if not gateway.signature_is_valid(payload):
        audit.record(
            "payment.callback_rejected", actor=None, label="payment gateway",
            outcome=audit.AuditEntry.Outcome.DENIED,
            detail={"session": str(payload.get("paymentSessionId", ""))[:32]},
        )
        raise InvalidSignature("Invalid signature.")
    return _apply_callback(payload)


@transaction.atomic
def _apply_callback(payload):
    try:
        payment = Payment.objects.select_for_update().select_related("invoice").get(
            session_id=payload["paymentSessionId"])
    except Payment.DoesNotExist as error:
        raise UnknownPaymentSession("Unknown payment session.") from error
    if payment.status != Payment.Status.INITIATED:
        return payment  # already settled; a repeated callback is harmless
    status = payload["status"]
    payment.gateway_ref = str(payload.get("gatewayRef", ""))[:60]
    payment.completed_at = timezone.now()
    if status == "SUCCESS":
        invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
        if invoice.status == Invoice.Status.PAID:
            payment.status = Payment.Status.DUPLICATE
        else:
            payment.status = Payment.Status.SUCCESS
            invoice.status = Invoice.Status.PAID
            invoice.paid_at = payment.completed_at
            invoice.save(update_fields=["status", "paid_at"])
            payment.save()
            receipt = Receipt.objects.create(
                invoice=invoice, payment=payment, amount=payment.amount)
            audit.record(
                "payment.succeeded", target=payment, actor=None, label="payment gateway",
                detail={"invoice": invoice.number, "receipt": receipt.number,
                        "amount": payment.amount, "gatewayRef": payment.gateway_ref},
            )
            return payment
    elif status == "FAILED":
        payment.status = Payment.Status.FAILED
    else:
        payment.status = Payment.Status.ABANDONED
    payment.save()
    audit.record(
        f"payment.{payment.status.lower()}", target=payment, actor=None, label="payment gateway",
        outcome=audit.AuditEntry.Outcome.FAILURE,
        detail={"invoice": payment.invoice.number, "gatewayRef": payment.gateway_ref},
    )
    return payment


def abandon_stale_payments(minutes=30):
    """Mark payment sessions nobody finished as Abandoned. Returns how many."""
    cutoff = timezone.now() - timedelta(minutes=minutes)
    return Payment.objects.filter(
        status=Payment.Status.INITIATED, created_at__lt=cutoff
    ).update(status=Payment.Status.ABANDONED, completed_at=timezone.now())


def _send_overdue_reminder(invoice):
    """Send one overdue notice to the resident and, when available, their guardian."""
    application = None
    if invoice.allocation_id:
        application = invoice.allocation.application
    else:
        # Mess invoices may not be linked to a hostel allocation. Use the resident's
        # most recently submitted application to obtain their contact and guardian details.
        application = invoice.resident.applications.order_by("-submitted_at").first()

    resident_email = (
        getattr(application, "email", "") or invoice.resident.email
    ).strip()
    guardian_email = (getattr(application, "guardian_email", "") or "").strip()

    # Prefer the resident in To and the guardian in BCC so their email addresses are not
    # disclosed to one another. If only one address is available, send to that address.
    to = [resident_email] if resident_email else []
    bcc = [guardian_email] if resident_email and guardian_email else []
    if not to and guardian_email:
        to = [guardian_email]
    if not to:
        logger.warning(
            "Cannot send overdue reminder for invoice %s: no resident or guardian email",
            invoice.number,
        )
        return False

    subject = f"Overdue hostel fee reminder — {invoice.number}"
    resident_name = (
        getattr(application, "full_name", "")
        or invoice.resident.get_full_name()
        or invoice.resident.username
    )
    body = (
        f"Dear {resident_name},\n\n"
        f"Our records show that invoice {invoice.number} ({invoice.description}) is overdue.\n"
        f"Amount due: ₹{invoice.total}\n"
        f"Due date: {invoice.due_date:%d %b %Y}\n\n"
        "Please sign in to the Hostel Management System to review the invoice and "
        "complete payment.\n\n"
        "If you have already paid, please contact the hostel office with your payment details.\n\n"
        "Regards,\nHostel Management System"
    )
    message = EmailMessage(
        subject=subject, body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=to, bcc=bcc
    )
    return message.send(fail_silently=False) == 1


def process_overdue_invoices(today=None):
    """Mark past-due unpaid invoices Overdue and send each one reminder at most once.

    The command invoking this service should be scheduled for 00:00 daily. Using
    ``due_date__lt=today`` means an invoice is not overdue on its due date; it becomes
    overdue on the following calendar day, as required by HMS-F-013.
    """
    today = today or timezone.localdate()
    overdue_candidates = Invoice.objects.filter(
        due_date__lt=today, status=Invoice.Status.UNPAID
    )
    marked_overdue = overdue_candidates.update(status=Invoice.Status.OVERDUE)

    reminders_sent = 0
    reminders_failed = 0
    reminders_skipped = 0
    pending = Invoice.objects.filter(
        due_date__lt=today, status=Invoice.Status.OVERDUE, reminder_sent_at__isnull=True
    ).select_related(
        "resident", "allocation__application"
    ).order_by("pk")

    for invoice in pending:
        try:
            if _send_overdue_reminder(invoice):
                invoice.reminder_sent_at = timezone.now()
                invoice.save(update_fields=["reminder_sent_at"])
                reminders_sent += 1
            else:
                reminders_skipped += 1
        except Exception:
            # One provider failure should not prevent reminders for other residents. Leave
            # reminder_sent_at empty so the next scheduled run can retry this invoice.
            logger.exception("Failed to send overdue reminder for invoice %s", invoice.number)
            reminders_failed += 1

    return {
        "marked_overdue": marked_overdue,
        "reminders_sent": reminders_sent,
        "reminders_failed": reminders_failed,
        "reminders_skipped": reminders_skipped,
    }
