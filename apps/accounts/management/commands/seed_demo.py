from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.admissions import allocation, services, vacating
from apps.admissions.models import Application, Block, Room
from apps.complaints.models import Complaint
from apps.gate import services as gate
from apps.gate.models import CurfewAlert, CurfewConfiguration
from apps.mess.models import MealOptOut, MessActivity, MessMenuItem
from apps.visitors.models import VisitingHours, Visitor

PASSWORD = "demo-pass-123"
# Fixed authenticator key so the demo accounts' codes can be read with `manage.py totp_code`.
DEMO_TOTP_KEY = "3132333435363738393031323334353637383930"

PEOPLE = [
    ("admin", "Asha", "Menon", User.Role.ADMINISTRATOR),
    ("warden", "Wendy", "Rao", User.Role.WARDEN),
    ("guard", "Gopal", "Singh", User.Role.SECURITY_GUARD),
    ("maintenance", "Manoj", "Kumar", User.Role.MAINTENANCE_STAFF),
    ("mess", "Meera", "Nair", User.Role.MESS_MANAGER),
    # Residents with a bed, so every Sprint 2 screen has something to show.
    ("aarav", "Aarav", "Sharma", User.Role.RESIDENT),
    ("diya", "Diya", "Patel", User.Role.RESIDENT),
    ("rohan", "Rohan", "Iyer", User.Role.RESIDENT),
    ("isha", "Isha", "Reddy", User.Role.RESIDENT),
    # Two residents who have not applied yet, for trying the application form.
    ("neha", "Neha", "Kapoor", User.Role.RESIDENT),
    ("omar", "Omar", "Sheikh", User.Role.RESIDENT),
]

# username: (enrolment number, gender, block, CGPA)
HOUSED = {
    "aarav": ("PES2UG24CS001", "M", "Block A", "8.70"),
    "rohan": ("PES2UG24CS002", "M", "Block A", "7.90"),
    "diya": ("PES2UG24CS003", "F", "Block B", "9.10"),
    "isha": ("PES2UG24CS004", "F", "Block B", "8.20"),
}

MENU = {
    "BREAKFAST": (time(8, 0), ["Idli, sambar, chutney", "Poha, banana", "Aloo paratha, curd",
                               "Dosa, chutney", "Upma, boiled egg", "Puri bhaji",
                               "Bread, omelette"]),
    "LUNCH": (time(13, 0), ["Rice, dal, cabbage poriyal", "Rajma chawal, salad",
                            "Veg biryani, raita", "Chapati, paneer butter masala",
                            "Curd rice, pickle", "Rice, sambar, beans", "Chole, jeera rice"]),
    "DINNER": (time(20, 0), ["Chapati, mixed veg, dal", "Fried rice, gobi manchurian",
                             "Chapati, egg curry", "Khichdi, kadhi", "Pulao, dal makhani",
                             "Chapati, aloo gobi", "Noodles, soup"]),
}


def at(day, clock):
    return timezone.make_aware(datetime.combine(day, clock))


