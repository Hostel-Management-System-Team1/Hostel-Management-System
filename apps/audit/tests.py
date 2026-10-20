from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.testutils import PASSWORD, login
from apps.admissions import allocation as allocator
from apps.admissions import services as admissions
from apps.admissions.testutils import (
    allocated_resident,
    application_data,
    approved_application,
    make_block,
    make_resident,
    make_room,
)
from apps.fees import gateway
from apps.fees import services as fees
from apps.fees.models import Invoice

from . import service
from .models import GENESIS_HASH, AuditEntry, AuditImmutable

User = get_user_model()
R = User.Role


def actions():
    return list(AuditEntry.objects.order_by("seq").values_list("action", flat=True))


class RecordTests(TestCase):
    def test_entry_records_actor_action_time_outcome_and_target(self):
        user = make_resident("w1", role=R.WARDEN)
        entry = service.record("allocation.confirmed", target=user, actor=user, detail={"x": 1})
        entry.refresh_from_db()
        self.assertEqual(entry.actor, user)
        self.assertEqual(entry.actor_label, "w1")
        self.assertEqual(entry.action, "allocation.confirmed")
        self.assertEqual(entry.category, "allocation")
        self.assertEqual(entry.outcome, "SUCCESS")
        self.assertIsNotNone(entry.timestamp)
        self.assertEqual((entry.target_type, entry.target_id), ("accounts.user", str(user.pk)))
        self.assertEqual(entry.detail, {"x": 1})

    def test_entries_form_a_hash_chain(self):
        first = service.record("a.one", actor=None)
        second = service.record("a.two", actor=None)
        self.assertEqual((first.seq, second.seq), (1, 2)) if first.seq == 1 else None
        self.assertEqual(first.prev_hash, GENESIS_HASH if first.seq == 1 else first.prev_hash)
        self.assertEqual(second.prev_hash, first.hash)
        self.assertEqual(second.hash, second.compute_hash())
        checked, problems = service.verify_chain()
        self.assertGreaterEqual(checked, 2)
        self.assertEqual(problems, [])

    def test_decimal_detail_survives_the_round_trip(self):
        from decimal import Decimal

        service.record("fee.test", actor=None, detail={"amount": Decimal("73000.00")})
        self.assertEqual(service.verify_chain()[1], [])

    def test_failure_and_denied_outcomes(self):
        service.record("x.fail", actor=None, outcome=AuditEntry.Outcome.FAILURE)
        service.record("x.deny", actor=None, outcome=AuditEntry.Outcome.DENIED)
        self.assertEqual(
            set(AuditEntry.objects.values_list("outcome", flat=True)), {"FAILURE", "DENIED"})


class AppendOnlyTests(TestCase):
    """TC-SEC-04: entries cannot be edited or deleted through the application."""

    def setUp(self):
        self.entry = service.record("a.one", actor=None)

    def test_orm_refuses_edit_and_delete(self):
        self.entry.action = "changed"
        with self.assertRaises(AuditImmutable):
            self.entry.save()
        with self.assertRaises(AuditImmutable):
            self.entry.delete()
        with self.assertRaises(AuditImmutable):
            AuditEntry.objects.all().update(action="changed")
        with self.assertRaises(AuditImmutable):
            AuditEntry.objects.all().delete()
        with self.assertRaises(AuditImmutable):
            AuditEntry.objects.bulk_update([self.entry], ["action"])

    def test_database_refuses_edit_and_delete_even_with_raw_sql(self):
        for sql in ("UPDATE audit_auditentry SET action = 'x'", "DELETE FROM audit_auditentry"):
            with self.subTest(sql=sql), self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql)
        self.assertEqual(AuditEntry.objects.get(pk=self.entry.pk).action, "a.one")

    def test_admin_offers_no_way_to_add_edit_or_delete(self):
        User.objects.create_superuser(username="a1", password=PASSWORD)
        login(self.client, "a1")
        self.assertContains(self.client.get(reverse("admin:audit_auditentry_changelist")),
                            "Integrity check passed")
        self.assertEqual(self.client.get(reverse("admin:audit_auditentry_add")).status_code, 403)
        change = self.client.get(reverse("admin:audit_auditentry_change", args=[self.entry.pk]))
        self.assertNotContains(change, 'name="_save"')  # a read-only view, nothing to submit
        self.assertEqual(self.client.post(
            reverse("admin:audit_auditentry_change", args=[self.entry.pk]), {"action": "x"}
        ).status_code, 403)
        self.assertEqual(self.client.get(
            reverse("admin:audit_auditentry_delete", args=[self.entry.pk])).status_code, 403)
        self.assertEqual(self.client.post(
            reverse("admin:audit_auditentry_delete", args=[self.entry.pk]), {"post": "yes"}
        ).status_code, 403)


