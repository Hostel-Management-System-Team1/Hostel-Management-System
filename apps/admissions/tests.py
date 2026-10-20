from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.testutils import PASSWORD, login

from . import services
from .models import Application, Block

User = get_user_model()
R = User.Role


def application_data(**overrides):
    data = {
        "enrolment_number": "PES2UG24CS500",
        "full_name": "Aarav Sharma",
        "date_of_birth": date(2006, 5, 14),
        "gender": "M",
        "phone": "9876543210",
        "email": "aarav@example.edu",
        "address": "12 MG Road, Bengaluru",
        "programme": "B.Tech Computer Science",
        "year_of_study": 1,
        "cgpa": "8.50",
        "guardian_name": "Rakesh Sharma",
        "guardian_relation": "Father",
        "guardian_phone": "9876500000",
        "guardian_email": "rakesh@example.com",
        "blood_group": "O+",
        "medical_conditions": "Asthma",
        "room_type": "DOUBLE",
    }
    data.update(overrides)
    return data


def form_data(**overrides):
    data = application_data(**overrides)
    data["date_of_birth"] = data["date_of_birth"].isoformat()
    return data


class SubmitApplicationTests(TestCase):
    """TC-ADM-01: a valid application gets a number; a duplicate is rejected."""

    def setUp(self):
        self.boys = Block.objects.create(name="Block A", gender="M")
        self.girls = Block.objects.create(name="Block B", gender="F")
        self.resident = User.objects.create_user(username="r1", password=PASSWORD)
        self.other = User.objects.create_user(username="r2", password=PASSWORD)

    def test_valid_application_gets_a_number(self):
        application = services.submit_application(self.resident, **application_data())
        self.assertRegex(application.application_number, r"^HMS-2026-\d{5}$")
        self.assertEqual(application.status, Application.Status.SUBMITTED)
        self.assertEqual(application.academic_session, "2026-27")

    def test_enrolment_number_is_normalised(self):
        application = services.submit_application(
            self.resident, **application_data(enrolment_number=" pes2ug24cs 500 ")
        )
        self.assertEqual(application.enrolment_number, "PES2UG24CS500")

    def test_duplicate_enrolment_number_is_rejected_with_a_message(self):
        first = services.submit_application(self.resident, **application_data())
        with self.assertRaises(services.DuplicateApplication) as caught:
            services.submit_application(self.other, **application_data())
        self.assertIn(first.application_number, str(caught.exception))
        self.assertIn("PES2UG24CS500", str(caught.exception))
        self.assertEqual(Application.objects.count(), 1)

    def test_same_enrolment_number_is_fine_in_another_session(self):
        services.submit_application(self.resident, **application_data())
        with override_settings(ACADEMIC_SESSION="2027-28"):
            again = services.submit_application(self.resident, **application_data())
        self.assertEqual(again.academic_session, "2027-28")

    def test_one_application_per_resident_per_session(self):
        services.submit_application(self.resident, **application_data())
        with self.assertRaises(services.DuplicateApplication):
            services.submit_application(
                self.resident, **application_data(enrolment_number="PES2UG24CS501")
            )

    def test_no_number_is_issued_when_validation_fails(self):
        from django.core.exceptions import ValidationError

        for bad in (
            {"phone": "12345"},
            {"full_name": "<script>alert(1)</script>"},
            {"address": "<b>x</b>"},
            {"cgpa": "11"},
            {"year_of_study": 9},
            {"date_of_birth": date(2030, 1, 1)},
            {"enrolment_number": "x"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                services.submit_application(self.resident, **application_data(**bad))
        self.assertEqual(Application.objects.count(), 0)

    def test_block_for_the_other_gender_is_refused(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError) as caught:
            services.submit_application(
                self.resident, **application_data(preferred_block=self.girls)
            )
        self.assertIn("preferred_block", caught.exception.message_dict)
        services.submit_application(self.resident, **application_data(preferred_block=self.boys))

    @override_settings(HMS_ERP_ADAPTER="apps.admissions.tests.NoSuchStudentERP")
    def test_unknown_student_is_refused(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            services.submit_application(self.resident, **application_data())


class NoSuchStudentERP:
    def lookup(self, enrolment_number):
        return None


class ApplyViewTests(TestCase):
    def setUp(self):
        Block.objects.create(name="Block A", gender="M")
        self.resident = User.objects.create_user(username="r1", password=PASSWORD)
        login(self.client, "r1")

    def test_form_page_lists_every_section(self):
        response = self.client.get(reverse("admissions:apply"))
        for heading in ("Personal details", "Academic details", "Guardian details",
                        "Medical details", "Room preference"):
            self.assertContains(response, heading)

    def test_resident_submits_and_sees_the_status_page(self):
        response = self.client.post(reverse("admissions:apply"), form_data(), follow=True)
        self.assertRedirects(response, reverse("admissions:my_application"))
        self.assertContains(response, "HMS-2026-")
        self.assertContains(response, "Waiting for the warden")

    def test_second_visit_goes_to_the_status_page(self):
        self.client.post(reverse("admissions:apply"), form_data())
        response = self.client.get(reverse("admissions:apply"))
        self.assertRedirects(response, reverse("admissions:my_application"))

    def test_status_page_without_application_goes_to_the_form(self):
        response = self.client.get(reverse("admissions:my_application"))
        self.assertRedirects(response, reverse("admissions:apply"))

    def test_invalid_form_shows_errors_and_creates_nothing(self):
        response = self.client.post(reverse("admissions:apply"), form_data(phone="abc"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter 10 to 15 digits")
        self.assertContains(response, 'aria-invalid="true"')
        self.assertEqual(Application.objects.count(), 0)

    def test_duplicate_shows_an_explanatory_message(self):
        other = User.objects.create_user(username="r2", password=PASSWORD)
        services.submit_application(other, **application_data())
        response = self.client.post(reverse("admissions:apply"), form_data())
        self.assertContains(response, "already exists")
        self.assertEqual(Application.objects.count(), 1)

    def test_markup_in_text_is_never_stored_or_shown_raw(self):
        response = self.client.post(
            reverse("admissions:apply"), form_data(address="<script>alert(1)</script>")
        )
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertEqual(Application.objects.count(), 0)


class WardenReviewTests(TestCase):
    def setUp(self):
        self.resident = User.objects.create_user(username="r1", password=PASSWORD)
        self.warden = User.objects.create_user(
            username="w1", password=PASSWORD, role=R.WARDEN, first_name="Wendy"
        )
        self.application = services.submit_application(self.resident, **application_data())
        login(self.client, "w1")

    def test_waiting_applications_are_listed_with_counts(self):
        response = self.client.get(reverse("admissions:application_list"))
        self.assertContains(response, "Aarav Sharma")
        waiting = next(t for t in response.context["tabs"] if t["value"] == "SUBMITTED")
        self.assertEqual(waiting["count"], 1)

    def test_other_tabs_show_other_statuses(self):
        response = self.client.get(reverse("admissions:application_list"), {"status": "APPROVED"})
        self.assertNotContains(response, "Aarav Sharma")

    def test_detail_shows_everything_the_warden_needs(self):
        response = self.client.get(
            reverse("admissions:application_detail", args=[self.application.pk])
        )
        self.assertContains(response, "Rakesh Sharma")
        self.assertContains(response, "Asthma")

    def test_dashboard_lists_pending_applications(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Pending applications")
        self.assertContains(response, "Aarav Sharma")

    def test_approve(self):
        url = reverse("admissions:application_decide", args=[self.application.pk])
        self.client.post(url, {"action": "approve", "note": "Eligible"})
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.APPROVED)
        self.assertEqual(self.application.decided_by, self.warden)
        self.assertIsNotNone(self.application.decided_at)

    def test_rejection_needs_a_reason(self):
        url = reverse("admissions:application_decide", args=[self.application.pk])
        self.client.post(url, {"action": "reject", "note": ""})
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.SUBMITTED)
        self.client.post(url, {"action": "reject", "note": "Incomplete documents"})
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.Status.REJECTED)
        self.assertEqual(self.application.decision_note, "Incomplete documents")

    def test_decided_application_cannot_be_decided_again(self):
        services.decide(self.application, self.warden, True)
        with self.assertRaises(services.DecisionError):
            services.decide(self.application, self.warden, False, "Changed my mind")

    def test_decision_needs_post(self):
        url = reverse("admissions:application_decide", args=[self.application.pk])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_resident_sees_the_decision(self):
        services.decide(self.application, self.warden, False, "Incomplete documents")
        self.client.logout()
        login(self.client, "r1")
        response = self.client.get(reverse("admissions:my_application"))
        self.assertContains(response, "Rejected")
        self.assertContains(response, "Incomplete documents")


class PrivacyTests(TestCase):
    def test_other_roles_cannot_open_applications(self):
        resident = User.objects.create_user(username="r1", password=PASSWORD)
        application = services.submit_application(resident, **application_data())
        for index, role in enumerate([R.SECURITY_GUARD, R.MAINTENANCE_STAFF, R.MESS_MANAGER]):
            User.objects.create_user(username=f"s{index}", password=PASSWORD, role=role)
        other = User.objects.create_user(username="r2", password=PASSWORD)
        for username in ("s0", "s1", "s2", "r2"):
            self.client.logout()
            login(self.client, username)
            url = reverse("admissions:application_detail", args=[application.pk])
            self.assertEqual(self.client.get(url).status_code, 403, username)
        self.assertNotEqual(other.pk, resident.pk)

    def test_admin_site_leaves_out_medical_details(self):
        resident = User.objects.create_user(username="r1", password=PASSWORD)
        application = services.submit_application(resident, **application_data())
        User.objects.create_superuser(username="a1", password=PASSWORD)
        login(self.client, "a1")
        response = self.client.get(
            reverse("admin:admissions_application_change", args=[application.pk])
        )
        self.assertContains(response, "Aarav Sharma")
        self.assertNotContains(response, "Asthma")
        self.assertNotContains(response, "Blood group")


class ApplicationApiTests(TestCase):
    """SAD 4.3: POST /api/v1/applications."""

    payload = {
        "enrolmentNumber": "PES2UG24CS500",
        "personalDetails": {
            "fullName": "Aarav Sharma", "dateOfBirth": "2006-05-14", "gender": "M",
            "phone": "9876543210", "email": "aarav@example.edu", "address": "12 MG Road",
        },
        "academicDetails": {"programme": "B.Tech CSE", "yearOfStudy": 1, "cgpa": "8.5"},
        "guardianDetails": {
            "name": "Rakesh Sharma", "relation": "Father", "phone": "9876500000",
            "email": "rakesh@example.com",
        },
        "medicalDetails": {"bloodGroup": "O+", "conditions": ""},
        "preferredBlock": None,
        "roomType": "DOUBLE",
    }

    def setUp(self):
        User.objects.create_user(username="r1", password=PASSWORD)
        login(self.client, "r1")

    def post(self, payload=None):
        return self.client.post(
            "/api/v1/applications", payload or self.payload, content_type="application/json"
        )

    def test_valid_request_returns_the_application_number(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "Submitted")
        self.assertRegex(body["applicationNumber"], r"^HMS-2026-\d{5}$")

    def test_duplicate_is_409_with_the_error_envelope(self):
        self.post()
        other = User.objects.create_user(username="r2", password=PASSWORD)
        self.client.logout()
        login(self.client, "r2")
        response = self.post()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], 409)
        self.assertIn("already exists", response.json()["message"])
        self.assertEqual(Application.objects.count(), 1)
        self.assertNotEqual(other.pk, None)

    def test_invalid_request_is_400_with_field_details(self):
        payload = {**self.payload, "personalDetails": {**self.payload["personalDetails"],
                                                       "phone": "12"}}
        response = self.post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", str(response.json()["details"]))

    def test_missing_fields_are_400(self):
        self.assertEqual(self.post({"enrolmentNumber": "PES2UG24CS500"}).status_code, 400)

    def test_only_residents_may_apply(self):
        User.objects.create_user(username="w1", password=PASSWORD, role=R.WARDEN)
        self.client.logout()
        login(self.client, "w1")
        self.assertEqual(self.post().status_code, 403)
