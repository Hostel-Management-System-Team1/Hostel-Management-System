from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from hms.adminfields import money

from .models import FeeHead, Invoice, InvoiceItem, Payment, Receipt


@admin.register(FeeHead)
class FeeHeadAdmin(admin.ModelAdmin):
    """The fee structure: what an invoice for each room type is made of (HMS-F-010)."""

    list_display = ("name", "room_type", "amount_inr", "refundable", "active")
    list_filter = ("room_type", "refundable", "active")
    actions = None
    amount_inr = money("amount")


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    can_delete = False
    readonly_fields = ("description", "amount_inr", "refundable")
    fields = readonly_fields
    amount_inr = money("amount")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "resident", "kind", "total_inr", "due_date", "status")
    list_filter = ("status", "kind")
    search_fields = ("number", "resident__username", "resident__first_name", "resident__last_name")
    inlines = [InvoiceItemInline]
    actions = None
    total_inr = money("total")
    readonly_fields = ("number", "resident", "allocation", "kind", "description", "issue_date",
                       "due_date", "status", "total_inr", "paid_at", "created_at")
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "method", "amount_inr", "status", "gateway_ref", "created_at")
    list_filter = ("status", "method")
    search_fields = ("invoice__number", "gateway_ref", "session_id")
    actions = None
    amount_inr = money("amount")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ("number", "invoice", "amount_inr", "issued_at", "pdf")
    search_fields = ("number", "invoice__number")
    actions = None
    amount_inr = money("amount")

    @admin.display(description="PDF")
    def pdf(self, obj):
        return format_html('<a href="{}">Download</a>', reverse("fees:receipt_pdf", args=[obj.pk]))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
