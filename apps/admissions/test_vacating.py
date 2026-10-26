"""Tests for the hostel vacating workflow (HMS-F-062)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.testutils import PASSWORD
from apps.admissions.testutils import allocated_resident, make_room
from apps.fees.models import Invoice

from . import vacating
from .models import Allocation, Bed, NoDuesClearance, VacatingRequest


class VacatingServiceTests(TestCase):
    def setUp(self):
        self.warden = User.objects.create_user(
            username="warden0",
            password=PASSWORD,
            role=User.Role.WARDEN,
        )
        self.allocation = allocated_resident(
            "resident1",
            room=make_room(number="V101"),
        )
        self.resident = self.allocation.resident
        self.invoice = Invoice.objects.get(allocation=self.allocation)

    def submit_request(self):
        return vacating.submit_vacating_request(
            self.resident,
            "Leaving the hostel",
        )

    def mark_invoice_paid(self):
        self.invoice.status = Invoice.Status.PAID
        self.invoice.paid_at = timezone.now()
        self.invoice.save(update_fields=["status", "paid_at"])

    def clear_department(self, request, department):
        return vacating.record_clearance(
            request,
            department,
            self.warden,
            True,
            "Verified by staff",
        )

    def clear_all_departments(self, request):
        for department in vacating.REQUIRED_DEPARTMENTS:
            self.clear_department(request, department)

    def approve(self, request):
        return vacating.approve_vacating_request(request, self.warden)

    def prepare_for_approval(self, request):
        self.mark_invoice_paid()
        self.clear_all_departments(request)

    def test_resident_can_submit_request_with_three_pending_clearances(self):
        request = self.submit_request()

        self.assertEqual(request.resident, self.resident)
        self.assertEqual(request.allocation, self.allocation)
        self.assertEqual(request.status, VacatingRequest.Status.REQUESTED)
        self.assertEqual(request.clearances.count(), 3)
        self.assertEqual(
            set(request.clearances.values_list("department", flat=True)),
            set(vacating.REQUIRED_DEPARTMENTS),
        )
        self.assertEqual(
            request.clearances.filter(status=NoDuesClearance.Status.PENDING).count(),
            3,
        )

    def test_duplicate_open_request_is_rejected(self):
        self.submit_request()

        with self.assertRaises(ValidationError):
            self.submit_request()

    def test_unpaid_invoice_prevents_hostel_clearance(self):
        request = self.submit_request()

        with self.assertRaises(ValidationError):
            self.clear_department(
                request,
                NoDuesClearance.Department.HOSTEL,
            )

        self.assertEqual(
            request.clearances.get(department=NoDuesClearance.Department.HOSTEL).status,
            NoDuesClearance.Status.PENDING,
        )

    def test_pending_clearance_prevents_approval(self):
        request = self.submit_request()
        self.mark_invoice_paid()

        self.clear_department(
            request,
            NoDuesClearance.Department.HOSTEL,
        )
        self.clear_department(
            request,
            NoDuesClearance.Department.MESS,
        )

        with self.assertRaises(ValidationError):
            self.approve(request)

        request.refresh_from_db()
        self.allocation.refresh_from_db()
        self.allocation.bed.refresh_from_db()

        self.assertEqual(request.status, VacatingRequest.Status.REQUESTED)
        self.assertEqual(self.allocation.status, Allocation.Status.ACTIVE)
        self.assertEqual(self.allocation.bed.status, Bed.Status.OCCUPIED)

    def test_unpaid_invoice_prevents_approval(self):
        request = self.submit_request()

        # Simulate staff having recorded clearances before a later
        # invoice check identifies an outstanding balance.
        request.clearances.update(status=NoDuesClearance.Status.CLEARED)

        with self.assertRaises(ValidationError):
            self.approve(request)

        request.refresh_from_db()
        self.allocation.refresh_from_db()
        self.allocation.bed.refresh_from_db()

        self.assertEqual(request.status, VacatingRequest.Status.REQUESTED)
        self.assertEqual(self.allocation.status, Allocation.Status.ACTIVE)
        self.assertEqual(self.allocation.bed.status, Bed.Status.OCCUPIED)

    def test_request_must_be_approved_before_completion(self):
        request = self.submit_request()
        self.prepare_for_approval(request)

        with self.assertRaises(ValidationError):
            vacating.complete_vacating(request, self.warden)

        request.refresh_from_db()
        self.allocation.refresh_from_db()
        self.allocation.bed.refresh_from_db()

        self.assertEqual(request.status, VacatingRequest.Status.REQUESTED)
        self.assertEqual(self.allocation.status, Allocation.Status.ACTIVE)
        self.assertEqual(self.allocation.bed.status, Bed.Status.OCCUPIED)

    def test_successful_completion_records_refund_and_releases_bed(self):
        request = self.submit_request()
        self.prepare_for_approval(request)

        vacating.add_damage_charge(
            request,
            self.warden,
            "Damaged desk",
            Decimal("1500.00"),
        )

        approved = self.approve(request)

        self.assertEqual(approved.status, VacatingRequest.Status.APPROVED)
        self.assertEqual(approved.approved_by, self.warden)
        self.assertIsNotNone(approved.approved_at)

        completed = vacating.complete_vacating(
            approved,
            self.warden,
            "Room inspected",
        )

        completed.refresh_from_db()
        self.allocation.refresh_from_db()
        self.allocation.bed.refresh_from_db()

        self.assertEqual(completed.status, VacatingRequest.Status.COMPLETED)
        self.assertIsNotNone(completed.vacated_at)
        self.assertEqual(completed.security_deposit, Decimal("10000.00"))
        self.assertEqual(completed.outstanding_dues, Decimal("0.00"))
        self.assertEqual(completed.damage_deduction, Decimal("1500.00"))
        self.assertEqual(completed.refund_amount, Decimal("8500.00"))
        self.assertEqual(completed.staff_notes, "Room inspected")

        self.assertEqual(self.allocation.status, Allocation.Status.ENDED)
        self.assertEqual(self.allocation.bed.status, Bed.Status.VACANT)

    def test_refund_never_becomes_negative(self):
        request = self.submit_request()
        self.prepare_for_approval(request)

        vacating.add_damage_charge(
            request,
            self.warden,
            "Major damage",
            Decimal("15000.00"),
        )

        self.approve(request)
        completed = vacating.complete_vacating(request, self.warden)

        self.assertEqual(completed.security_deposit, Decimal("10000.00"))
        self.assertEqual(completed.damage_deduction, Decimal("15000.00"))
        self.assertEqual(completed.refund_amount, Decimal("0.00"))

    def test_negative_damage_charge_is_rejected(self):
        request = self.submit_request()

        with self.assertRaises(ValidationError):
            vacating.add_damage_charge(
                request,
                self.warden,
                "Invalid charge",
                Decimal("-1.00"),
            )

    def test_completed_request_cannot_be_completed_again(self):
        request = self.submit_request()
        self.prepare_for_approval(request)
        self.approve(request)

        vacating.complete_vacating(request, self.warden)

        with self.assertRaises(ValidationError):
            vacating.complete_vacating(request, self.warden)
