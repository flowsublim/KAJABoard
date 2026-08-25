from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.models import EffectivePeriodModel, TimeStampedModel, UUIDPrimaryKeyModel
from apps.organizations.models import LegalEntity
from apps.partners.models import BusinessPartner


class UOM(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Unit of measure with a configurable quantity display/storage precision."""

    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    dimension = models.CharField(
        max_length=40,
        help_text="Stable dimension key such as COUNT, LENGTH, WEIGHT, or VOLUME.",
    )
    decimal_places = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "unit of measure"
        verbose_name_plural = "units of measure"
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(Lower("code"), name="catalog_uom_code_ci_unique"),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="catalog_uom_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("dimension", "is_active"), name="cat_uom_dim_active_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class ItemCategory(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Classification only; it never determines stock or accounting behavior."""

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=150)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "item categories"
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(Lower("code"), name="catalog_category_code_ci_unique"),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="catalog_category_effective_period_valid",
            ),
        ]
        indexes = [models.Index(fields=("parent", "is_active"), name="cat_category_parent_idx")]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class ItemKind(models.TextChoices):
    PRODUCT = "PRODUCT", "Product"
    MATERIAL = "MATERIAL", "Material"
    SERVICE = "SERVICE", "Service"
    PACKAGING = "PACKAGING", "Packaging"
    OTHER = "OTHER", "Other"


class Item(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Canonical SKU/material identity; quantities remain owned by future Warehouse."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="items",
    )
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    item_kind = models.CharField(max_length=20, choices=ItemKind.choices, default=ItemKind.PRODUCT)
    category = models.ForeignKey(
        ItemCategory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="category_items",
    )
    subcategory = models.ForeignKey(
        ItemCategory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="subcategory_items",
    )
    uom = models.ForeignKey(UOM, on_delete=models.PROTECT, related_name="items")
    parent_item = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="variants",
        help_text="Optional parent product. Every variant remains a canonical Item.",
    )
    variant_attributes = models.JSONField(default=dict, blank=True)
    sales_eligible = models.BooleanField(default=False)
    purchase_eligible = models.BooleanField(default=False)
    production_eligible = models.BooleanField(default=False)
    inventory_eligible = models.BooleanField(default=False)
    tax_classification = models.CharField(max_length=64, blank=True)
    valuation_policy = models.CharField(max_length=64, blank=True)
    minimum_stock = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    lead_time_days = models.PositiveIntegerField(default=0)
    preferred_vendor = models.ForeignKey(
        BusinessPartner,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="preferred_items",
    )
    reference_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    reference_selling_price = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(Lower("code"), name="catalog_item_code_ci_unique"),
            models.CheckConstraint(
                condition=Q(minimum_stock__gte=0),
                name="catalog_item_minimum_stock_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(reference_cost__gte=0),
                name="catalog_item_reference_cost_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(reference_selling_price__gte=0),
                name="catalog_item_selling_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="catalog_item_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "is_active"), name="catalog_item_entity_active_idx"
            ),
            models.Index(fields=("item_kind", "is_active"), name="catalog_item_kind_active_idx"),
            models.Index(
                fields=("parent_item", "is_active"), name="catalog_item_parent_active_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"
