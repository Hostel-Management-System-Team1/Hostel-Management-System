import time
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.testutils import PASSWORD, login
from apps.admissions.testutils import allocated_resident, make_block, make_room

from . import gateway, services
from .models import FeeHead, Invoice, Payment, Receipt

User = get_user_model()
R = User.Role


def callback(payment, status="SUCCESS", ref="GW-1", **overrides):
    payload = {"paymentSessionId": payment.session_id, "status": status, "gatewayRef": ref}
    payload["signature"] = gateway.sign(payload)
    payload.update(overrides)
    return payload


class InvoiceGenerationTests(TestCase):
    """TC-FEE-01: the invoice total equals the sum of the fee heads for the room type."""

    def setUp(self):
        User.objects.create_user(username="warden0", password=PASSWORD, role=R.WARDEN)

    def test_invoice_is_raised_when_an_allocation_is_confirmed(self):
        allocation = allocated_resident("r1", room=make_room(room_type="DOUBLE"))
        invoice = Invoice.objects.get(allocation=allocation)
        self.assertEqual(invoice.resident, allocation.resident)
        self.assertEqual(invoice.status, Invoice.Status.UNPAID)
        self.assertRegex(invoice.number, r"^INV-\d{4}-\d{6}$")
        self.assertEqual(invoice.due_date, timezone.localdate() + timedelta(days=15))

    def test_total_is_the_sum_of_the_items_for_every_room_type(self):
        for number, room_type in (("1", "SINGLE"), ("2", "DOUBLE"), ("3", "TRIPLE")):
            allocation = allocated_resident(
                f"r{number}", room=make_room(number=number, room_type=room_type))
            invoice = Invoice.objects.get(allocation=allocation)
            heads = FeeHead.objects.filter(room_type=room_type, active=True)
            self.assertEqual(invoice.total, sum(h.amount for h in heads))
            self.assertEqual(invoice.total, sum(i.amount for i in invoice.items.all()))
            self.assertEqual(
                {i.description for i in invoice.items.all()},
                {"Room rent", "Mess advance", "Security deposit", "Maintenance"},
            )

    def test_security_deposit_is_marked_refundable(self):
        allocation = allocated_resident("r1", room=make_room())
        invoice = Invoice.objects.get(allocation=allocation)
        self.assertEqual(invoice.refundable_total, Decimal("10000.00"))

    def test_inactive_fee_heads_are_left_out(self):
        FeeHead.objects.filter(room_type="DOUBLE", name="Maintenance").update(active=False)
        allocation = allocated_resident("r1", room=make_room())
        invoice = Invoice.objects.get(allocation=allocation)
        self.assertNotIn("Maintenance", [i.description for i in invoice.items.all()])
        self.assertEqual(invoice.total, Decimal("70000.00"))

    def test_changing_the_fee_structure_does_not_change_an_existing_invoice(self):
        allocation = allocated_resident("r1", room=make_room())
        invoice = Invoice.objects.get(allocation=allocation)
        FeeHead.objects.filter(room_type="DOUBLE", name="Room rent").update(amount=1)
        invoice.refresh_from_db()
        self.assertEqual(invoice.total, Decimal("73000.00"))

    def test_no_fee_structure_means_no_invoice_but_the_allocation_stands(self):
        FeeHead.objects.filter(room_type="DOUBLE").delete()
        allocation = allocated_resident("r1", room=make_room())
        self.assertEqual(allocation.status, "ACTIVE")
        self.assertFalse(Invoice.objects.exists())

    def test_generating_twice_gives_one_invoice(self):
        allocation = allocated_resident("r1", room=make_room())
        again = services.generate_invoice(allocation)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(again.pk, Invoice.objects.get().pk)


