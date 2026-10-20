from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.testutils import PASSWORD, login

from . import allocation as allocator
from .models import Allocation, AllocationPolicy, Application, Bed, Room
from .testutils import (
    allocated_resident,
    approved_application,
    make_block,
    make_resident,
    make_room,
)

User = get_user_model()
R = User.Role


class RoomInventoryTests(TestCase):
    """TC-INV-01 and the room maintenance side of HMS-F-061."""

    def test_beds_follow_the_room_type(self):
        cases = (("1", "SINGLE", 1), ("2", "DOUBLE", 2), ("3", "TRIPLE", 3))
        for number, room_type, count in cases:
            room = make_room(number=number, room_type=room_type)
            self.assertEqual(room.beds.count(), count)
            self.assertEqual(room.bed_capacity, count)

    def test_labels_are_a_b_c(self):
        room = make_room(room_type="TRIPLE")
        self.assertEqual([b.label for b in room.beds.all()], ["A", "B", "C"])

    def test_capacity_can_be_set_and_changed(self):
        room = make_room(bed_capacity=4)
        self.assertEqual(room.beds.count(), 4)
        room.bed_capacity = 3
        room.save()
        self.assertEqual(room.beds.count(), 3)
        room.bed_capacity = 5
        room.save()
        self.assertEqual(room.beds.count(), 5)

    def test_capacity_cannot_drop_below_beds_in_use(self):
        from django.core.exceptions import ValidationError

        room = make_room(room_type="DOUBLE")
        allocated_resident("r1", room=room)
        room.bed_capacity = 1  # one bed is occupied, the other is free to go
        room.full_clean()
        allocated_resident("r2", room=room)
        room.bed_capacity = 1  # both beds now hold residents
        with self.assertRaises(ValidationError):
            room.full_clean()

    def test_room_number_is_unique_within_a_block(self):
        from django.db import IntegrityError, transaction

        block = make_block()
        make_room(block, "101")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_room(block, "101")
        make_room(make_block("Block B", "F"), "101")  # fine in another block

    def test_room_with_an_occupied_bed_cannot_be_deleted(self):
        allocated_resident("r1", room=make_room())
        room = Room.objects.get()
        with self.assertRaises(ProtectedError):
            room.delete()
        with self.assertRaises(ProtectedError):
            Room.objects.filter(pk=room.pk).delete()
        self.assertTrue(Room.objects.filter(pk=room.pk).exists())

    def test_room_with_only_vacant_beds_can_be_deleted(self):
        room = make_room()
        room.delete()
        self.assertFalse(Room.objects.exists())
        self.assertFalse(Bed.objects.exists())

    def test_admin_hides_delete_for_a_room_with_an_occupied_bed(self):
        User.objects.create_superuser(username="a1", password=PASSWORD)
        login(self.client, "a1")
        full = make_room(number="201")
        allocated_resident("r1", room=full)
        empty = make_room(number="202")
        page = self.client.get(reverse("admin:admissions_room_change", args=[full.pk]))
        self.assertNotContains(page, "class=\"deletelink\"")
        self.assertEqual(
            self.client.get(reverse("admin:admissions_room_delete", args=[full.pk])).status_code,
            403,
        )
        page = self.client.get(reverse("admin:admissions_room_change", args=[empty.pk]))
        self.assertContains(page, "class=\"deletelink\"")

    def test_administrator_edits_the_room_inventory_in_the_admin(self):
        User.objects.create_superuser(username="a1", password=PASSWORD)
        login(self.client, "a1")
        block = make_block()
        response = self.client.post(reverse("admin:admissions_room_add"), {
            "block": block.pk, "floor": 2, "number": "205", "room_type": "TRIPLE",
            "bed_capacity": "", "status": "AVAILABLE",
            "beds-TOTAL_FORMS": 0, "beds-INITIAL_FORMS": 0, "beds-MIN_NUM_FORMS": 0,
            "beds-MAX_NUM_FORMS": 1000, "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Room.objects.get(number="205").beds.count(), 3)

    def test_blocked_rooms_and_beds_are_not_offered(self):
        room = make_room()
        room.beds.filter(label="A").update(status=Bed.Status.BLOCKED)
        resident = make_resident("r1")
        application = approved_application(resident)
        self.assertEqual([b.label for b in allocator.candidate_beds(application)], ["B"])
        room.status = Room.Status.BLOCKED
        room.save()
        self.assertFalse(allocator.candidate_beds(application).exists())


class AutomaticAllocationTests(TestCase):
    """TC-ALL-01: only vacant, gender-matching beds that fit the request are considered."""

    def setUp(self):
        self.boys = make_block("Block A", "M")
        self.girls = make_block("Block B", "F")
        self.warden = make_resident("w1", role=R.WARDEN)

    def test_a_bed_in_a_matching_room_is_allocated(self):
        make_room(self.boys, "101", "DOUBLE")
        resident = make_resident("r1")
        application = approved_application(resident)
        allocation = allocator.allocate(application, self.warden)
        self.assertEqual(allocation.bed.room.number, "101")
        self.assertEqual(allocation.bed.status, Bed.Status.OCCUPIED)
        self.assertEqual(allocation.resident, resident)
        self.assertEqual(allocation.allocated_by, self.warden)
        application.refresh_from_db()
        self.assertEqual(application.status, Application.Status.ALLOCATED)

    def test_gender_must_match_the_block(self):
        make_room(self.girls, "101", "DOUBLE")
        application = approved_application(make_resident("r1"), gender="M")
        with self.assertRaises(allocator.NoVacantBed):
            allocator.allocate(application, self.warden)

    def test_a_woman_is_placed_in_a_womens_block(self):
        make_room(self.boys, "101")
        make_room(self.girls, "201")
        application = approved_application(make_resident("r1"), gender="F")
        self.assertEqual(
            allocator.allocate(application, self.warden).bed.room.block, self.girls)

    def test_room_type_must_match(self):
        make_room(self.boys, "101", "SINGLE")
        application = approved_application(make_resident("r1"), room_type="TRIPLE")
        with self.assertRaises(allocator.NoVacantBed):
            allocator.allocate(application, self.warden)

    def test_preferred_block_is_respected(self):
        other = make_block("Block C", "M")
        make_room(self.boys, "101")
        make_room(other, "301")
        application = approved_application(make_resident("r1"), preferred_block=other)
        self.assertEqual(allocator.allocate(application, self.warden).bed.room.block, other)

    def test_occupied_beds_are_not_reused(self):
        make_room(self.boys, "101", "SINGLE")
        first = approved_application(make_resident("r1"), room_type="SINGLE")
        allocator.allocate(first, self.warden)
        second = approved_application(make_resident("r2"), room_type="SINGLE")
        with self.assertRaises(allocator.NoVacantBed):
            allocator.allocate(second, self.warden)

    def test_only_an_approved_application_can_be_allocated(self):
        from . import services
        from .testutils import application_data

        make_room(self.boys, "101")
        application = services.submit_application(make_resident("r1"), **application_data())
        with self.assertRaises(allocator.AllocationError):
            allocator.allocate(application, self.warden)

    def test_no_second_allocation_for_the_same_application(self):
        make_room(self.boys, "101")
        application = approved_application(make_resident("r1"))
        allocator.allocate(application, self.warden)
        with self.assertRaises(allocator.AllocationError):
            allocator.allocate(application, self.warden)
        self.assertEqual(Allocation.objects.count(), 1)

    def test_data_layer_refuses_the_wrong_gender_even_if_the_query_is_bypassed(self):
        from django.core.exceptions import ValidationError

        room = make_room(self.girls, "201")
        application = approved_application(make_resident("r1"), gender="M")
        with self.assertRaises(ValidationError):
            Allocation.objects.create(
                application=application, resident=application.applicant,
                bed=room.beds.first(), allocated_by=self.warden,
            )
        self.assertFalse(Allocation.objects.exists())


class RankingTests(TestCase):
    def setUp(self):
        self.warden = make_resident("w1", role=R.WARDEN)
        make_room(make_block("Block A", "M"), "101", "SINGLE")  # one bed, three applicants
        make_room(make_block("Block A", "M"), "102", "SINGLE")
        make_room(make_block("Block A", "M"), "103", "SINGLE")
        # Applied in this order: low merit / senior, high merit / junior, middle.
        self.a = approved_application(make_resident("ra"), cgpa="7.00", year_of_study=4,
                                      room_type="SINGLE")
        self.b = approved_application(make_resident("rb"), cgpa="9.50", year_of_study=1,
                                      room_type="SINGLE")
        self.c = approved_application(make_resident("rc"), cgpa="8.00", year_of_study=2,
                                      room_type="SINGLE")

    def order(self):
        return [a.pk for a in allocator.ranked_waiting_applications()]

    def test_merit_ranks_by_cgpa(self):
        AllocationPolicy.objects.update_or_create(pk=1, defaults={"ranking": "MERIT"})
        self.assertEqual(self.order(), [self.b.pk, self.c.pk, self.a.pk])

    def test_seniority_ranks_by_year(self):
        AllocationPolicy.objects.update_or_create(pk=1, defaults={"ranking": "SENIORITY"})
        self.assertEqual(self.order(), [self.a.pk, self.c.pk, self.b.pk])

    def test_first_come_ranks_by_submission_time(self):
        AllocationPolicy.objects.update_or_create(pk=1, defaults={"ranking": "FIRST_COME"})
        self.assertEqual(self.order(), [self.a.pk, self.b.pk, self.c.pk])

    def test_allocate_all_follows_the_ranking_and_reports_who_missed_out(self):
        Bed.objects.filter(room__number="103").update(status=Bed.Status.BLOCKED)
        AllocationPolicy.objects.update_or_create(pk=1, defaults={"ranking": "MERIT"})
        allocations, skipped = allocator.allocate_all(self.warden)
        self.assertEqual([a.application_id for a in allocations], [self.b.pk, self.c.pk])
        self.assertEqual([a.pk for a, _ in skipped], [self.a.pk])
        self.assertIn("No vacant bed", skipped[0][1])


class ManualAllocationTests(TestCase):
    def setUp(self):
        self.warden = make_resident("w1", role=R.WARDEN)
        self.boys = make_room(make_block("Block A", "M"), "101", "DOUBLE")
        self.girls = make_room(make_block("Block B", "F"), "201", "DOUBLE")

    def test_warden_chooses_a_bed(self):
        application = approved_application(make_resident("r1"))
        bed = self.boys.beds.get(label="B")
        self.assertEqual(allocator.allocate(application, self.warden, bed=bed).bed, bed)

    def test_chosen_bed_must_be_for_the_applicants_gender(self):
        application = approved_application(make_resident("r1"), gender="M")
        with self.assertRaises(allocator.AllocationError):
            allocator.allocate(application, self.warden, bed=self.girls.beds.first())

    def test_chosen_bed_must_be_vacant(self):
        allocated_resident("r1", room=self.boys)
        application = approved_application(make_resident("r2"))
        taken = self.boys.beds.get(status=Bed.Status.OCCUPIED)
        with self.assertRaises(allocator.AllocationError):
            allocator.allocate(application, self.warden, bed=taken)


class AllocationViewTests(TestCase):
    def setUp(self):
        self.warden = make_resident("w1", role=R.WARDEN, first_name="Wendy")
        self.room = make_room(make_block("Block A", "M"), "101", "DOUBLE")
        self.resident = make_resident("r1", first_name="Aarav")
        self.application = approved_application(self.resident)
        login(self.client, "w1")

    def test_detail_offers_the_suggested_bed(self):
        response = self.client.get(
            reverse("admissions:application_detail", args=[self.application.pk]))
        self.assertContains(response, "Suggested bed")
        self.assertContains(response, "Block A · room 101 · bed A")

    def test_detail_without_a_matching_bed_says_so(self):
        Bed.objects.update(status=Bed.Status.BLOCKED)
        response = self.client.get(
            reverse("admissions:application_detail", args=[self.application.pk]))
        self.assertContains(response, "No matching bed")

    def test_warden_allocates_the_suggested_bed(self):
        url = reverse("admissions:application_allocate", args=[self.application.pk])
        response = self.client.post(url, follow=True)
        self.assertContains(response, "is allocated Block A · 101 · bed A")
        self.assertEqual(Allocation.objects.get().resident, self.resident)

    def test_warden_allocates_a_chosen_bed(self):
        bed = self.room.beds.get(label="B")
        url = reverse("admissions:application_allocate", args=[self.application.pk])
        self.client.post(url, {"bed": bed.pk})
        self.assertEqual(Allocation.objects.get().bed, bed)

    def test_failed_allocation_shows_the_reason(self):
        Bed.objects.update(status=Bed.Status.BLOCKED)
        url = reverse("admissions:application_allocate", args=[self.application.pk])
        response = self.client.post(url, follow=True)
        self.assertContains(response, "No vacant bed matches")
        self.assertFalse(Allocation.objects.exists())

    def test_allocate_all_button(self):
        response = self.client.post(reverse("admissions:allocate_all"), follow=True)
        self.assertContains(response, "1 applicants were allocated beds")
        self.assertEqual(Allocation.objects.count(), 1)

    def test_approved_tab_lists_in_allocation_order(self):
        response = self.client.get(reverse("admissions:application_list"), {"status": "APPROVED"})
        self.assertContains(response, "Allocate all in ranked order")
        self.assertContains(response, "highest cgpa first")

    def test_allocated_application_shows_the_bed(self):
        self.client.post(reverse("admissions:application_allocate", args=[self.application.pk]))
        response = self.client.get(
            reverse("admissions:application_detail", args=[self.application.pk]))
        self.assertContains(response, "Allocated")
        self.assertContains(response, "Wendy")

    def test_room_list_shows_occupants(self):
        self.client.post(reverse("admissions:application_allocate", args=[self.application.pk]))
        response = self.client.get(reverse("admissions:room_list"))
        self.assertContains(response, "1 of 2 occupied")
        self.assertContains(response, "Aarav")

    def test_room_list_filters_by_block(self):
        other = make_room(make_block("Block B", "F"), "201")
        response = self.client.get(reverse("admissions:room_list"), {"block": other.block_id})
        self.assertContains(response, "Block B · 201")
        self.assertNotContains(response, "Block A · 101")

    def test_resident_sees_their_room_and_roommate(self):
        allocation = allocator.allocate(self.application, self.warden)
        other = allocated_resident("r2", room=self.room, first_name="Rohan")
        self.assertEqual(other.bed.room, allocation.bed.room)
        self.client.logout()
        login(self.client, "r1")
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Your room")
        self.assertContains(response, "Roommates")
        self.assertContains(response, "Rohan")


class AllocationApiTests(TestCase):
    def setUp(self):
        self.warden = make_resident("w1", role=R.WARDEN)
        self.room = make_room(make_block("Block A", "M"), "101")
        self.application = approved_application(make_resident("r1"))
        login(self.client, "w1")

    def post(self, number):
        return self.client.post(
            "/api/v1/allocations", {"applicationNumber": number}, content_type="application/json")

    def test_allocation_returns_bed_block_room_and_time(self):
        response = self.post(self.application.application_number)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual((body["block"], body["room"]), ("Block A", "101"))
        self.assertIn("allocatedAt", body)
        self.assertTrue(Bed.objects.filter(pk=body["bedId"]).exists())

    def test_unknown_or_unapproved_application_is_404(self):
        self.assertEqual(self.post("HMS-2026-99999").status_code, 404)

    def test_no_matching_bed_is_409(self):
        Bed.objects.update(status=Bed.Status.BLOCKED)
        response = self.post(self.application.application_number)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], 409)

    def test_residents_cannot_allocate(self):
        self.client.logout()
        login(self.client, "r1")
        self.assertEqual(self.post(self.application.application_number).status_code, 403)
