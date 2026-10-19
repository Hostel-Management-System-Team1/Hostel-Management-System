from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.testutils import PASSWORD, login

from . import allocation as allocator
from .models import Allocation, Bed, Transfer
from .testutils import allocated_resident, make_block, make_resident, make_room

User = get_user_model()
R = User.Role


class TransferServiceTests(TestCase):
    """TC-ALL-02: source vacant, target occupied, atomically, with reason, actor and time."""

    def setUp(self):
        self.warden = make_resident("w1", role=R.WARDEN)
        self.boys = make_block("Block A", "M")
        self.girls = make_block("Block B", "F")
        self.room1 = make_room(self.boys, "101", "DOUBLE")
        self.room2 = make_room(self.boys, "102", "DOUBLE")
        self.allocation = allocated_resident("r1", room=self.room1)
        self.source = self.allocation.bed
        self.target = self.room2.beds.get(label="A")

    def test_transfer_moves_the_resident_and_records_it(self):
        record = allocator.transfer(self.allocation, self.target, "Roommate conflict", self.warden)
        self.allocation.refresh_from_db()
        self.source.refresh_from_db()
        self.target.refresh_from_db()
        self.assertEqual(self.allocation.bed, self.target)
        self.assertEqual(self.source.status, Bed.Status.VACANT)
        self.assertEqual(self.target.status, Bed.Status.OCCUPIED)
        self.assertEqual(record.reason, "Roommate conflict")
        self.assertEqual(record.performed_by, self.warden)
        self.assertEqual((record.from_bed, record.to_bed), (self.source, self.target))
        self.assertIsNotNone(record.performed_at)

    def test_reason_is_required(self):
        for reason in ("", "   ", None):
            with self.assertRaises(allocator.TransferError):
                allocator.transfer(self.allocation, self.target, reason, self.warden)
        self.assertFalse(Transfer.objects.exists())

    def test_target_must_be_vacant(self):
        other = allocated_resident("r2", room=self.room2)
        with self.assertRaises(allocator.TransferError):
            allocator.transfer(self.allocation, other.bed, "Move", self.warden)

    def test_target_must_be_in_a_block_for_the_residents_gender(self):
        girls_room = make_room(self.girls, "201", "DOUBLE")
        with self.assertRaises(allocator.TransferError):
            allocator.transfer(self.allocation, girls_room.beds.first(), "Move", self.warden)
        self.allocation.refresh_from_db()
        self.assertEqual(self.allocation.bed, self.source)

    def test_blocked_beds_and_rooms_are_refused(self):
        Bed.objects.filter(pk=self.target.pk).update(status=Bed.Status.BLOCKED)
        with self.assertRaises(allocator.TransferError):
            allocator.transfer(self.allocation, self.target, "Move", self.warden)

    def test_same_bed_is_refused(self):
        with self.assertRaises(allocator.TransferError):
            allocator.transfer(self.allocation, self.source, "Move", self.warden)

    def test_ended_allocation_cannot_be_transferred(self):
        allocator.end_allocation(self.allocation)
        with self.assertRaises(allocator.TransferError):
            allocator.transfer(self.allocation, self.target, "Move", self.warden)

    def test_it_is_all_or_nothing(self):
        with mock.patch.object(Transfer.objects, "create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                allocator.transfer(self.allocation, self.target, "Move", self.warden)
        self.allocation.refresh_from_db()
        self.source.refresh_from_db()
        self.target.refresh_from_db()
        self.assertEqual(self.allocation.bed, self.source)
        self.assertEqual(self.source.status, Bed.Status.OCCUPIED)
        self.assertEqual(self.target.status, Bed.Status.VACANT)

    def test_moves_can_be_repeated_and_all_are_kept(self):
        allocator.transfer(self.allocation, self.target, "First", self.warden)
        allocator.transfer(self.allocation, self.source, "Back again", self.warden)
        self.assertEqual(
            list(Transfer.objects.order_by("pk").values_list("reason", flat=True)),
            ["First", "Back again"])
        self.allocation.refresh_from_db()
        self.assertEqual(self.allocation.bed, self.source)
        self.assertEqual(Allocation.objects.filter(status="ACTIVE").count(), 1)

    def test_a_transfer_into_a_room_with_a_roommate_shows_on_their_dashboard(self):
        mate = allocated_resident("r2", bed=self.room2.beds.get(label="A"), first_name="Rohan")
        allocator.transfer(self.allocation, self.room2.beds.get(label="B"),
                           "Closer to class", self.warden)
        self.assertEqual(mate.bed.room, self.room2)
        login(self.client, "r2")
        self.assertContains(self.client.get(reverse("home")), "R1")  # first name of r1


class TransferViewTests(TestCase):
    def setUp(self):
        self.warden = make_resident("w1", role=R.WARDEN, first_name="Wendy")
        self.boys = make_block("Block A", "M")
        self.room1 = make_room(self.boys, "101", "DOUBLE")
        self.room2 = make_room(self.boys, "102", "DOUBLE")
        self.allocation = allocated_resident("r1", room=self.room1, first_name="Aarav")
        login(self.client, "w1")
        self.url = reverse("admissions:resident_detail", args=[self.allocation.pk])

    def test_resident_list_search(self):
        response = self.client.get(reverse("admissions:resident_list"))
        self.assertContains(response, "Aarav")
        self.assertContains(self.client.get(reverse("admissions:resident_list"), {"q": "102"}),
                            "No match")
        self.assertContains(self.client.get(reverse("admissions:resident_list"), {"q": "101"}),
                            "Aarav")

    def test_detail_lists_only_suitable_beds(self):
        girls_room = make_room(make_block("Block B", "F"), "201")
        response = self.client.get(self.url)
        self.assertContains(response, "Block A · room 102 · bed A")
        self.assertNotContains(response, f'value="{girls_room.beds.first().pk}"')

    def test_warden_transfers_a_resident(self):
        target = self.room2.beds.get(label="B")
        response = self.client.post(
            self.url, {"bed": target.pk, "reason": "Maintenance in room 101"}, follow=True)
        self.assertRedirects(response, self.url)
        self.assertContains(response, "moved from")
        self.assertContains(response, "Maintenance in room 101")
        self.assertContains(response, "Wendy")  # the actor, in the history table
        self.allocation.refresh_from_db()
        self.assertEqual(self.allocation.bed, target)

    def test_form_needs_a_reason_and_a_bed(self):
        response = self.client.post(self.url, {"bed": "", "reason": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")
        self.assertFalse(Transfer.objects.exists())

    def test_markup_in_the_reason_is_refused(self):
        target = self.room2.beds.get(label="A")
        response = self.client.post(self.url, {"bed": target.pk, "reason": "<b>x</b>"})
        self.assertContains(response, "Angle brackets are not allowed")
        self.assertFalse(Transfer.objects.exists())

    def test_residents_and_other_roles_cannot_transfer(self):
        target = self.room2.beds.get(label="A")
        self.client.logout()
        login(self.client, "r1")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        response = self.client.post(self.url, {"bed": target.pk, "reason": "Sneaky"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Transfer.objects.exists())

    def test_admin_site_shows_transfers_read_only(self):
        allocator.transfer(self.allocation, self.room2.beds.first(), "Move", self.warden)
        User.objects.create_superuser(username="a1", password=PASSWORD)
        self.client.logout()
        login(self.client, "a1")
        self.assertContains(self.client.get(reverse("admin:admissions_transfer_changelist")),
                            "Move")
        self.assertEqual(self.client.get(reverse("admin:admissions_transfer_add")).status_code, 403)
