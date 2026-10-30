from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fees", "0002_default_fee_structure")]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="reminder_sent_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the overdue reminder was successfully dispatched.",
                null=True,
            ),
        ),
    ]
