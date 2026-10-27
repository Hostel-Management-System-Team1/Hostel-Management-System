
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.accounts.models import User
from apps.admissions.models import (
    Allocation,
    Application,
    Bed,
    Block,
    Room,
    RoomType,
)


class Command(BaseCommand):
    help = "Create synthetic resident allocations for performance testing."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=2000)

    @transaction.atomic
    def handle(self, *args, **options):
        count = options["count"]

        if connection.vendor != "postgresql":
            raise CommandError("This command requires PostgreSQL.")

        if connection.settings_dict["NAME"] != "hms_perf_test":
            raise CommandError(
                "Safety check failed: database must be hms_perf_test."
            )

        if count < 1:
            raise CommandError("--count must be positive.")

        if Allocation.objects.filter(
            status=Allocation.Status.ACTIVE
        ).exists():
            raise CommandError(
                "Active allocations already exist. Use a fresh test database."
            )

        if User.objects.filter(
            username__startswith="perfresident"
        ).exists():
            raise CommandError(
                "Synthetic users already exist. Use a fresh test database."
            )

        actor = User.objects.filter(role="WARDEN").first()
        if actor is None:
            actor = User.objects.filter(role="ADMINISTRATOR").first()
        if actor is None:
            raise CommandError("Run seed_demo first to create demo staff.")

        male_block, _ = Block.objects.get_or_create(
            name="Performance Block M",
            defaults={"gender": "M"},
        )
        female_block, _ = Block.objects.get_or_create(
            name="Performance Block F",
            defaults={"gender": "F"},
        )

        if male_block.gender != "M" or female_block.gender != "F":
            raise CommandError("Performance block gender mismatch.")

        session = "2026-27"
        room_type = RoomType.TRIPLE

        # Ensure enough beds in each gender-specific block.
        for block, required in (
            (male_block, (count + 1) // 2),
            (female_block, count // 2),
        ):
            existing_beds = Bed.objects.filter(
                room__block=block,
                room__room_type=room_type,
                room__status=Room.Status.AVAILABLE,
                status=Bed.Status.VACANT,
            ).count()

            room_number = 1
            while existing_beds < required:
                number = f"PT{room_number:05d}"
                if Room.objects.filter(
                    block=block, number=number
                ).exists():
                    room_number += 1
                    continue

                Room.objects.create(
                    block=block,
                    floor=room_number % 5,
                    number=number,
                    room_type=room_type,
                    bed_capacity=3,
                    status=Room.Status.AVAILABLE,
                )
                existing_beds += 3
                room_number += 1

        male_beds = list(
            Bed.objects.filter(
                room__block=male_block,
                room__room_type=room_type,
                room__status=Room.Status.AVAILABLE,
                status=Bed.Status.VACANT,
            ).select_related("room", "room__block").order_by("id")
        )
        female_beds = list(
            Bed.objects.filter(
                room__block=female_block,
                room__room_type=room_type,
                room__status=Room.Status.AVAILABLE,
                status=Bed.Status.VACANT,
            ).select_related("room", "room__block").order_by("id")
        )

        male_count = (count + 1) // 2
        female_count = count // 2

        if len(male_beds) < male_count or len(female_beds) < female_count:
            raise CommandError("Not enough gender-matched vacant beds.")

        residents = []
        applications = []

        for i in range(1, count + 1):
            gender = "M" if i % 2 else "F"
            username = f"perfresident{i:05d}"

            resident = User.objects.create_user(
                username=username,
                password=None,
                first_name=f"Perf{i:05d}",
                last_name="Resident",
                email=f"{username}@example.invalid",
                role="RESIDENT",
                is_active=True,
            )
            residents.append(resident)

            block = male_block if gender == "M" else female_block
            applications.append(
                Application(
                    application_number=f"PERF-{i:05d}",
                    applicant=resident,
                    academic_session=session,
                    status=Application.Status.ALLOCATED,
                    enrolment_number=f"PERF{i:05d}",
                    full_name=f"Perf{i:05d} Resident",
                    date_of_birth=date(2004, 1, 1),
                    gender=gender,
                    phone=f"9{i:09d}",
                    email=f"{username}@example.invalid",
                    address="Synthetic performance test record",
                    programme="B.Tech Computer Science",
                    year_of_study=2,
                    cgpa="8.00",
                    guardian_name="Test Guardian",
                    guardian_relation="Parent",
                    guardian_phone=f"8{i:09d}",
                    preferred_block=block,
                    room_type=room_type,
                )
            )

        Application.objects.bulk_create(applications, batch_size=500)

        saved_apps = {
            app.applicant_id: app
            for app in Application.objects.filter(
                applicant__username__startswith="perfresident",
                academic_session=session,
            )
        }

        allocations = []
        occupied_beds = []

        for i, resident in enumerate(residents, start=1):
            gender = "M" if i % 2 else "F"
            bed_pool = male_beds if gender == "M" else female_beds
            bed = bed_pool.pop(0)
            application = saved_apps[resident.id]

            allocations.append(
                Allocation(
                    application=application,
                    resident=resident,
                    bed=bed,
                    status=Allocation.Status.ACTIVE,
                    allocated_by=actor,
                )
            )
            bed.status = Bed.Status.OCCUPIED
            occupied_beds.append(bed)

        Allocation.objects.bulk_create(allocations, batch_size=500)
        Bed.objects.bulk_update(
            occupied_beds, ["status"], batch_size=500
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {count} synthetic residents, applications, "
                "and active allocations."
            )
        )