class TamperDetectionTests(TestCase):
    """A change made behind the application's back is noticed."""

    def setUp(self):
        for index in range(4):
            service.record(f"a.step{index}", actor=None, detail={"n": index})

    def tamper(self, sql, *params):
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("ALTER TABLE audit_auditentry DISABLE TRIGGER audit_entry_append_only")
            cursor.execute(sql, params)
            cursor.execute("ALTER TABLE audit_auditentry ENABLE TRIGGER audit_entry_append_only")

    def test_untouched_log_verifies(self):
        self.assertEqual(service.verify_chain()[1], [])

    def test_an_edited_entry_is_detected(self):
        self.tamper("UPDATE audit_auditentry SET outcome = 'SUCCESS', action = 'a.forged' "
                    "WHERE seq = (SELECT max(seq) - 1 FROM audit_auditentry)")
        problems = service.verify_chain()[1]
        self.assertTrue(any("contents were changed" in p for p in problems), problems)

    def test_a_deleted_entry_is_detected(self):
        self.tamper("DELETE FROM audit_auditentry WHERE seq = (SELECT max(seq) - 2 FROM "
                    "audit_auditentry)")
        problems = service.verify_chain()[1]
        self.assertTrue(any("missing" in p or "does not follow" in p for p in problems), problems)

    def test_verify_command_reports_ok_and_fails_on_tampering(self):
        out = StringIO()
        call_command("verify_audit", stdout=out)
        self.assertIn("verified", out.getvalue())
        self.tamper("UPDATE audit_auditentry SET action = 'a.forged' WHERE seq = "
                    "(SELECT min(seq) FROM audit_auditentry)")
        with self.assertRaises(CommandError):
            call_command("verify_audit", stdout=StringIO(), stderr=StringIO())

    def test_admin_banner_warns_about_tampering(self):
        User.objects.create_superuser(username="a1", password=PASSWORD)
        login(self.client, "a1")
        self.tamper("UPDATE audit_auditentry SET action = 'a.forged' WHERE seq = "
                    "(SELECT min(seq) FROM audit_auditentry)")
        response = self.client.get(reverse("admin:audit_auditentry_changelist"))
        self.assertContains(response, "has been tampered with")


