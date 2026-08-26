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


class SalesDeliveryState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"
    CANCELLED = "CANCELLED", "Cancelled"


class InvoiceSourceMode(models.TextChoices):
    DELIVERY = "DELIVERY", "Delivery"
    SALES_ORDER = "SALES_ORDER", "Sales Order exception"


class SalesInvoiceDocumentKind(models.TextChoices):
    INVOICE = "INVOICE", "Invoice"
    PROFORMA = "PROFORMA", "Proforma"


class SalesInvoiceState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CONFIRMED = "CONFIRMED", "Confirmed"
    CANCELLED = "CANCELLED", "Cancelled"


class CreditControlStatus(models.TextChoices):
    NOT_AVAILABLE = "NOT_AVAILABLE", "Finance source unavailable"
    NOT_CONFIGURED = "NOT_CONFIGURED", "Credit limit not configured"
    PASSED = "PASSED", "Passed"
    HELD = "HELD", "Held"
    OVERRIDDEN = "OVERRIDDEN", "Overridden"


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


class SalesOrderCreditControl(UUIDPrimaryKeyModel, TimeStampedModel):
    """Sales-side evaluation snapshot; Finance remains the authority for exposure balances."""

    sales_order = models.OneToOneField(
        SalesOrder, on_delete=models.PROTECT, related_name="credit_control"
    )
    customer = models.ForeignKey(
        BusinessPartner, on_delete=models.PROTECT, related_name="sales_credit_controls"
    )
    legal_entity = models.ForeignKey(
        LegalEntity, on_delete=models.PROTECT, related_name="sales_credit_controls"
    )
    status = models.CharField(max_length=20, choices=CreditControlStatus.choices)
    credit_limit_snapshot = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    outstanding_snapshot = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    order_exposure_snapshot = models.DecimalField(max_digits=18, decimal_places=2)
    source_available = models.BooleanField(default=False)
    source_name = models.CharField(max_length=100)
    evaluated_at = models.DateTimeField()
    evaluated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="evaluated_sales_credit_controls",
    )
    override_reason = models.TextField(blank=True)
    overridden_at = models.DateTimeField(null=True, blank=True)
    overridden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="overridden_sales_credit_controls",
    )

    class Meta:
        permissions = [
            ("override_salesorder_credit", "Can override Sales Order credit hold"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(order_exposure_snapshot__gte=0), name="sales_credit_order_nonneg"
            ),
            models.CheckConstraint(
                condition=Q(credit_limit_snapshot__isnull=True) | Q(credit_limit_snapshot__gte=0),
                name="sales_credit_limit_nonneg",
            ),
            models.CheckConstraint(
                condition=Q(outstanding_snapshot__isnull=True) | Q(outstanding_snapshot__gte=0),
                name="sales_credit_outstanding_nonneg",
            ),
        ]
        indexes = [
            models.Index(fields=("customer", "status"), name="sales_credit_customer_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.sales_order.document_number} / {self.status}"


class SalesDelivery(UUIDPrimaryKeyModel, TimeStampedModel):
    """Commercial Surat Jalan. POSTED exposes a Warehouse candidate, never a movement."""

    legal_entity = models.ForeignKey(
        LegalEntity, on_delete=models.PROTECT, related_name="sales_deliveries"
    )
    document_allocation = models.OneToOneField(
        DocumentNumberAllocation, on_delete=models.PROTECT, related_name="sales_delivery"
    )
    document_number = models.CharField(max_length=120)
    delivery_date = models.DateField()
    customer = models.ForeignKey(
        BusinessPartner, on_delete=models.PROTECT, related_name="sales_deliveries"
    )
    customer_code_snapshot = models.CharField(max_length=40)
    customer_name_snapshot = models.CharField(max_length=255)
    customer_legal_name_snapshot = models.CharField(max_length=255, blank=True)
    destination_snapshot = models.TextField(blank=True)
    expedition_reference = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)
    state = models.CharField(
        max_length=20, choices=SalesDeliveryState.choices, default=SalesDeliveryState.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_sales_deliveries",
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_sales_deliveries",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cancelled_sales_deliveries",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-delivery_date", "-created_at")
        permissions = [
            ("post_salesdelivery", "Can post sales delivery"),
            ("cancel_salesdelivery", "Can cancel sales delivery"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "document_number"),
                name="sales_del_entity_doc_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "state", "delivery_date"),
                name="sales_delivery_list_idx",
            ),
            models.Index(
                fields=("customer", "state", "delivery_date"),
                name="sales_delivery_customer_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.document_number


class SalesDeliveryLine(UUIDPrimaryKeyModel, TimeStampedModel):
    """Immutable lineage anchor between a delivery and a stable Sales Order line."""

    sales_delivery = models.ForeignKey(
        SalesDelivery, on_delete=models.PROTECT, related_name="lines"
    )
    source_sales_order_line = models.ForeignKey(
        SalesOrderLine, on_delete=models.PROTECT, related_name="delivery_lines"
    )
    line_number = models.PositiveIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="sales_delivery_lines")
    source_sales_order_number_snapshot = models.CharField(max_length=120)
    item_code_snapshot = models.CharField(max_length=64)
    item_name_snapshot = models.CharField(max_length=255)
    description_snapshot = models.TextField(blank=True)
    uom_code_snapshot = models.CharField(max_length=20)
    ordered_quantity_snapshot = models.DecimalField(max_digits=18, decimal_places=6)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("line_number", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("sales_delivery", "line_number"),
                name="sales_del_line_no_unique",
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sales_del_line_qty_pos"),
            models.CheckConstraint(
                condition=Q(ordered_quantity_snapshot__gt=0),
                name="sales_del_line_ordered_qty_pos",
            ),
        ]
        indexes = [
            models.Index(
                fields=("source_sales_order_line", "sales_delivery"),
                name="sales_delivery_line_source_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sales_delivery.document_number} line {self.line_number}"


class SalesInvoice(UUIDPrimaryKeyModel, TimeStampedModel):
    """Commercial invoice source only; Finance owns AR, journals, and revenue recognition."""

    legal_entity = models.ForeignKey(
        LegalEntity, on_delete=models.PROTECT, related_name="sales_invoices"
    )
    document_allocation = models.OneToOneField(
        DocumentNumberAllocation, on_delete=models.PROTECT, related_name="sales_invoice"
    )
    document_number = models.CharField(max_length=120)
    invoice_date = models.DateField()
    customer = models.ForeignKey(
        BusinessPartner, on_delete=models.PROTECT, related_name="sales_invoices"
    )
    customer_code_snapshot = models.CharField(max_length=40)
    customer_name_snapshot = models.CharField(max_length=255)
    customer_legal_name_snapshot = models.CharField(max_length=255, blank=True)
    source_mode = models.CharField(max_length=20, choices=InvoiceSourceMode.choices)
    document_kind = models.CharField(
        max_length=12,
        choices=SalesInvoiceDocumentKind.choices,
        default=SalesInvoiceDocumentKind.INVOICE,
    )
    source_exception_reason = models.TextField(blank=True)
    state = models.CharField(
        max_length=20, choices=SalesInvoiceState.choices, default=SalesInvoiceState.DRAFT
    )
    currency = models.CharField(max_length=3, default="IDR")
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
        related_name="created_sales_invoices",
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="confirmed_sales_invoices",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cancelled_sales_invoices",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-invoice_date", "-created_at")
        permissions = [
            ("confirm_salesinvoice", "Can confirm sales invoice source"),
            ("cancel_salesinvoice", "Can cancel sales invoice source"),
            ("create_salesorder_invoice", "Can create Sales Order based invoice source"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "document_number"),
                name="sales_inv_entity_doc_unique",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0)
                & Q(discount_total__gte=0)
                & Q(tax_total__gte=0)
                & Q(freight_amount__gte=0)
                & Q(grand_total__gte=0),
                name="sales_inv_totals_nonneg",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "state", "invoice_date"), name="sales_invoice_list_idx"
            ),
            models.Index(
                fields=("customer", "state", "invoice_date"), name="sales_invoice_customer_idx"
            ),
            models.Index(
                fields=("source_mode", "document_kind", "state"), name="sales_invoice_source_idx"
            ),
        ]

    @property
    def is_proforma(self) -> bool:
        return self.document_kind == SalesInvoiceDocumentKind.PROFORMA

    def __str__(self) -> str:
        return self.document_number


