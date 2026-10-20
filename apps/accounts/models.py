from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


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
    phone = models.CharField(max_length=15, blank=True)

    objects = HMSUserManager()

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
