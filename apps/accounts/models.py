import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel

from .managers import UserManager


class User(AbstractUser):
    """Stable internal user identity with email-based authentication."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(_("email address"), unique=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]
        ordering = ("email",)

    def __str__(self) -> str:
        return self.email


class Employee(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    employee_code = models.CharField(max_length=64)
    display_name = models.CharField(max_length=255)
    user = models.OneToOneField(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="employee_profile"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "employee_code"), name="acct_employee_code_uq"
            )
        ]
