"""The vacating pages a resident and a warden use (HMS-F-062, TC-VAC-01).

test_vacating.py covers the rules in the service layer; these tests drive the same workflow
through the views, including the refusals each page shows.
"""

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.testutils import sign_in
from apps.admissions.testutils import allocated_resident, make_room
from apps.fees.models import Invoice

from . import vacating
from .models import Allocation, NoDuesClearance, VacatingRequest

R = User.Role


class VacatingViewTests(TestCase):
    def setUp(self):
        self.warden = User.objects.create_user("vv_warden", password="x", role=R.WARDEN)
        self.allocation = allocated_resident("vv_resident", room=make_room(number="VV1"))
        self.resident = self.allocation.resident
        self.invoice = Invoice.objects.get(allocation=self.allocation)

    def as_user(self, user):
        self.client.logout()
        sign_in(self.client, user)

    def last_message(self, response):
        return " ".join(str(m) for m in get_messages(response.wsgi_request))

    def submit(self, reason="Graduating"):
        self.as_user(self.resident)
        return self.client.post(reverse("admissions:submit_vacating"), {"reason": reason},
                                follow=True)

    def pay_invoice(self):
        self.invoice.status = Invoice.Status.PAID
        self.invoice.paid_at = timezone.now()
        self.invoice.save(update_fields=["status", "paid_at"])

    def clear_all(self, request):
        self.as_user(self.warden)
        for department in vacating.REQUIRED_DEPARTMENTS:
            self.client.post(reverse("admissions:vacating_clearance", args=[request.pk]),
                             {"department": department, "cleared": "yes", "notes": "ok"})

    # --- the resident's side -------------------------------------------------------------

    def test_resident_submits_and_sees_the_open_request(self):
        response = self.submit()
        self.assertContains(response, "Vacating request submitted")
        request = VacatingRequest.objects.get()
        self.assertEqual(request.clearances.count(), 3)
        self.assertEqual(response.context["open_request"], request)

    def test_a_second_open_request_is_refused(self):
        self.submit()
        response = self.submit("Again")
        self.assertEqual(VacatingRequest.objects.count(), 1)
        self.assertNotContains(response, "Vacating request submitted")

    def test_resident_reads_only_their_own_request(self):
        self.submit()
        request = VacatingRequest.objects.get()
        self.assertEqual(
            self.client.get(reverse("admissions:vacating_detail", args=[request.pk])).status_code,
            200)
        other = allocated_resident("vv_other", room=make_room(number="VV2")).resident
        self.as_user(other)
        self.assertEqual(
            self.client.get(reverse("admissions:vacating_detail", args=[request.pk])).status_code,
            404)

    def test_resident_cannot_use_the_warden_pages(self):
        self.submit()
        request = VacatingRequest.objects.get()
        for name in ("vacating_clearance", "vacating_damage", "vacating_approve",
                     "vacating_complete"):
            response = self.client.post(reverse(f"admissions:{name}", args=[request.pk]))
            self.assertEqual(response.status_code, 403, name)
        self.assertEqual(self.client.get(reverse("admissions:vacating_list")).status_code, 403)

    # --- the warden's side ---------------------------------------------------------------

    def test_warden_list_filters_by_status_and_ignores_unknown_values(self):
        self.submit()
        self.as_user(self.warden)
        listing = self.client.get(reverse("admissions:vacating_list"))
        self.assertEqual(len(listing.context["vacating_requests"]), 1)
        completed = self.client.get(reverse("admissions:vacating_list"), {"status": "COMPLETED"})
        self.assertEqual(len(completed.context["vacating_requests"]), 0)
        junk = self.client.get(reverse("admissions:vacating_list"), {"status": "nonsense"})
        self.assertEqual(junk.context["selected_status"], VacatingRequest.Status.REQUESTED)

    def test_approval_is_refused_until_dues_are_paid_and_clearances_are_in(self):
        self.submit()
        request = VacatingRequest.objects.get()
        self.as_user(self.warden)
        response = self.client.post(reverse("admissions:vacating_approve", args=[request.pk]),
                                    follow=True)
        request.refresh_from_db()
        self.assertEqual(request.status, VacatingRequest.Status.REQUESTED)
        self.assertTrue(self.last_message(response))

    def test_a_clearance_is_refused_while_the_hostel_invoice_is_unpaid(self):
        self.submit()
        request = VacatingRequest.objects.get()
        self.as_user(self.warden)
        self.client.post(reverse("admissions:vacating_clearance", args=[request.pk]),
                         {"department": NoDuesClearance.Department.HOSTEL, "cleared": "yes"})
        clearance = request.clearances.get(department=NoDuesClearance.Department.HOSTEL)
        self.assertNotEqual(clearance.status, NoDuesClearance.Status.CLEARED)

    def test_an_unknown_department_is_refused_with_a_message(self):
        self.submit()
        request = VacatingRequest.objects.get()
        self.as_user(self.warden)
        response = self.client.post(
            reverse("admissions:vacating_clearance", args=[request.pk]),
            {"department": "LIBRARY", "cleared": "yes"}, follow=True)
        self.assertIn("Unknown clearance department", self.last_message(response))

    def test_full_workflow_releases_the_bed_and_reports_the_refund(self):
        self.submit()
        request = VacatingRequest.objects.get()
        self.pay_invoice()
        self.clear_all(request)
        damage = self.client.post(reverse("admissions:vacating_damage", args=[request.pk]),
                                  {"description": "Broken window", "amount": "500"}, follow=True)
        self.assertIn("Damage charge added", self.last_message(damage))
        self.assertEqual(request.damage_charges.count(), 1)

        self.client.post(reverse("admissions:vacating_approve", args=[request.pk]), follow=True)
        request.refresh_from_db()
        self.assertEqual(request.status, VacatingRequest.Status.APPROVED)

        late = self.client.post(reverse("admissions:vacating_damage", args=[request.pk]),
                                {"description": "Door", "amount": "100"}, follow=True)
        self.assertIn("before approval", self.last_message(late))
        self.assertEqual(request.damage_charges.count(), 1)

        done = self.client.post(reverse("admissions:vacating_complete", args=[request.pk]),
                                {"staff_notes": "Keys returned"}, follow=True)
        self.assertIn("Vacating completed", self.last_message(done))
        request.refresh_from_db()
        self.assertEqual(request.status, VacatingRequest.Status.COMPLETED)
        self.allocation.refresh_from_db()
        self.assertNotEqual(self.allocation.status, Allocation.Status.ACTIVE)

    def test_a_bad_damage_amount_is_refused(self):
        self.submit()
        request = VacatingRequest.objects.get()
        self.as_user(self.warden)
        for amount in ("abc", "-5", ""):
            response = self.client.post(
                reverse("admissions:vacating_damage", args=[request.pk]),
                {"description": "Door", "amount": amount}, follow=True)
            self.assertTrue(self.last_message(response), amount)
        self.assertEqual(request.damage_charges.count(), 0)

    def test_completing_before_approval_is_refused(self):
        self.submit()
        request = VacatingRequest.objects.get()
        self.as_user(self.warden)
        response = self.client.post(reverse("admissions:vacating_complete", args=[request.pk]),
                                    follow=True)
        self.assertIn("must be approved", self.last_message(response))
        request.refresh_from_db()
        self.assertEqual(request.status, VacatingRequest.Status.REQUESTED)
