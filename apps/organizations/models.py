from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.models import EffectivePeriodModel, TimeStampedModel, UUIDPrimaryKeyModel


class LegalEntity(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Company/legal reporting boundary and stable document identity."""

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(max_length=2, default="ID")
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    npwp = models.CharField(max_length=40, blank=True)
    nitku = models.CharField(max_length=40, blank=True)
    is_pkp = models.BooleanField(default=False)
    reporting_currency = models.CharField(max_length=3, default="IDR")
    timezone = models.CharField(max_length=64, default="Asia/Jakarta")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "legal entities"
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(Lower("code"), name="organizations_entity_code_ci_unique"),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="organizations_legalentity_effective_period_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class BusinessUnit(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Brand or operating unit within one legal entity."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="business_units",
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    document_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(
                Lower("code"), name="organizations_businessunit_code_ci_unique"
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="organizations_businessunit_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("legal_entity", "is_active"), name="org_bu_entity_active_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class Department(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Organization department, optionally attached to a business unit."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="departments",
    )
    business_unit = models.ForeignKey(
        BusinessUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="departments",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(Lower("code"), name="organizations_department_code_ci_unique"),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="organizations_department_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("legal_entity", "is_active"), name="org_dept_entity_active_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class CostCenterCategory(models.TextChoices):
    PRODUCTION = "PRODUCTION", "Production"
    WAREHOUSE = "WAREHOUSE", "Warehouse"
    OFFICE = "OFFICE", "Office"
    SALES_MARKETING = "SALES_MARKETING", "Sales & Marketing"
    GENERAL = "GENERAL", "General"
    OTHER = "OTHER", "Other"


class CostCenter(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Configurable analysis dimension with explicit overhead eligibility."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="cost_centers",
    )
    business_unit = models.ForeignKey(
        BusinessUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cost_centers",
    )
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cost_centers",
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    category = models.CharField(
        max_length=32,
        choices=CostCenterCategory.choices,
        default=CostCenterCategory.OTHER,
    )
    is_production_overhead_eligible = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(Lower("code"), name="organizations_costcenter_code_ci_unique"),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="organizations_costcenter_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("legal_entity", "is_active"), name="org_cc_entity_active_idx"),
            models.Index(
                fields=("is_production_overhead_eligible", "is_active"),
                name="org_cc_prod_eligible_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class Warehouse(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Warehouse master only; it does not hold stock quantity or movement."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="warehouses",
    )
    business_unit = models.ForeignKey(
        BusinessUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="warehouses",
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(Lower("code"), name="organizations_warehouse_code_ci_unique"),
            models.UniqueConstraint(
                fields=("legal_entity",),
                condition=Q(is_default=True),
                name="organizations_one_default_warehouse_per_entity",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="organizations_warehouse_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("legal_entity", "is_active"), name="org_wh_entity_active_idx"),
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