class PaymentFlowTests(TestCase):
    """TC-FEE-02: success marks the invoice Paid; failed or abandoned leaves it Unpaid."""

    def setUp(self):
        User.objects.create_user(username="warden0", password=PASSWORD, role=R.WARDEN)
        self.allocation = allocated_resident("r1", room=make_room())
        self.invoice = Invoice.objects.get(allocation=self.allocation)

    def start(self):
        return services.start_payment(self.invoice, "UPI", "/fees/")[0]

    def test_starting_a_payment_changes_nothing_on_the_invoice(self):
        payment, url = services.start_payment(self.invoice, "CARD", "/fees/")
        self.assertEqual(payment.status, Payment.Status.INITIATED)
        self.assertEqual(payment.amount, self.invoice.total)
        self.assertEqual(url, reverse("fees:mock_gateway", args=[payment.session_id]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.UNPAID)

    def test_successful_callback_marks_the_invoice_paid_and_issues_a_receipt(self):
        payment = self.start()
        services.handle_callback(callback(payment))
        self.invoice.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertIsNotNone(self.invoice.paid_at)
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertEqual(payment.gateway_ref, "GW-1")
        receipt = Receipt.objects.get(invoice=self.invoice)
        self.assertEqual(receipt.amount, self.invoice.total)
        self.assertRegex(receipt.number, r"^RCT-\d{4}-\d{6}$")

    def test_failed_payment_leaves_the_invoice_unpaid(self):
        payment = self.start()
        services.handle_callback(callback(payment, "FAILED"))
        self.invoice.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.UNPAID)
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertFalse(Receipt.objects.exists())

    def test_abandoned_payment_leaves_the_invoice_unpaid(self):
        payment = self.start()
        services.handle_callback(callback(payment, "ABANDONED"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.UNPAID)
        self.assertEqual(Payment.objects.get().status, Payment.Status.ABANDONED)

    def test_a_failed_attempt_can_be_followed_by_a_successful_one(self):
        services.handle_callback(callback(self.start(), "FAILED"))
        services.handle_callback(callback(self.start(), "SUCCESS"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertEqual(Receipt.objects.count(), 1)

    def test_a_repeated_callback_changes_nothing(self):
        payment = self.start()
        services.handle_callback(callback(payment))
        services.handle_callback(callback(payment))
        services.handle_callback(callback(payment, "FAILED"))
        self.assertEqual(Receipt.objects.count(), 1)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)

    def test_a_second_success_for_a_paid_invoice_is_flagged_not_receipted(self):
        first, second = self.start(), self.start()
        services.handle_callback(callback(first))
        services.handle_callback(callback(second, ref="GW-2"))
        second.refresh_from_db()
        self.assertEqual(second.status, Payment.Status.DUPLICATE)
        self.assertEqual(Receipt.objects.count(), 1)

    def test_bad_signature_is_refused_and_changes_nothing(self):
        payment = self.start()
        with self.assertRaises(services.InvalidSignature):
            services.handle_callback(callback(payment, signature="0" * 64))
        with self.assertRaises(services.InvalidSignature):
            services.handle_callback({"paymentSessionId": payment.session_id})
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.INITIATED)

    def test_a_tampered_status_is_refused(self):
        payment = self.start()
        payload = callback(payment, "FAILED")
        payload["status"] = "SUCCESS"  # signed as FAILED, changed in transit
        with self.assertRaises(services.InvalidSignature):
            services.handle_callback(payload)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.UNPAID)

    def test_unknown_session_is_refused(self):
        payload = {"paymentSessionId": "nope", "status": "SUCCESS", "gatewayRef": "x"}
        payload["signature"] = gateway.sign(payload)
        with self.assertRaises(services.UnknownPaymentSession):
            services.handle_callback(payload)

    def test_paid_invoice_cannot_be_paid_again(self):
        services.handle_callback(callback(self.start()))
        self.invoice.refresh_from_db()
        with self.assertRaises(services.InvoiceAlreadyPaid):
            services.start_payment(self.invoice, "CARD")

    @override_settings(PAYMENT_GATEWAY_ENABLED=False)
    def test_gateway_down_leaves_the_invoice_unpaid_and_creates_no_payment(self):
        with self.assertRaises(gateway.GatewayUnavailable):
            services.start_payment(self.invoice, "CARD")
        self.assertFalse(Payment.objects.exists())
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.UNPAID)

    def test_stale_sessions_are_abandoned(self):
        payment = self.start()
        Payment.objects.update(created_at=timezone.now() - timedelta(minutes=31))
        self.assertEqual(services.abandon_stale_payments(), 1)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.ABANDONED)


