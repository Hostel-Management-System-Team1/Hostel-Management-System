from decimal import Decimal

from django.db import migrations

# A starting fee structure so a new installation can invoice straight away. The
# administrator changes the amounts under Masters → Fee structure.
RENT = {"SINGLE": "60000.00", "DOUBLE": "45000.00", "TRIPLE": "36000.00"}


def add_default_fee_heads(apps, schema_editor):
    FeeHead = apps.get_model("fees", "FeeHead")
    for room_type, rent in RENT.items():
        for name, amount, refundable in (
            ("Room rent", rent, False),
            ("Mess advance", "15000.00", False),
            ("Security deposit", "10000.00", True),
            ("Maintenance", "3000.00", False),
        ):
            FeeHead.objects.get_or_create(
                name=name, room_type=room_type,
                defaults={"amount": Decimal(amount), "refundable": refundable},
            )


class Migration(migrations.Migration):
    dependencies = [("fees", "0001_initial")]
    operations = [migrations.RunPython(add_default_fee_heads, migrations.RunPython.noop)]
