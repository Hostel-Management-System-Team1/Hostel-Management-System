"""Builders other modules' tests use to get a resident into a bed quickly."""

from datetime import date

from django.contrib.auth import get_user_model

from apps.accounts.testutils import PASSWORD

from . import allocation, services
from .models import Application, Block, Room

User = get_user_model()

_counter = {"n": 0}


def application_data(**overrides):
    _counter["n"] += 1
    n = _counter["n"]
    data = {
        "enrolment_number": f"PES2UG24CS{n:03d}",
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
        "medical_conditions": "",
        "room_type": "DOUBLE",
    }
    data.update(overrides)
    return data


def make_block(name="Block A", gender="M"):
    return Block.objects.get_or_create(name=name, defaults={"gender": gender})[0]


def make_room(block=None, number="101", room_type="DOUBLE", floor=1, **kwargs):
    block = block or make_block()
    return Room.objects.create(
        block=block, number=number, room_type=room_type, floor=floor, **kwargs
    )


def make_resident(username, **extra):
    return User.objects.create_user(username=username, password=PASSWORD, **extra)


def approved_application(resident, **overrides):
    application = services.submit_application(resident, **application_data(**overrides))
    warden = User.objects.filter(role=User.Role.WARDEN).first() or User.objects.create_user(
        username="warden0", password=PASSWORD, role=User.Role.WARDEN
    )
    return services.decide(application, warden, True)


def allocated_resident(username="r1", room=None, **overrides):
    """A resident with an approved application and an active allocation; returns the allocation."""
    resident = make_resident(username, first_name=overrides.pop("first_name", username.title()))
    room = room or Room.objects.first() or make_room()
    overrides.setdefault("gender", room.block.gender)
    overrides.setdefault("room_type", room.room_type)
    application = approved_application(resident, **overrides)
    warden = User.objects.filter(role=User.Role.WARDEN).first()
    return allocation.allocate(Application.objects.get(pk=application.pk), warden)
