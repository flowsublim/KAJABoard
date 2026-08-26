from django.db import models
from django.db.models import Q

from apps.core.models import EffectivePeriodModel, TimeStampedModel, UUIDPrimaryKeyModel
from apps.organizations.models import CostCenter, LegalEntity


class AccountingTreatment(models.TextChoices):
    INVENTORY = "INVENTORY", "Inventory"
    ASSET = "ASSET", "Asset"
    EXPENSE = "EXPENSE", "Expense"
    SERVICE = "SERVICE", "Service"
    MAKLUN = "MAKLUN", "Maklun"


class PurchaseCategory(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Effective purchase classification; behavior is never inferred from the name."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="purchase_categories",
    )
    code = models.CharField(max_length=50)
    code_normalized = models.CharField(max_length=50, editable=False)
    name = models.CharField(max_length=150)
    accounting_treatment = models.CharField(max_length=20, choices=AccountingTreatment.choices)
    cost_center = models.ForeignKey(
        CostCenter,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_categories",
    )
    inventory_classification = models.CharField(max_length=80, blank=True)
    asset_class_reference = models.CharField(max_length=80, blank=True)
    snapshot_production = models.BooleanField(default=False)
    default_accounting_mapping_key = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "purchase categories"
        ordering = ("legal_entity__code", "code", "-effective_from")
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "code_normalized", "effective_from"),
                name="purch_category_scope_start_unique",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="purch_purchasecategory_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "code_normalized", "is_active"),
                name="purch_category_lookup_idx",
            ),
            models.Index(
                fields=("accounting_treatment", "is_active"),
                name="purch_category_treatment_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"
