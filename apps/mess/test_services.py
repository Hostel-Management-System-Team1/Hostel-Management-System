"""Unit tests for the mess helpers: publishing, the week grid, headcount and month figures."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.admissions.testutils import allocated_resident
from apps.fees.services import MESS_MEAL_PRICE

from . import services
from .models import MealOptOut, MessMenuItem

User = get_user_model()
R = User.Role


class MessServiceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user("svc_mess", password="x", role=R.MESS_MANAGER)

    def meal(self, when, meal_type="LUNCH", published=True):
        return MessMenuItem.objects.create(
            menu_date=timezone.localtime(when).date(),
            meal_datetime=when,
            meal_type=meal_type,
            description="Rice",
            is_published=published,
            published_by=self.manager,
        )

    def test_only_a_mess_manager_can_publish(self):
        item = self.meal(timezone.now() + timedelta(days=2), published=False)
        warden = User.objects.create_user("svc_warden", password="x", role=R.WARDEN)
        with self.assertRaises(PermissionError):
            services.publish_menu(item, warden)
        services.publish_menu(item, self.manager)
        item.refresh_from_db()
        self.assertTrue(item.is_published)
        self.assertEqual(item.published_by, self.manager)

    def test_headcount_counts_only_active_allocations(self):
        self.assertEqual(services.housed_resident_count(), 0)
        allocated_resident("svc_resident")
        self.assertEqual(services.housed_resident_count(), 1)

    def test_menu_grid_lists_days_in_order_and_only_the_meal_types_used(self):
        later = self.meal(timezone.now() + timedelta(days=3), "DINNER")
        sooner = self.meal(timezone.now() + timedelta(days=1), "LUNCH")
        types, days = services.menu_grid([later, sooner])
        self.assertEqual([value for value, _ in types], ["LUNCH", "DINNER"])
        self.assertEqual([day for day, _ in days], [sooner.menu_date, later.menu_date])
        self.assertEqual(days[0][1], [("Lunch", sooner), ("Dinner", None)])

    def test_week_start_is_a_monday_and_moves_by_whole_weeks(self):
        monday = services.week_start()
        self.assertEqual(monday.weekday(), 0)
        self.assertEqual(services.week_start(2), monday + timedelta(weeks=2))

    def test_week_offset_is_clamped_and_tolerates_garbage(self):
        factory = RequestFactory()
        self.assertEqual(services.week_offset(factory.get("/", {"week": "9"}), -1, 2), 2)
        self.assertEqual(services.week_offset(factory.get("/", {"week": "-9"}), -1, 2), -1)
        self.assertEqual(services.week_offset(factory.get("/", {"week": "abc"}), -1, 2), 0)
        self.assertEqual(services.week_offset(factory.get("/"), -1, 2), 0)

    def test_week_grid_has_seven_days_and_hides_snacks_unless_used(self):
        monday = services.week_start()
        types, days = services.week_grid(monday, [])
        self.assertEqual(len(days), 7)
        self.assertNotIn("SNACKS", [value for value, _ in types])
        snack = self.meal(timezone.now() + timedelta(days=1), "SNACKS")
        types, _ = services.week_grid(monday, [snack])
        self.assertIn("SNACKS", [value for value, _ in types])

    def test_month_so_far_prices_the_meals_eaten_not_the_ones_skipped(self):
        resident = allocated_resident("svc_eater").resident
        today = timezone.localdate()
        # Two meals already served earlier today; the resident skipped one of them.
        # Midnight and 00:30 keep both inside the current month and in the past.
        start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        first = self.meal(start + timedelta(minutes=1), "BREAKFAST")
        self.meal(start + timedelta(minutes=2), "LUNCH")
        MealOptOut.objects.create(resident=resident, menu_item=first)
        if timezone.now() < start + timedelta(minutes=2):
            self.skipTest("run too close to midnight for the meals to count as served")
        figures = services.month_so_far(resident)
        self.assertEqual(figures, {"eaten": 1, "skipped": 1, "cost": MESS_MEAL_PRICE})
