from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import role_required

from . import gateway, services
from .models import Invoice, Payment, Receipt
from .receipts import receipt_pdf

R = User.Role


def own_invoice(request, pk):
    invoice = get_object_or_404(Invoice.objects.prefetch_related("items"), pk=pk)
    if invoice.resident_id != request.user.pk:
        raise PermissionDenied
    return invoice


@role_required(R.RESIDENT)
def invoice_list(request):
    invoices = Invoice.objects.filter(resident=request.user).select_related("receipt")
    return render(request, "fees/invoice_list.html", {"invoices": invoices})


@role_required(R.RESIDENT)
def invoice_detail(request, pk):
    invoice = own_invoice(request, pk)
    return render(request, "fees/invoice_detail.html", {
        "invoice": invoice,
        "methods": Payment.Method.choices,
        "receipt": getattr(invoice, "receipt", None),
    })


@role_required(R.RESIDENT)
@require_POST
def invoice_pay(request, pk):
    """Start an online payment: hand the resident to the gateway's page."""
    invoice = own_invoice(request, pk)
    method = request.POST.get("method")
    if method not in Payment.Method.values:
        messages.error(request, "Choose how you want to pay.")
        return redirect("fees:invoice_detail", pk=pk)
    try:
        _, redirect_url = services.start_payment(
            invoice, method, reverse("fees:invoice_detail", args=[pk]))
    except services.InvoiceAlreadyPaid:
        messages.info(request, "This invoice is already paid.")
        return redirect("fees:invoice_detail", pk=pk)
    except gateway.GatewayUnavailable:
        messages.error(request, "The payment gateway is not reachable. Nothing was charged; "
                                "the invoice is still unpaid. Please try again shortly.")
        return redirect("fees:invoice_detail", pk=pk)
    return redirect(redirect_url)


def mock_gateway(request, session_id):
    """The stand-in gateway's hosted payment page.

    It plays the provider: the resident chooses an outcome, and the page sends the HMS the
    same signed callback a real gateway would. No card details are asked for or kept.
    """
    payment = get_object_or_404(Payment.objects.select_related("invoice"), session_id=session_id)
    if request.method == "POST":
        outcome = {"pay": "SUCCESS", "fail": "FAILED", "cancel": "ABANDONED"}.get(
            request.POST.get("outcome"))
        if outcome is None:
            raise Http404("Unknown outcome")
        payload = {"paymentSessionId": payment.session_id, "status": outcome,
                   "gatewayRef": f"MOCK-{payment.session_id[:10].upper()}"}
        payload["signature"] = gateway.sign(payload)
        services.handle_callback(payload)
        notes = {
            "SUCCESS": (messages.success, "Payment received. Your receipt is ready to download."),
            "FAILED": (messages.error, "The payment failed. Nothing was charged and the invoice "
                                        "is still unpaid."),
            "ABANDONED": (messages.warning, "The payment was cancelled. The invoice is still "
                                            "unpaid."),
        }
        notify, text = notes[outcome]
        notify(request, text)
        target = payment.return_url
        if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
            target = "/"
        return redirect(target)
    return render(request, "fees/mock_gateway.html", {"payment": payment})


def receipt_download(request, pk):
    """The receipt PDF, for the resident it belongs to and for administrators."""
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    receipt = get_object_or_404(Receipt.objects.select_related("invoice__resident"), pk=pk)
    owner = receipt.invoice.resident_id == request.user.pk
    if not (owner or request.user.role == R.ADMINISTRATOR):
        raise PermissionDenied
    response = FileResponse(
        iter([receipt_pdf(receipt)]), content_type="application/pdf",
        filename=f"{receipt.number}.pdf",
    )
    response["Content-Disposition"] = f'inline; filename="{receipt.number}.pdf"'
    return response
