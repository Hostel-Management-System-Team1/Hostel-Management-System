"""Invoicing, payment and receipts (HMS-F-010 to HMS-F-012)."""

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
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