class NoCardDataTests(TestCase):
    """HMS-SR-005 / TC-SEC-05: nothing that looks like card or bank data is stored."""

    def test_no_model_has_a_card_or_bank_field(self):
        from django.apps import apps

        forbidden = ("card", "cvv", "cvc", "pan", "account_number", "ifsc", "bank", "expiry")
        for model in apps.get_app_config("fees").get_models():
            for field in model._meta.get_fields():
                name = field.name.lower()
                for word in forbidden:
                    self.assertNotIn(word, name, f"{model.__name__}.{field.name}")

    def test_card_details_posted_to_the_gateway_page_are_not_kept(self):
        User.objects.create_user(username="warden0", password=PASSWORD, role=R.WARDEN)
        allocation = allocated_resident("r1", room=make_room())
        invoice = Invoice.objects.get(allocation=allocation)
        payment, _ = services.start_payment(invoice, "CARD", "/fees/")
        self.client.post(reverse("fees:mock_gateway", args=[payment.session_id]), {
            "outcome": "pay", "card_number": "4111111111111111", "cvv": "123",
        })
        stored = " ".join(
            str(value) for p in Payment.objects.values() for value in p.values())
        self.assertNotIn("4111111111111111", stored)
        self.assertNotIn("123", payment.gateway_ref)


class ResidentViewTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="warden0", password=PASSWORD, role=R.WARDEN)
        self.allocation = allocated_resident("r1", room=make_room(room_type="DOUBLE"))
        self.invoice = Invoice.objects.get(allocation=self.allocation)
        login(self.client, "r1")

    def test_invoice_list_and_detail_show_the_itemised_invoice(self):
        response = self.client.get(reverse("fees:invoice_list"))
        self.assertContains(response, self.invoice.number)
        self.assertContains(response, "₹73,000.00")
        detail = self.client.get(reverse("fees:invoice_detail", args=[self.invoice.pk]))
        for item in ("Room rent", "Mess advance", "Security deposit", "Maintenance"):
            self.assertContains(detail, item)
        self.assertContains(detail, "Refundable when you vacate")
        self.assertContains(detail, "Pay online")

    def test_empty_list_before_allocation(self):
        User.objects.create_user(username="r2", password=PASSWORD)
        self.client.logout()
        login(self.client, "r2")
        self.assertContains(self.client.get(reverse("fees:invoice_list")), "No invoices yet")

    def pay(self, outcome):
        response = self.client.post(
            reverse("fees:invoice_pay", args=[self.invoice.pk]), {"method": "UPI"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/pay/gateway/", response["Location"])
        return self.client.post(response["Location"], {"outcome": outcome}, follow=True)

    def test_paying_through_the_gateway_page(self):
        response = self.pay("pay")
        self.assertRedirects(response, reverse("fees:invoice_detail", args=[self.invoice.pk]))
        self.assertContains(response, "Payment received")
        self.assertContains(response, "Download receipt")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)

    def test_failed_payment_message_and_invoice_still_unpaid(self):
        response = self.pay("fail")
        self.assertContains(response, "The payment failed")
        self.assertContains(response, "Pay online")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.UNPAID)

    def test_cancelled_payment_message_and_invoice_still_unpaid(self):
        response = self.pay("cancel")
        self.assertContains(response, "cancelled")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.UNPAID)

    def test_payment_method_is_required(self):
        response = self.client.post(
            reverse("fees:invoice_pay", args=[self.invoice.pk]), {"method": "CASH"}, follow=True)
        self.assertContains(response, "Choose how you want to pay")
        self.assertFalse(Payment.objects.exists())

    @override_settings(PAYMENT_GATEWAY_ENABLED=False)
    def test_gateway_outage_is_explained_and_nothing_is_charged(self):
        response = self.client.post(
            reverse("fees:invoice_pay", args=[self.invoice.pk]), {"method": "UPI"}, follow=True)
        self.assertContains(response, "Nothing was charged")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.UNPAID)

    def test_return_url_cannot_send_the_resident_off_site(self):
        payment, _ = services.start_payment(self.invoice, "UPI", "https://evil.example/")
        response = self.client.post(
            reverse("fees:mock_gateway", args=[payment.session_id]), {"outcome": "cancel"})
        self.assertEqual(response["Location"], "/")

    def test_gateway_page_needs_post_to_act(self):
        payment, _ = services.start_payment(self.invoice, "UPI", "/fees/")
        page = self.client.get(reverse("fees:mock_gateway", args=[payment.session_id]))
        self.assertContains(page, "asks for no card or bank details")
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.INITIATED)

    def test_another_resident_cannot_see_or_pay_the_invoice(self):
        User.objects.create_user(username="r2", password=PASSWORD)
        self.client.logout()
        login(self.client, "r2")
        detail = self.client.get(reverse("fees:invoice_detail", args=[self.invoice.pk]))
        self.assertEqual(detail.status_code, 403)
        pay = self.client.post(
            reverse("fees:invoice_pay", args=[self.invoice.pk]), {"method": "UPI"})
        self.assertEqual(pay.status_code, 403)

    def test_dashboard_shows_outstanding_fees(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Outstanding")
        self.assertContains(response, "₹73,000.00")


class ReceiptTests(TestCase):
    """TC-FEE-03: a unique receipt number and a PDF straight after payment."""

    def setUp(self):
        User.objects.create_user(username="warden0", password=PASSWORD, role=R.WARDEN)
        self.room = make_room(room_type="DOUBLE")
        self.allocation = allocated_resident("r1", room=self.room)
        self.invoice = Invoice.objects.get(allocation=self.allocation)
        payment = services.start_payment(self.invoice, "CARD", "/fees/")[0]
        services.handle_callback(callback(payment))
        self.receipt = Receipt.objects.get()

    def test_pdf_is_available_immediately_after_payment(self):
        login(self.client, "r1")
        started = time.monotonic()
        response = self.client.get(reverse("fees:receipt_pdf", args=[self.receipt.pk]))
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        content = b"".join(response.streaming_content)
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertIn(self.receipt.number, response["Content-Disposition"])

    def test_receipt_numbers_are_unique(self):
        second = allocated_resident("r2", room=self.room)
        invoice = Invoice.objects.get(allocation=second)
        payment = services.start_payment(invoice, "UPI", "/fees/")[0]
        services.handle_callback(callback(payment, ref="GW-2"))
        numbers = list(Receipt.objects.values_list("number", flat=True))
        self.assertEqual(len(numbers), 2)
        self.assertEqual(len(set(numbers)), 2)

    def test_only_the_owner_and_administrators_can_download(self):
        url = reverse("fees:receipt_pdf", args=[self.receipt.pk])
        User.objects.create_user(username="r2", password=PASSWORD)
        User.objects.create_superuser(username="a1", password=PASSWORD)
        for username, status in (("r2", 403), ("warden0", 403), ("a1", 200), ("r1", 200)):
            self.client.logout()
            login(self.client, username)
            self.assertEqual(self.client.get(url).status_code, status, username)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)


