from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.models import EffectivePeriodModel, TimeStampedModel, UUIDPrimaryKeyModel
from apps.organizations.models import LegalEntity


class BusinessPartner(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """One canonical party identity shared by customer, vendor, and other roles."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="business_partners",
    )
    code = models.CharField(max_length=40)
    display_name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True)
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(max_length=2, default="ID")
    pic_name = models.CharField(max_length=150, blank=True)
    pic_title = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    pic_email = models.EmailField(blank=True)
    pic_phone = models.CharField(max_length=50, blank=True)
    npwp = models.CharField(max_length=40, blank=True)
    nitku = models.CharField(max_length=40, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_name = models.CharField(max_length=150, blank=True)
    bank_account_number = models.CharField(max_length=100, blank=True)
    payment_terms_days = models.PositiveIntegerField(default=0)
    credit_terms_days = models.PositiveIntegerField(default=0)
    credit_limit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    risk_flags = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(Lower("code"), name="partners_partner_code_ci_unique"),
            models.CheckConstraint(
                condition=Q(credit_limit__gte=0),
                name="partners_partner_credit_limit_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="partners_partner_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("legal_entity", "is_active"), name="partners_entity_active_idx"),
            models.Index(fields=("display_name",), name="partners_display_name_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.display_name}"


class PartnerRoleType(models.TextChoices):
    CUSTOMER = "CUSTOMER", "Customer"
    VENDOR = "VENDOR", "Vendor"
    SUBCONTRACTOR = "SUBCONTRACTOR", "Subcontractor"
    MARKETPLACE_PARTNER = "MARKETPLACE_PARTNER", "Marketplace partner"
    OTHER = "OTHER", "Other"


class PartnerRole(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Effective role assignment without a competing customer or supplier identity."""

    partner = models.ForeignKey(
        BusinessPartner,
        on_delete=models.PROTECT,
        related_name="roles",
    )
    role_type = models.CharField(max_length=32, choices=PartnerRoleType.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("partner__code", "role_type", "-effective_from")
        constraints = [
            models.UniqueConstraint(
                fields=("partner", "role_type", "effective_from"),
                name="partners_role_version_unique",
            ),
            models.UniqueConstraint(
                fields=("partner", "role_type"),
                condition=Q(is_active=True),
                name="partners_one_active_role_type",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="partners_role_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("role_type", "is_active"), name="partners_role_type_active_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.partner.code}: {self.role_type}"
