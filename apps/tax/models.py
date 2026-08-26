from django.db import models
from django.db.models import Q

from apps.core.models import EffectivePeriodModel, TimeStampedModel, UUIDPrimaryKeyModel
from apps.organizations.models import LegalEntity
from apps.partners.models import BusinessPartner


class TaxRegistration(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Effective tax metadata; NPWP/NITKU stay on the owned subject master."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tax_registrations",
    )
    business_partner = models.ForeignKey(
        BusinessPartner,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tax_registrations",
    )
    registration_status = models.CharField(max_length=60, default="UNKNOWN")
    tax_classification_key = models.CharField(max_length=80, blank=True)
    registration_reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("registration_status", "-effective_from")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(legal_entity__isnull=False, business_partner__isnull=True)
                    | Q(legal_entity__isnull=True, business_partner__isnull=False)
                ),
                name="tax_registration_one_subject",
            ),
            models.UniqueConstraint(
                fields=("legal_entity", "effective_from"),
                condition=Q(business_partner__isnull=True),
                name="tax_registration_entity_start_unique",
            ),
            models.UniqueConstraint(
                fields=("business_partner", "effective_from"),
                condition=Q(legal_entity__isnull=True),
                name="tax_registration_partner_start_unique",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="tax_taxregistration_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("legal_entity", "is_active"), name="tax_reg_entity_idx"),
            models.Index(fields=("business_partner", "is_active"), name="tax_reg_partner_idx"),
            models.Index(
                fields=("tax_classification_key", "is_active"),
                name="tax_reg_classification_idx",
            ),
        ]

    @property
    def subject(self):
        return self.legal_entity or self.business_partner

    @property
    def npwp(self) -> str:
        return self.subject.npwp if self.subject else ""

    @property
    def nitku(self) -> str:
        return self.subject.nitku if self.subject else ""

    def __str__(self) -> str:
        subject = self.subject
        return f"{subject} tax registration" if subject else "Tax registration"
