from rest_framework import serializers

from .models import Payment


class PaymentStartSerializer(serializers.Serializer):
    """POST /api/v1/invoices/{id}/payments request body."""

    method = serializers.ChoiceField(choices=Payment.Method.choices)
    returnUrl = serializers.CharField(required=False, allow_blank=True, max_length=200)


class CallbackSerializer(serializers.Serializer):
    """POST /api/v1/payments/callback request body (sent by the gateway)."""

    paymentSessionId = serializers.CharField()
    status = serializers.ChoiceField(choices=["SUCCESS", "FAILED", "ABANDONED"])
    gatewayRef = serializers.CharField(allow_blank=True)
    signature = serializers.CharField()