class Command(BaseCommand):
    help = "Create demo accounts (one per role) and sample data. Development only; safe to re-run."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs in development (DJANGO_DEBUG=true).")
        people = {}
        for username, first, last, role in PEOPLE:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "role": role,
                          "email": f"{username}@example.edu", "phone": "9876543210"},
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            if role in {User.Role.WARDEN, User.Role.ADMINISTRATOR}:
                TOTPDevice.objects.get_or_create(
                    user=user, name="Demo authenticator",
                    defaults={"key": DEMO_TOTP_KEY, "confirmed": True},
                )
            people[username] = user
        for name, gender in (("Block A", "M"), ("Block B", "F")):
            block = Block.objects.get_or_create(name=name, defaults={"gender": gender})[0]
            for floor, numbers, room_type in ((1, ("101", "102", "103", "104"), "DOUBLE"),
                                              (2, ("201", "202"), "TRIPLE")):
                for number in numbers:
                    Room.objects.get_or_create(block=block, number=number, defaults={
                        "floor": floor, "room_type": room_type})
            CurfewConfiguration.objects.get_or_create(block=block, defaults={
                "curfew_time": time(22, 0)})

        # Outpass approvals and returns email the guardian; keep the demo quiet.
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            self.house_residents(people)
            if not Complaint.objects.exists():
                self.seed_activity(people)

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready. Sign in as admin, warden, guard, maintenance, mess, aarav, diya, "
            f"rohan, isha, neha or omar with password {PASSWORD}. For admin and warden the "
            f"second-step code comes from: python manage.py totp_code <username>"
        ))

    def house_residents(self, people):
        """Apply, approve and allocate a bed for the residents in HOUSED (invoices follow)."""
        warden = people["warden"]
        for username, (enrolment, gender, block_name, cgpa) in HOUSED.items():
            user = people[username]
            if Application.objects.filter(applicant=user).exists():
                continue
            application = services.submit_application(
                user,
                enrolment_number=enrolment, full_name=user.get_full_name(),
                date_of_birth=date(2006, 3, 14), gender=gender, phone="9876543210",
                email=user.email, address="12 MG Road, Bengaluru",
                programme="B.Tech Computer Science", year_of_study=2, cgpa=cgpa,
                guardian_name="Ravi Kumar", guardian_relation="Father",
                guardian_phone="9876500000", guardian_email=f"{username}.parent@example.com",
                blood_group="O+", room_type="DOUBLE",
                preferred_block=Block.objects.get(name=block_name),
            )
            services.decide(application, warden, approve=True)
            allocation.allocate(application, warden)

    def seed_activity(self, people):
        now = timezone.now()
        today = timezone.localdate()
        warden, guard = people["warden"], people["guard"]
        aarav, diya, rohan, isha = (people[n] for n in ("aarav", "diya", "rohan", "isha"))

        # Gate (#8): today's movements; Rohan was out past curfew last night.
        gate.record_movement(rohan, "OUT", "MANUAL", occurred_at=now - timedelta(hours=26),
                             recorded_by=guard)
        gate.record_movement(rohan, "IN", "RFID", occurred_at=now - timedelta(hours=20))
        gate.record_movement(aarav, "OUT", "RFID", occurred_at=now - timedelta(hours=3))
        gate.record_movement(diya, "OUT", "MANUAL", occurred_at=now - timedelta(hours=5),
                             recorded_by=guard)
        gate.record_movement(diya, "IN", "BIOMETRIC", occurred_at=now - timedelta(hours=2))
        CurfewAlert.objects.get_or_create(
            resident=rohan, curfew_date=today - timedelta(days=1),
            defaults={"block": Block.objects.get(name="Block A"),
                      "notified_at": now - timedelta(hours=24)},
        )

        # Outpasses (#9): Diya's waits for the warden; Isha is away on an approved one.
        gate.submit_outpass(diya, "Home, Mysuru", "9876511111", now + timedelta(days=2))
        away = gate.submit_outpass(isha, "Sister's wedding, Chennai", "9876522222",
                                   now + timedelta(days=1, hours=4))
        gate.decide_outpass(away.pk, warden, "APPROVED", "Carry the invitation card.")
        gate.generate_night_attendance(today - timedelta(days=1))

        # Complaints (#11): one per state, and one past its 48-hour SLA.
        def complaint(resident, title, category, description, days_ago, **extra):
            return Complaint.objects.create(
                created_by=resident, title=title, category=category, description=description,
                created_at=now - timedelta(days=days_ago), **extra)

        complaint(aarav, "Tap leaking in bathroom", "MAINTENANCE",
                  "The wash-basin tap in A-101 drips all night.", 1,
                  status="IN_PROGRESS", assigned_to=people["maintenance"])
        complaint(isha, "Ceiling fan not working", "MAINTENANCE",
                  "The fan in B-101 stopped working on Friday.", 3)
        complaint(diya, "Corridor not cleaned", "CLEANING",
                  "The second-floor corridor has not been swept for two days.", 0)
        complaint(rohan, "Loud music after 11 pm", "NOISE",
                  "Room A-104 plays music late every night.", 4, status="RESOLVED",
                  assigned_to=people["maintenance"], resolved_at=now - timedelta(days=1))

        # Mess (#10): this week's menu, a few opt-outs, and meals served last week.
        mess = people["mess"]
        for offset in range(-3, 7):  # the last few days (to record meals served) and the week ahead
            day = today + timedelta(days=offset)
            for meal, (clock, dishes) in MENU.items():
                MessMenuItem.objects.get_or_create(
                    menu_date=day, meal_type=meal,
                    defaults={"meal_datetime": at(day, clock), "description": dishes[offset % 7],
                              "is_published": True, "published_by": mess},
                )
        for resident, offset, meal in ((aarav, 3, "DINNER"), (diya, 2, "LUNCH"),
                                       (isha, 1, "BREAKFAST"), (isha, 1, "LUNCH")):
            MealOptOut.objects.get_or_create(
                resident=resident,
                menu_item=MessMenuItem.objects.get(menu_date=today + timedelta(days=offset),
                                                   meal_type=meal),
                defaults={"reason": "Away" if resident == isha else ""},
            )
        for offset in range(1, 6):
            for meal, served in (("BREAKFAST", 3), ("LUNCH", 4), ("DINNER", 4)):
                MessActivity.objects.get_or_create(
                    activity_date=today - timedelta(days=offset), meal_type=meal,
                    defaults={"meals_served": served - (offset % 2), "recorded_by": mess},
                )

        # Visitors (#12): one inside, one gone, one registered at the gate.
        VisitingHours.objects.get_or_create(is_active=True, defaults={
            "start_time": time(9, 0), "end_time": time(18, 0)})
        Visitor.objects.create(
            visitor_name="Sunita Sharma", phone="9876533333", id_proof_type="Aadhaar",
            id_proof_number="XXXX-1234", resident=aarav, purpose="Bringing winter clothes",
            registered_by=guard, entry_time=now - timedelta(minutes=40), status="INSIDE")
        Visitor.objects.create(
            visitor_name="Karan Patel", phone="9876544444", id_proof_type="Driving licence",
            id_proof_number="KA01-2020-77", resident=diya, purpose="Family visit",
            registered_by=guard, entry_time=now - timedelta(hours=26),
            exit_time=now - timedelta(hours=25), status="EXITED")
        Visitor.objects.create(
            visitor_name="Vikram Iyer", phone="9876555555", id_proof_type="Aadhaar",
            id_proof_number="XXXX-9876", resident=rohan, purpose="Dropping documents",
            registered_by=guard)

        # Vacating (#14): Rohan has asked to leave; the clearances are pending.
        vacating.submit_vacating_request(rohan, "Moving to a flat with friends next semester.")
