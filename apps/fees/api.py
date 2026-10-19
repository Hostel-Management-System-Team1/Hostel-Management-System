from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import roles

from . import gateway, services
from .models import Invoice
from .serializers import CallbackSerializer, PaymentStartSerializer


class AlreadyPaid(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This invoice is already paid."


class GatewayDown(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "The payment gateway is unavailable."


class PaymentStartView(APIView):
    """POST /api/v1/invoices/{id}/payments — begin paying an invoice (HMS-F-011)."""

    permission_classes = [roles(User.Role.RESIDENT)]

    def post(self, request, pk):
        invoice = Invoice.objects.filter(pk=pk, resident=request.user).first()
        if invoice is None:
            raise NotFound("Invoice not found.")
        serializer = PaymentStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment, redirect_url = services.start_payment(
                invoice, serializer.validated_data["method"],
                serializer.validated_data.get("returnUrl", ""),
            )
        except services.InvoiceAlreadyPaid as error:
            raise AlreadyPaid(str(error)) from error
        except gateway.GatewayUnavailable as error:
            raise GatewayDown(str(error)) from error
        return Response(
            {"paymentSessionId": payment.session_id, "redirectUrl": redirect_url},
            status=status.HTTP_201_CREATED,
        )


class PaymentCallbackView(APIView):
    """POST /api/v1/payments/callback — the gateway's webhook.

    Not signed in (the gateway has no account) but every request is checked against the
    shared-secret signature.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CallbackSerializer(data=request.data)
        if not serializer.is_valid():
            raise ValidationError("Malformed callback.")
        try:
            services.handle_callback(dict(serializer.validated_data))
        except services.InvalidSignature as error:
            raise ValidationError(str(error)) from error
        except services.UnknownPaymentSession as error:
            raise NotFound(str(error)) from error
        return Response({"received": True})
