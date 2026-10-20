from django.urls import path

from . import views

app_name = "fees"

urlpatterns = [
    path("fees/", views.invoice_list, name="invoice_list"),
    path("fees/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("fees/<int:pk>/pay/", views.invoice_pay, name="invoice_pay"),
    path("fees/receipts/<int:pk>/pdf/", views.receipt_download, name="receipt_pdf"),
    path("pay/gateway/<str:session_id>/", views.mock_gateway, name="mock_gateway"),
]
