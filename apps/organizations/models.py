from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel


class LegalEntity(UUIDPrimaryKeyModel, TimeStampedModel):
    """A company/legal reporting boundary, without speculative hierarchy."""

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "legal entities"
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(Lower("code"), name="organizations_entity_code_ci_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class OrganizationMembership(UUIDPrimaryKeyModel, TimeStampedModel):
    """Minimal user-to-legal-entity scope; detailed roles remain permission data."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "legal_entity"),
                name="organizations_membership_user_entity_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "is_active"),
                name="org_member_entity_active_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.legal_entity.code}"
