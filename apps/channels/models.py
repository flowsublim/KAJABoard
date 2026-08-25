from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.catalog.models import Item
from apps.core.models import EffectivePeriodModel, TimeStampedModel, UUIDPrimaryKeyModel
from apps.organizations.models import BusinessUnit, LegalEntity


class Store(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Stable store/sales-channel identity; no order or accounting posting behavior."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="stores",
    )
    business_unit = models.ForeignKey(
        BusinessUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stores",
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    channel = models.CharField(
        max_length=50,
        help_text="Stable platform/channel key such as SHOPEE, TIKTOK, POS, or B2B.",
    )
    external_account_id = models.CharField(max_length=120, blank=True)
    external_aliases = models.JSONField(default=list, blank=True)
    finance_dimension = models.CharField(max_length=80, blank=True)
    revenue_mapping_key = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(Lower("code"), name="channels_store_code_ci_unique"),
            models.UniqueConstraint(
                fields=("legal_entity", "channel", "external_account_id"),
                condition=~Q(external_account_id=""),
                name="channels_store_external_account_unique",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="channels_store_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "channel", "is_active"),
                name="channels_store_scope_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class ExternalSKUMap(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Effective external SKU identity mapped to one canonical catalog Item."""

    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        related_name="sku_mappings",
    )
    item = models.ForeignKey(
        Item,
        on_delete=models.PROTECT,
        related_name="external_sku_mappings",
    )
    external_sku = models.CharField(max_length=150)
    external_sku_normalized = models.CharField(max_length=150, editable=False)
    external_product_name = models.CharField(max_length=255, blank=True)
    external_variation = models.CharField(max_length=255, blank=True)
    external_variation_normalized = models.CharField(max_length=255, blank=True, editable=False)
    conversion_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "external SKU mapping"
        ordering = ("store__code", "external_sku", "external_variation", "-effective_from")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "store",
                    "external_sku_normalized",
                    "external_variation_normalized",
                    "effective_from",
                ),
                name="channels_skumap_scope_start_unique",
            ),
            models.CheckConstraint(
                condition=Q(conversion_quantity__gt=0),
                name="channels_skumap_conversion_positive",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="channels_skumap_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=(
                    "store",
                    "external_sku_normalized",
                    "external_variation_normalized",
                    "is_active",
                ),
                name="channels_skumap_lookup_idx",
            ),
        ]

    def __str__(self) -> str:
        variation = f" / {self.external_variation}" if self.external_variation else ""
        return f"{self.store.code}: {self.external_sku}{variation} → {self.item.code}"
