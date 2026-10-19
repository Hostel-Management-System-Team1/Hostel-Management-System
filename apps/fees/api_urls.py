from django.urls import path

from . import api

urlpatterns = [
    path("invoices/<int:pk>/payments", api.PaymentStartView.as_view(), name="api-pay"),
    path("payments/callback", api.PaymentCallbackView.as_view(), name="api-payment-callback"),
]
