from django.db import models
from django.db.models import Q

from apps.catalog.models import Item
from apps.core.models import (
    DocumentNumberAllocation,
    EffectivePeriodModel,
    TimeStampedModel,
    UUIDPrimaryKeyModel,
)
from apps.organizations.models import BusinessUnit, CostCenter, LegalEntity
from apps.partners.models import BusinessPartner


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


class PurchaseOrderState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CONFIRMED = "CONFIRMED", "Confirmed"
    CANCELLED = "CANCELLED", "Cancelled"
    CLOSED = "CLOSED", "Closed"


class PurchaseOrder(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(
        LegalEntity, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    document_allocation = models.OneToOneField(
        DocumentNumberAllocation, on_delete=models.PROTECT, related_name="purchase_order"
    )
    document_number = models.CharField(max_length=120)
    document_date = models.DateField()
    vendor = models.ForeignKey(
        BusinessPartner, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    vendor_code_snapshot = models.CharField(max_length=40)
    vendor_name_snapshot = models.CharField(max_length=255)
    vendor_reference = models.CharField(max_length=120, blank=True)
    business_unit = models.ForeignKey(
        BusinessUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    project = models.ForeignKey(
        "projects.Project",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    expected_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="IDR")
    state = models.CharField(
        max_length=20, choices=PurchaseOrderState.choices, default=PurchaseOrderState.DRAFT
    )
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    freight_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_purchase_orders",
    )
    confirmed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="confirmed_purchase_orders",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cancelled_purchase_orders",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [
            ("confirm_purchaseorder", "Can confirm purchase order"),
            ("cancel_purchaseorder", "Can cancel purchase order"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "document_number"), name="po_entity_document_unique"
            )
        ]
        indexes = [
            models.Index(fields=("legal_entity", "state", "document_date"), name="po_list_idx")
        ]


class PurchaseOrderLine(UUIDPrimaryKeyModel, TimeStampedModel):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="lines"
    )
    line_number = models.PositiveIntegerField()
    item = models.ForeignKey(
        Item, null=True, blank=True, on_delete=models.PROTECT, related_name="purchase_order_lines"
    )
    purchase_category = models.ForeignKey(
        PurchaseCategory, on_delete=models.PROTECT, related_name="purchase_order_lines"
    )
    item_code_snapshot = models.CharField(max_length=64, blank=True)
    item_name_snapshot = models.CharField(max_length=255, blank=True)
    uom_code_snapshot = models.CharField(max_length=20, blank=True)
    category_code_snapshot = models.CharField(max_length=50)
    category_name_snapshot = models.CharField(max_length=150)
    accounting_treatment_snapshot = models.CharField(
        max_length=20, choices=AccountingTreatment.choices
    )
    cost_center_snapshot = models.ForeignKey(
        CostCenter,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_order_line_snapshots",
    )
    inventory_classification_snapshot = models.CharField(max_length=80, blank=True)
    asset_class_reference_snapshot = models.CharField(max_length=80, blank=True)
    snapshot_production = models.BooleanField(default=False)
    accounting_mapping_key_snapshot = models.CharField(max_length=80, blank=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    line_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    line_tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("purchase_order", "line_number"), name="po_line_number_unique"
            )
        ]
        indexes = [
            models.Index(
                fields=("purchase_order", "accounting_treatment_snapshot"),
                name="po_line_treatment_idx",
            )
        ]
