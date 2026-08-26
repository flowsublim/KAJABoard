from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import Item
from apps.core.models import DocumentNumberAllocation, TimeStampedModel, UUIDPrimaryKeyModel
from apps.organizations.models import BusinessUnit, LegalEntity
from apps.partners.models import BusinessPartner


class SalesOrderState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CONFIRMED = "CONFIRMED", "Confirmed"
    ON_HOLD = "ON_HOLD", "On hold"
    CANCELLED = "CANCELLED", "Cancelled"
    CLOSED = "CLOSED", "Closed"


class DiscountType(models.TextChoices):
    AMOUNT = "AMOUNT", "Amount"
    PERCENT = "PERCENT", "Percent"


class SalesOrder(UUIDPrimaryKeyModel, TimeStampedModel):
    """Commercial B2B order source. It deliberately creates no stock or finance entry."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="sales_orders",
    )
    document_allocation = models.OneToOneField(
        DocumentNumberAllocation,
        on_delete=models.PROTECT,
        related_name="sales_order",
    )
    document_number = models.CharField(max_length=120)
    document_date = models.DateField()
    customer = models.ForeignKey(
        BusinessPartner,
        on_delete=models.PROTECT,
        related_name="sales_orders",
    )
    customer_code_snapshot = models.CharField(max_length=40)
    customer_name_snapshot = models.CharField(max_length=255)
    customer_legal_name_snapshot = models.CharField(max_length=255, blank=True)
    customer_po_reference = models.CharField(max_length=120, blank=True)
    business_unit = models.ForeignKey(
        BusinessUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sales_orders",
    )
    requested_delivery_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="IDR")
    state = models.CharField(
        max_length=20,
        choices=SalesOrderState.choices,
        default=SalesOrderState.DRAFT,
    )
    notes = models.TextField(blank=True)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    discount_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    tax_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    freight_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    grand_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_sales_orders",
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="confirmed_sales_orders",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cancelled_sales_orders",
    )

    class Meta:
        ordering = ("-document_date", "-created_at")
        permissions = [
            ("confirm_salesorder", "Can confirm sales order"),
            ("cancel_salesorder", "Can cancel sales order"),
            ("hold_salesorder", "Can hold or release sales order"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "document_number"),
                name="sales_order_entity_document_number_unique",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0)
                & Q(discount_total__gte=0)
                & Q(tax_total__gte=0)
                & Q(freight_amount__gte=0)
                & Q(grand_total__gte=0),
                name="sales_order_totals_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "state", "document_date"), name="sales_order_list_idx"
            ),
            models.Index(
                fields=("customer", "state", "document_date"), name="sales_order_customer_idx"
            ),
        ]

    def __str__(self) -> str:
        return self.document_number


class SalesOrderLine(UUIDPrimaryKeyModel, TimeStampedModel):
    """Stable commercial line identity retained for later delivery and invoice lineage."""

    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="lines")
    line_number = models.PositiveIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="sales_order_lines")
    item_code_snapshot = models.CharField(max_length=64)
    item_name_snapshot = models.CharField(max_length=255)
    description_snapshot = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    uom_code_snapshot = models.CharField(max_length=20)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    discount_type = models.CharField(
        max_length=10,
        choices=DiscountType.choices,
        default=DiscountType.AMOUNT,
    )
    discount_value = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    tax_classification_snapshot = models.CharField(max_length=64, blank=True)
    tax_rate = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0"))
    line_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    line_discount_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0")
    )
    line_tax_base = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    line_tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    line_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("line_number", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("sales_order", "line_number"),
                name="sales_order_line_number_unique",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="sales_order_line_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="sales_order_line_price_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(discount_value__gte=0), name="sales_order_line_discount_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(tax_rate__gte=0), name="sales_order_line_tax_nonnegative"
            ),
        ]
        indexes = [
            models.Index(fields=("sales_order", "item"), name="sales_order_line_item_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.sales_order.document_number} line {self.line_number}"