class FeesApiTests(TestCase):
    """SAD 4.3: POST /api/v1/invoices/{id}/payments and POST /api/v1/payments/callback."""

    def setUp(self):
        User.objects.create_user(username="warden0", password=PASSWORD, role=R.WARDEN)
        self.allocation = allocated_resident("r1", room=make_room())
        self.invoice = Invoice.objects.get(allocation=self.allocation)
        login(self.client, "r1")

    def pay(self, pk=None, **body):
        return self.client.post(
            f"/api/v1/invoices/{pk or self.invoice.pk}/payments",
            {"method": "UPI", "returnUrl": "/fees/", **body}, content_type="application/json")

    def test_start_payment(self):
        response = self.pay()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["redirectUrl"].endswith(body["paymentSessionId"] + "/"))

    def test_unknown_or_foreign_invoice_is_404(self):
        self.assertEqual(self.pay(pk=99999).status_code, 404)
        User.objects.create_user(username="r2", password=PASSWORD)
        self.client.logout()
        login(self.client, "r2")
        self.assertEqual(self.pay().status_code, 404)

    def test_paid_invoice_is_409(self):
        payment = services.start_payment(self.invoice, "UPI")[0]
        services.handle_callback(callback(payment))
        self.assertEqual(self.pay().status_code, 409)

    @override_settings(PAYMENT_GATEWAY_ENABLED=False)
    def test_gateway_down_is_502(self):
        self.assertEqual(self.pay().status_code, 502)
        self.assertEqual(Payment.objects.count(), 0)

    def test_invalid_method_is_400(self):
        self.assertEqual(self.pay(method="CASH").status_code, 400)

    def test_webhook_marks_the_invoice_paid_without_a_login(self):
        payment = services.start_payment(self.invoice, "UPI")[0]
        self.client.logout()
        response = self.client.post(
            "/api/v1/payments/callback", callback(payment), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"received": True})
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)

    def test_webhook_with_a_bad_signature_is_400(self):
        payment = services.start_payment(self.invoice, "UPI")[0]
        response = self.client.post(
            "/api/v1/payments/callback", callback(payment, signature="bad"),
            content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid signature", response.json()["message"])
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.UNPAID)

    def test_webhook_for_an_unknown_session_is_404(self):
        payload = {"paymentSessionId": "nope", "status": "SUCCESS", "gatewayRef": "x"}
        payload["signature"] = gateway.sign(payload)
        response = self.client.post(
            "/api/v1/payments/callback", payload, content_type="application/json")
        self.assertEqual(response.status_code, 404)


class FeeAdminTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="a1", password=PASSWORD)
        login(self.client, "a1")

    def test_administrator_edits_the_fee_structure(self):
        head = FeeHead.objects.get(room_type="DOUBLE", name="Room rent")
        response = self.client.post(
            reverse("admin:fees_feehead_change", args=[head.pk]),
            {"name": "Room rent", "room_type": "DOUBLE", "amount": "50000.00", "active": "on",
             "_save": "Save"})
        self.assertEqual(response.status_code, 302)
        head.refresh_from_db()
        self.assertEqual(head.amount, Decimal("50000.00"))

    def test_invoices_are_listed_but_not_editable(self):
        User.objects.create_user(username="warden0", password=PASSWORD, role=R.WARDEN)
        allocated_resident("r1", room=make_room())
        invoice = Invoice.objects.get()
        self.assertContains(self.client.get(reverse("admin:fees_invoice_changelist")),
                            invoice.number)
        page = self.client.get(reverse("admin:fees_invoice_change", args=[invoice.pk]))
        self.assertNotContains(page, 'name="_save"')
        self.assertEqual(self.client.post(
            reverse("admin:fees_invoice_delete", args=[invoice.pk]), {"post": "yes"}).status_code,
            403)

    def test_fee_structure_and_fees_appear_in_the_admin_navigation(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Fee structure")
        self.assertContains(response, reverse("admin:fees_invoice_changelist"))
        make_block()


class CommandTests(TestCase):
    def test_expire_payments_command(self):
        from io import StringIO

        from django.core.management import call_command

        User.objects.create_user(username="warden0", password=PASSWORD, role=R.WARDEN)
        allocation = allocated_resident("r1", room=make_room())
        services.start_payment(Invoice.objects.get(allocation=allocation), "UPI")
        Payment.objects.update(created_at=timezone.now() - timedelta(hours=1))
        out = StringIO()
        call_command("expire_payments", stdout=out)
        self.assertIn("1 stale", out.getvalue())

    def test_generate_missing_invoices_after_a_fee_structure_is_added(self):
        from io import StringIO

        from django.core.management import call_command

        User.objects.create_user(username="warden0", password=PASSWORD, role=R.WARDEN)
        saved = list(FeeHead.objects.filter(room_type="TRIPLE").values())
        FeeHead.objects.filter(room_type="TRIPLE").delete()
        allocated_resident("r1", room=make_room(room_type="TRIPLE"))
        self.assertFalse(Invoice.objects.exists())
        FeeHead.objects.bulk_create([FeeHead(**row) for row in saved])
        out = StringIO()
        call_command("generate_missing_invoices", stdout=out)
        self.assertIn("1 invoices raised", out.getvalue())
        self.assertEqual(Invoice.objects.count(), 1)