class WhatIsLoggedTests(TestCase):
    """TC-SEC-04: a sample of each action type appears with actor, action, time and outcome."""

    def setUp(self):
        self.warden = make_resident("w1", role=R.WARDEN)
        self.room = make_room(make_block("Block A", "M"), "101")
        self.room2 = make_room(make_block("Block A", "M"), "102")

    def last(self, action):
        return AuditEntry.objects.filter(action=action).order_by("-seq").first()

    def test_application_decisions(self):
        application = admissions.submit_application(make_resident("r1"), **application_data())
        admissions.decide(application, self.warden, True)
        entry = self.last("application.approved")
        self.assertEqual((entry.actor, entry.outcome), (self.warden, "SUCCESS"))
        self.assertEqual(entry.detail["application"], application.application_number)
        other = admissions.submit_application(make_resident("r2"), **application_data())
        admissions.decide(other, self.warden, False, "Incomplete")
        self.assertTrue(self.last("application.rejected"))

    def test_allocation_invoice_transfer(self):
        allocation = allocated_resident("r1", room=self.room)
        self.assertEqual(self.last("allocation.confirmed").actor, self.warden_or_system())
        invoice = self.last("invoice.raised")
        self.assertEqual(invoice.target_type, "fees.invoice")
        allocator.transfer(allocation, self.room2.beds.first(), "Closer to class", self.warden)
        moved = self.last("allocation.transferred")
        self.assertEqual(moved.actor, self.warden)
        self.assertEqual(moved.detail["reason"], "Closer to class")

    def warden_or_system(self):
        return User.objects.get(role=R.WARDEN)

    def test_refused_allocation_and_transfer_are_logged_as_failures(self):
        resident = make_resident("r1")
        application = approved_application(resident, gender="F")  # no block for women exists
        with self.assertRaises(allocator.NoVacantBed):
            allocator.allocate(application, self.warden)
        failed = self.last("allocation.failed")
        self.assertEqual(failed.outcome, "FAILURE")
        self.assertIn("No vacant bed", failed.detail["reason"])
        allocation = allocated_resident("r2", room=self.room)
        with self.assertRaises(allocator.TransferError):
            allocator.transfer(allocation, self.room2.beds.first(), "", self.warden)
        self.assertEqual(self.last("allocation.transfer_failed").outcome, "FAILURE")

    def test_payments(self):
        allocated_resident("r1", room=self.room)
        invoice = Invoice.objects.get()
        payment = fees.start_payment(invoice, "UPI", "/fees/")[0]
        self.assertEqual(self.last("payment.started").detail["method"], "UPI")
        payload = {"paymentSessionId": payment.session_id, "status": "SUCCESS",
                   "gatewayRef": "GW"}
        payload["signature"] = gateway.sign(payload)
        fees.handle_callback(payload)
        done = self.last("payment.succeeded")
        self.assertEqual(done.actor_label, "payment gateway")
        self.assertEqual(done.detail["amount"], "73000.00")
        bad = dict(payload, signature="x")
        with self.assertRaises(fees.InvalidSignature):
            fees.handle_callback(bad)
        self.assertEqual(self.last("payment.callback_rejected").outcome, "DENIED")

    def test_failed_and_abandoned_payments(self):
        allocated_resident("r1", room=self.room)
        invoice = Invoice.objects.get()
        for status in ("FAILED", "ABANDONED"):
            payment = fees.start_payment(invoice, "CARD")[0]
            payload = {"paymentSessionId": payment.session_id, "status": status,
                       "gatewayRef": "GW"}
            payload["signature"] = gateway.sign(payload)
            fees.handle_callback(payload)
            self.assertEqual(self.last(f"payment.{status.lower()}").outcome, "FAILURE")

    def test_account_management_through_the_admin(self):
        User.objects.create_superuser(username="a1", password=PASSWORD)
        login(self.client, "a1")
        self.client.post(reverse("admin:accounts_user_add"), {
            "username": "w9", "role": "WARDEN", "phone": "9876543210",
            "password1": "Strong-pass-77", "password2": "Strong-pass-77", "_save": "1"})
        created = self.last("account.created")
        self.assertEqual(created.actor.username, "a1")
        self.assertEqual(created.detail["role"], "WARDEN")
        user = User.objects.get(username="w9")
        user.role = R.MAINTENANCE_STAFF
        user.is_active = False
        user.save()
        updated = self.last("account.updated")
        self.assertEqual(updated.detail["changes"]["role"], ["WARDEN", "MAINTENANCE_STAFF"])
        self.assertEqual(updated.detail["changes"]["is_active"], [True, False])
        user.set_password("Another-pass-88")
        user.save()
        self.assertTrue(self.last("account.password_changed"))
        user.delete()
        self.assertEqual(self.last("account.deleted").detail["username"], "w9")

    def test_saving_without_changes_logs_nothing_extra(self):
        user = make_resident("r1")
        before = AuditEntry.objects.count()
        user.first_name = "Aarav"
        user.save()
        self.assertEqual(AuditEntry.objects.count(), before)

    def test_sign_in_and_out_and_failed_attempts(self):
        make_resident("r1")
        self.client.post(reverse("login"), {"username": "r1", "password": "wrong"})
        failed = self.last("auth.login_failed")
        self.assertEqual((failed.outcome, failed.detail["username"]), ("FAILURE", "r1"))
        self.assertNotIn("wrong", str(failed.detail))
        login(self.client, "r1")
        self.assertEqual(self.last("auth.login").actor.username, "r1")
        self.client.post(reverse("logout"))
        self.assertEqual(self.last("auth.logout").actor.username, "r1")

    def test_mfa_events(self):
        from django_otp.oath import TOTP
        from django_otp.plugins.otp_totp.models import TOTPDevice

        self.client.login(username="w1", password="x")  # wrong password: not signed in
        make_resident("w2", role=R.WARDEN)
        self.client.login(username="w2", password=PASSWORD)
        self.client.post(reverse("mfa"), {"token": "123456"})
        self.assertEqual(self.last("auth.mfa_failed").outcome, "FAILURE")
        device = TOTPDevice.objects.get(user__username="w2")
        code = f"{TOTP(device.bin_key, device.step, device.t0, device.digits).token():06d}"
        device.throttling_failure_count = 0
        device.throttling_failure_timestamp = None
        device.save()
        self.client.post(reverse("mfa"), {"token": code})
        self.assertTrue(self.last("auth.mfa_enrolled"))
        self.assertTrue(self.last("auth.mfa_verified"))

    def test_refused_requests_are_logged(self):
        make_resident("r1")
        login(self.client, "r1")
        self.client.get(reverse("admissions:application_list"))
        denied = self.last("access.denied")
        self.assertEqual((denied.outcome, denied.actor.username), ("DENIED", "r1"))
        self.assertEqual(denied.detail["path"], "/applications/")
        self.client.get("/api/v1/users")
        self.assertEqual(self.last("access.denied").detail["path"], "/api/v1/users")

    def test_no_personal_data_in_the_log(self):
        data = application_data(medical_conditions="Severe peanut allergy",
                                guardian_phone="9123456780", full_name="Zed Unusualname")
        resident = make_resident("r1")
        application = admissions.submit_application(resident, **data)
        admissions.decide(application, self.warden, True, "Approved with a private note")
        allocator.allocate(application, self.warden)
        text = " ".join(str(e.detail) + e.target_repr for e in AuditEntry.objects.all())
        for secret in ("peanut", "9123456780", "private note", PASSWORD):
            self.assertNotIn(secret, text)

    def test_every_entry_has_actor_action_timestamp_outcome(self):
        allocated_resident("r1", room=self.room)
        for entry in AuditEntry.objects.all():
            self.assertTrue(entry.actor_label and entry.action and entry.outcome)
            self.assertIsNotNone(entry.timestamp)
