"""The payment gateway adapter (SAD 3.6, HMS-SR-005).

A real deployment points this at a PCI-DSS compliant provider: we create a payment session,
send the resident to the provider's hosted page, and receive a signed callback. The bundled
``MockGateway`` plays the provider with a hosted page of its own (apps/fees/views.py,
``mock_gateway``) so the whole flow can be demonstrated. Card numbers, CVV and bank
credentials are only ever typed on the gateway's page, never in the HMS.
"""

import hashlib
import hmac

from django.conf import settings
from django.urls import reverse


class GatewayUnavailable(Exception):
    """The gateway could not be reached (HTTP 502 in the API); the invoice stays Unpaid."""


def sign(payload):
    """HMAC-SHA256 signature over the fields of a callback."""
    message = "|".join(
        str(payload[key]) for key in ("paymentSessionId", "status", "gatewayRef")
    )
    return hmac.new(
        settings.PAYMENT_GATEWAY_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()


def signature_is_valid(payload):
    try:
        expected = sign(payload)
    except KeyError:
        return False
    return hmac.compare_digest(expected, str(payload.get("signature", "")))


class MockGateway:
    def create_session(self, payment):
        """Return the URL of the gateway's hosted payment page for this payment."""
        if not settings.PAYMENT_GATEWAY_ENABLED:
            raise GatewayUnavailable("The payment gateway is not reachable right now.")
        return reverse("fees:mock_gateway", args=[payment.session_id])


def get_gateway():
    return MockGateway()