class SalesInvoiceLine(UUIDPrimaryKeyModel, TimeStampedModel):
    """Stable commercial source line preserving exact order and optional delivery lineage."""

    sales_invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="lines")
    source_sales_order_line = models.ForeignKey(
        SalesOrderLine, on_delete=models.PROTECT, related_name="invoice_lines"
    )
    source_sales_delivery_line = models.ForeignKey(
        SalesDeliveryLine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="invoice_lines",
    )
    line_number = models.PositiveIntegerField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="sales_invoice_lines")
    source_sales_order_number_snapshot = models.CharField(max_length=120)
    source_sales_delivery_number_snapshot = models.CharField(max_length=120, blank=True)
    item_code_snapshot = models.CharField(max_length=64)
    item_name_snapshot = models.CharField(max_length=255)
    description_snapshot = models.TextField(blank=True)
    uom_code_snapshot = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
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
                fields=("sales_invoice", "line_number"),
                name="sales_inv_line_no_unique",
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sales_inv_line_qty_pos"),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="sales_inv_line_price_nonneg"
            ),
            models.CheckConstraint(
                condition=Q(discount_value__gte=0), name="sales_inv_line_discount_nonneg"
            ),
            models.CheckConstraint(condition=Q(tax_rate__gte=0), name="sales_inv_line_tax_nonneg"),
        ]
        indexes = [
            models.Index(
                fields=("source_sales_delivery_line", "sales_invoice"),
                name="sales_inv_line_delivery_idx",
            ),
            models.Index(
                fields=("source_sales_order_line", "sales_invoice"),
                name="sales_inv_line_order_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sales_invoice.document_number} line {self.line_number}"
