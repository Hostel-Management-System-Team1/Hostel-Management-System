from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.db import models

from hms.validators import phone_number


class HMSUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMINISTRATOR)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """A system user. Guardians are notified but never log in (SRS 2.3)."""

    class Role(models.TextChoices):
        RESIDENT = "RESIDENT", "Resident"
        WARDEN = "WARDEN", "Warden"
        SECURITY_GUARD = "SECURITY_GUARD", "Security Guard"
        MAINTENANCE_STAFF = "MAINTENANCE_STAFF", "Maintenance Staff"
        MESS_MANAGER = "MESS_MANAGER", "Mess Manager"
        ADMINISTRATOR = "ADMINISTRATOR", "Hostel Administrator"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.RESIDENT,
        help_text="A Resident is a student living in the hostel. Hostel Administrators use "
        "this admin site; every other role signs in to the portal.",
    )
    phone = models.CharField(max_length=15, blank=True, validators=[phone_number])

    objects = HMSUserManager()

    @classmethod
    def from_db(cls, db, field_names, values):
        user = super().from_db(db, field_names, values)
        # What the row held when loaded, so the audit log can say what an edit changed.
        user._loaded = {"role": user.role, "is_active": user.is_active}
        return user

    def set_password(self, raw_password):
        super().set_password(raw_password)
        self._password_changed = True

    def clean(self):
        super().clean()
        errors = {
            field: "Angle brackets are not allowed."
            for field in ("first_name", "last_name")
            if "<" in getattr(self, field) or ">" in getattr(self, field)
        }
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # The role decides access: Hostel Administrators work in the admin site with
        # full rights; every other role uses the portal (SRS 2.3, HMS-SR-002).
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "role" in update_fields:
            self.is_staff = self.is_superuser = self.role == self.Role.ADMINISTRATOR
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "is_staff", "is_superuser"}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"
