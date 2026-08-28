from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel


class MovementDirection(models.TextChoices):
    IN = "IN", "Masuk"
    OUT = "OUT", "Keluar"


class MovementType(models.TextChoices):
    PRODUCTION_MATERIAL_ISSUE = "PRODUCTION_MATERIAL_ISSUE", "Issue Bahan Produksi"
    PRODUCTION_FINISHED_GOODS_RECEIPT = "PRODUCTION_FINISHED_GOODS_RECEIPT", "Terima Hasil Produksi"
    PURCHASE_RECEIPT = "PURCHASE_RECEIPT", "Penerimaan Pembelian"
    SUBCONTRACT_RECEIPT = "SUBCONTRACT_RECEIPT", "Penerimaan Maklun"
    SALES_DELIVERY_ISSUE = "SALES_DELIVERY_ISSUE", "Pengeluaran Penjualan"
    OPNAME_GAIN = "OPNAME_GAIN", "Stock Opname Gain"
    OPNAME_LOSS = "OPNAME_LOSS", "Stock Opname Loss"
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT", "Penyesuaian Stok"
    INTERNAL_CONSUMPTION = "INTERNAL_CONSUMPTION", "Pemakaian Internal"
    SUPPLIER_RETURN = "SUPPLIER_RETURN", "Retur Supplier"
    OMNI_PACKING = "OMNI_PACKING", "Packing Omnichannel"


class WarehouseDocumentState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class ValuationStatus(models.TextChoices):
    READY = "READY", "Ready"
    PENDING_VALUATION = "PENDING_VALUATION", "Menunggu Valuasi"
    BLOCKED = "BLOCKED", "Blocked"


class OperationalDocumentState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    COUNTED = "COUNTED", "Counted"
    APPROVED = "APPROVED", "Approved"
    POSTED = "POSTED", "Posted"
    VOID = "VOID", "Void"
    REVERSED = "REVERSED", "Reversed"


class StockMovement(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    item = models.ForeignKey(
        "catalog.Item", on_delete=models.PROTECT, related_name="warehouse_movements"
    )
    warehouse = models.ForeignKey(
        "organizations.Warehouse", on_delete=models.PROTECT, related_name="stock_movements"
    )
    direction = models.CharField(max_length=3, choices=MovementDirection.choices)
    movement_type = models.CharField(max_length=48, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    uom_code_snapshot = models.CharField(max_length=20)
    unit_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    total_value = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    valuation_status = models.CharField(
        max_length=24, choices=ValuationStatus.choices, default=ValuationStatus.READY
    )
    source_module = models.CharField(max_length=64)
    source_type = models.CharField(max_length=64)
    source_document_id = models.CharField(max_length=64)
    source_line_id = models.CharField(max_length=64)
    source_key = models.CharField(max_length=255)
    transaction_date = models.DateField()
    posting_sequence = models.BigIntegerField(unique=True)
    posted_at = models.DateTimeField()
    state = models.CharField(
        max_length=12, choices=WarehouseDocumentState.choices, default=WarehouseDocumentState.POSTED
    )
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_stock_movements",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_stock_movements",
    )
    reversal_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal_movements"
    )
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="wh_move_qty_positive"),
            models.UniqueConstraint(
                fields=("legal_entity", "source_key", "direction", "movement_type"),
                name="wh_move_source_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "warehouse", "item", "posting_sequence"),
                name="wh_move_ledger_idx",
            ),
            models.Index(fields=("source_key", "state"), name="wh_move_source_state_idx"),
        ]


class WarehousePostingSequence(UUIDPrimaryKeyModel):
    singleton = models.BooleanField(default=True, unique=True)
    last_sequence = models.BigIntegerField(default=0)


class InventoryValuationState(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    warehouse = models.ForeignKey(
        "organizations.Warehouse", on_delete=models.PROTECT, related_name="valuation_states"
    )
    item = models.ForeignKey(
        "catalog.Item", on_delete=models.PROTECT, related_name="warehouse_valuation_states"
    )
    quantity_on_hand = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    inventory_value = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    average_unit_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    valuation_status = models.CharField(
        max_length=24, choices=ValuationStatus.choices, default=ValuationStatus.READY
    )
    last_movement_sequence = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "warehouse", "item"), name="wh_val_state_unique"
            ),
            models.CheckConstraint(
                condition=Q(quantity_on_hand__gte=0), name="wh_val_qty_nonnegative"
            ),
        ]
        indexes = [models.Index(fields=("legal_entity", "warehouse"), name="wh_val_entity_wh_idx")]


class WarehouseMaterialIssue(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("organizations.Warehouse", on_delete=models.PROTECT)
    issue_date = models.DateField()
    source_module = models.CharField(max_length=64, default="production")
    source_type = models.CharField(max_length=64, default="MATERIAL_REQUEST")
    work_order = models.ForeignKey("purchasing.WorkOrder", on_delete=models.PROTECT)
    state = models.CharField(
        max_length=12, choices=WarehouseDocumentState.choices, default=WarehouseDocumentState.DRAFT
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_warehouse_issues",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_warehouse_issues",
    )
    posted_at = models.DateTimeField(null=True, blank=True)


class WarehouseMaterialIssueLine(UUIDPrimaryKeyModel, TimeStampedModel):
    issue = models.ForeignKey(
        WarehouseMaterialIssue, on_delete=models.PROTECT, related_name="lines"
    )
    allocation = models.ForeignKey(
        "purchasing.WorkOrderMaterialAllocation", on_delete=models.PROTECT
    )
    output = models.ForeignKey("purchasing.WorkOrderOutput", on_delete=models.PROTECT)
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    source_key = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    uom_code_snapshot = models.CharField(max_length=20)
    sequence = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    total_value = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("issue", "sequence"), name="wh_issue_line_seq_unique"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="wh_issue_qty_positive"),
        ]
        indexes = [models.Index(fields=("allocation",), name="wh_issue_alloc_idx")]


class WarehouseReceipt(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("organizations.Warehouse", on_delete=models.PROTECT)
    receipt_date = models.DateField()
    source_module = models.CharField(max_length=64, default="production")
    source_type = models.CharField(max_length=64, default="PRODUCTION_HANDOVER")
    work_order = models.ForeignKey("purchasing.WorkOrder", on_delete=models.PROTECT)
    handover = models.ForeignKey("production.ProductionWarehouseHandover", on_delete=models.PROTECT)
    state = models.CharField(
        max_length=12, choices=WarehouseDocumentState.choices, default=WarehouseDocumentState.DRAFT
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_warehouse_receipts",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_warehouse_receipts",
    )
    posted_at = models.DateTimeField(null=True, blank=True)


class WarehouseReceiptLine(UUIDPrimaryKeyModel, TimeStampedModel):
    receipt = models.ForeignKey(WarehouseReceipt, on_delete=models.PROTECT, related_name="lines")
    handover_line = models.ForeignKey(
        "production.ProductionWarehouseHandoverLine", on_delete=models.PROTECT
    )
    output = models.ForeignKey("purchasing.WorkOrderOutput", on_delete=models.PROTECT)
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    source_key = models.CharField(max_length=255)
    accepted_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    uom_code_snapshot = models.CharField(max_length=20)
    valuation_status = models.CharField(
        max_length=24, choices=ValuationStatus.choices, default=ValuationStatus.PENDING_VALUATION
    )
    unit_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    total_value = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    sequence = models.PositiveIntegerField()
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("receipt", "sequence"), name="wh_receipt_line_seq_unique"
            ),
            models.CheckConstraint(
                condition=Q(accepted_quantity__gt=0), name="wh_receipt_qty_positive"
            ),
        ]
        indexes = [models.Index(fields=("handover_line",), name="wh_receipt_handover_idx")]


class WarehousePurchaseReceipt(UUIDPrimaryKeyModel, TimeStampedModel):
    """Physical receipt document for confirmed Purchase Order INVENTORY lines."""

    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("organizations.Warehouse", on_delete=models.PROTECT)
    purchase_order = models.ForeignKey("purchasing.PurchaseOrder", on_delete=models.PROTECT)
    vendor = models.ForeignKey("partners.BusinessPartner", on_delete=models.PROTECT)
    vendor_code_snapshot = models.CharField(max_length=40)
    vendor_name_snapshot = models.CharField(max_length=255)
    receipt_date = models.DateField()
    state = models.CharField(
        max_length=12, choices=WarehouseDocumentState.choices, default=WarehouseDocumentState.DRAFT
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_warehouse_purchase_receipts",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_warehouse_purchase_receipts",
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [
            ("post_warehousepurchasereceipt", "Can post Warehouse purchase receipt"),
            ("reverse_warehousepurchasereceipt", "Can reverse Warehouse purchase receipt"),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "state", "receipt_date"), name="wh_purch_rec_list_idx"
            )
        ]


class WarehousePurchaseReceiptLine(UUIDPrimaryKeyModel, TimeStampedModel):
    receipt = models.ForeignKey(
        WarehousePurchaseReceipt, on_delete=models.PROTECT, related_name="lines"
    )
    purchase_order_line = models.ForeignKey(
        "purchasing.PurchaseOrderLine",
        on_delete=models.PROTECT,
        related_name="warehouse_receipt_lines",
    )
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    item_code_snapshot = models.CharField(max_length=64)
    item_name_snapshot = models.CharField(max_length=255)
    uom_code_snapshot = models.CharField(max_length=20)
    purchase_category_code_snapshot = models.CharField(max_length=50)
    purchase_category_name_snapshot = models.CharField(max_length=150)
    accounting_treatment_snapshot = models.CharField(max_length=20)
    vendor_id_snapshot = models.CharField(max_length=64)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    unit_cost_snapshot = models.DecimalField(max_digits=24, decimal_places=6)
    total_value_snapshot = models.DecimalField(max_digits=24, decimal_places=6)
    source_key = models.CharField(max_length=255, unique=True)
    sequence = models.PositiveIntegerField()
    posted_movement = models.OneToOneField(
        StockMovement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_receipt_line",
    )
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("receipt", "sequence"), name="wh_purch_rec_line_seq_uq"
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="wh_purch_rec_qty_positive"),
            models.CheckConstraint(
                condition=Q(unit_cost_snapshot__gt=0), name="wh_purch_rec_cost_positive"
            ),
        ]
        indexes = [models.Index(fields=("purchase_order_line",), name="wh_purch_rec_po_line_idx")]


class WarehouseSubcontractReceipt(UUIDPrimaryKeyModel, TimeStampedModel):
    """Physical receipt document for an accepted Purchasing subcontract receipt."""

    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("organizations.Warehouse", on_delete=models.PROTECT)
    subcontract_receipt = models.ForeignKey(
        "purchasing.SubcontractReceipt", on_delete=models.PROTECT
    )
    vendor = models.ForeignKey("partners.BusinessPartner", on_delete=models.PROTECT)
    vendor_code_snapshot = models.CharField(max_length=40)
    vendor_name_snapshot = models.CharField(max_length=255)
    receipt_date = models.DateField()
    state = models.CharField(
        max_length=12, choices=WarehouseDocumentState.choices, default=WarehouseDocumentState.DRAFT
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_warehouse_subcontract_receipts",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_warehouse_subcontract_receipts",
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [
            ("post_warehousesubcontractreceipt", "Can post Warehouse subcontract receipt"),
            ("reverse_warehousesubcontractreceipt", "Can reverse Warehouse subcontract receipt"),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "state", "receipt_date"), name="wh_subrec_list_idx"
            )
        ]


class WarehouseSubcontractReceiptLine(UUIDPrimaryKeyModel, TimeStampedModel):
    receipt = models.ForeignKey(
        WarehouseSubcontractReceipt, on_delete=models.PROTECT, related_name="lines"
    )
    subcontract_receipt_line = models.ForeignKey(
        "purchasing.SubcontractReceiptOutputLine",
        on_delete=models.PROTECT,
        related_name="warehouse_receipt_lines",
    )
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    item_code_snapshot = models.CharField(max_length=64)
    item_name_snapshot = models.CharField(max_length=255)
    uom_code_snapshot = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    quality_pass_quantity_snapshot = models.DecimalField(max_digits=18, decimal_places=6)
    unit_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    total_value = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    valuation_status = models.CharField(
        max_length=24, choices=ValuationStatus.choices, default=ValuationStatus.PENDING_VALUATION
    )
    source_key = models.CharField(max_length=255, unique=True)
    sequence = models.PositiveIntegerField()
    posted_movement = models.OneToOneField(
        StockMovement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="subcontract_receipt_line",
    )
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("receipt", "sequence"), name="wh_subrec_line_seq_uq"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="wh_subrec_qty_positive"),
        ]
        indexes = [
            models.Index(fields=("subcontract_receipt_line",), name="wh_subrec_source_line_idx")
        ]


class WarehouseSalesIssue(UUIDPrimaryKeyModel, TimeStampedModel):
    """Warehouse physical issue document sourced from a POSTED Sales Delivery."""

    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("organizations.Warehouse", on_delete=models.PROTECT)
    sales_delivery = models.ForeignKey("sales.SalesDelivery", on_delete=models.PROTECT)
    customer = models.ForeignKey("partners.BusinessPartner", on_delete=models.PROTECT)
    customer_code_snapshot = models.CharField(max_length=40)
    customer_name_snapshot = models.CharField(max_length=255)
    issue_date = models.DateField()
    state = models.CharField(
        max_length=12, choices=WarehouseDocumentState.choices, default=WarehouseDocumentState.DRAFT
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_warehouse_sales_issues",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_warehouse_sales_issues",
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [
            ("post_warehousesalesissue", "Can post Warehouse sales issue"),
            ("reverse_warehousesalesissue", "Can reverse Warehouse sales issue"),
        ]
        indexes = [
            models.Index(fields=("legal_entity", "state", "issue_date"), name="wh_sales_issue_idx")
        ]


class WarehouseSalesIssueLine(UUIDPrimaryKeyModel, TimeStampedModel):
    issue = models.ForeignKey(WarehouseSalesIssue, on_delete=models.PROTECT, related_name="lines")
    sales_delivery_line = models.ForeignKey(
        "sales.SalesDeliveryLine", on_delete=models.PROTECT, related_name="warehouse_issue_lines"
    )
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    sales_order_id_snapshot = models.CharField(max_length=64)
    sales_order_line_id_snapshot = models.CharField(max_length=64)
    delivery_id_snapshot = models.CharField(max_length=64)
    delivery_line_id_snapshot = models.CharField(max_length=64)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    uom_code_snapshot = models.CharField(max_length=20)
    source_key = models.CharField(max_length=255, unique=True)
    sequence = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    total_value = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    posted_movement = models.OneToOneField(
        StockMovement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sales_issue_line",
    )
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("issue", "sequence"), name="wh_sales_issue_line_seq_uq"
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="wh_sales_issue_qty_positive"),
        ]
        indexes = [models.Index(fields=("sales_delivery_line",), name="wh_sales_delivery_line_idx")]


class StockCount(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("organizations.Warehouse", on_delete=models.PROTECT)
    count_date = models.DateField()
    state = models.CharField(
        max_length=12,
        choices=OperationalDocumentState.choices,
        default=OperationalDocumentState.DRAFT,
    )
    snapshot_sequence = models.BigIntegerField(default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_stock_counts",
    )
    submitted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="submitted_stock_counts",
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_stock_counts",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_stock_counts",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [
            ("approve_stockcount", "Can approve stock count"),
            ("post_stockcount", "Can post stock count"),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "warehouse", "state", "count_date"),
                name="wh_count_list_idx",
            )
        ]


class StockCountLine(UUIDPrimaryKeyModel, TimeStampedModel):
    count = models.ForeignKey(StockCount, on_delete=models.PROTECT, related_name="lines")
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    system_qty_snapshot = models.DecimalField(max_digits=18, decimal_places=6)
    counted_qty = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    variance_qty = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    uom_code_snapshot = models.CharField(max_length=20)
    reason = models.TextField(blank=True)
    sequence = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("count", "item"), name="wh_count_item_uq"),
            models.UniqueConstraint(fields=("count", "sequence"), name="wh_count_line_seq_uq"),
            models.CheckConstraint(
                condition=Q(system_qty_snapshot__gte=0), name="wh_count_system_qty_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(counted_qty__isnull=True) | Q(counted_qty__gte=0),
                name="wh_count_counted_qty_nonnegative",
            ),
        ]


class InventoryAdjustment(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("organizations.Warehouse", on_delete=models.PROTECT)
    adjustment_date = models.DateField()
    state = models.CharField(
        max_length=12,
        choices=OperationalDocumentState.choices,
        default=OperationalDocumentState.DRAFT,
    )
    reason = models.TextField()
    reference = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_inventory_adjustments",
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_inventory_adjustments",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_inventory_adjustments",
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [
            ("approve_inventoryadjustment", "Can approve inventory adjustment"),
            ("post_inventoryadjustment", "Can post inventory adjustment"),
            ("reverse_inventoryadjustment", "Can reverse inventory adjustment"),
        ]


class InventoryAdjustmentLine(UUIDPrimaryKeyModel, TimeStampedModel):
    adjustment = models.ForeignKey(
        InventoryAdjustment, on_delete=models.PROTECT, related_name="lines"
    )
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    direction = models.CharField(max_length=3, choices=MovementDirection.choices)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    uom_code_snapshot = models.CharField(max_length=20)
    cost_treatment = models.CharField(max_length=40)
    unit_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    total_value = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    source_key = models.CharField(max_length=255, unique=True)
    sequence = models.PositiveIntegerField()
    posted_movement = models.OneToOneField(
        StockMovement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="adjustment_line",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("adjustment", "sequence"), name="wh_adjust_line_seq_uq"
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="wh_adjust_qty_positive"),
        ]


class InternalConsumption(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("organizations.Warehouse", on_delete=models.PROTECT)
    transaction_date = models.DateField()
    purpose = models.CharField(max_length=255)
    reason = models.TextField()
    reference = models.CharField(max_length=255, blank=True)
    cost_center = models.ForeignKey(
        "organizations.CostCenter", null=True, blank=True, on_delete=models.PROTECT
    )
    project = models.ForeignKey("projects.Project", null=True, blank=True, on_delete=models.PROTECT)
    state = models.CharField(
        max_length=12, choices=WarehouseDocumentState.choices, default=WarehouseDocumentState.DRAFT
    )
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_internal_consumptions",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_internal_consumptions",
    )
    posted_at = models.DateTimeField(null=True, blank=True)


class InternalConsumptionLine(UUIDPrimaryKeyModel, TimeStampedModel):
    consumption = models.ForeignKey(
        InternalConsumption, on_delete=models.PROTECT, related_name="lines"
    )
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    uom_code_snapshot = models.CharField(max_length=20)
    source_key = models.CharField(max_length=255, unique=True)
    sequence = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    total_value = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    posted_movement = models.OneToOneField(
        StockMovement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="internal_consumption_line",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("consumption", "sequence"), name="wh_internal_line_seq_uq"
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="wh_internal_qty_positive"),
        ]


class SupplierReturn(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    warehouse = models.ForeignKey("organizations.Warehouse", on_delete=models.PROTECT)
    supplier = models.ForeignKey("partners.BusinessPartner", on_delete=models.PROTECT)
    purchase_order = models.ForeignKey(
        "purchasing.PurchaseOrder", null=True, blank=True, on_delete=models.PROTECT
    )
    transaction_date = models.DateField()
    reason = models.TextField()
    reference = models.CharField(max_length=255, blank=True)
    state = models.CharField(
        max_length=12, choices=WarehouseDocumentState.choices, default=WarehouseDocumentState.DRAFT
    )
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_supplier_returns",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_supplier_returns",
    )
    posted_at = models.DateTimeField(null=True, blank=True)


class SupplierReturnLine(UUIDPrimaryKeyModel, TimeStampedModel):
    supplier_return = models.ForeignKey(
        SupplierReturn, on_delete=models.PROTECT, related_name="lines"
    )
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    purchase_order_line = models.ForeignKey(
        "purchasing.PurchaseOrderLine", null=True, blank=True, on_delete=models.PROTECT
    )
    purchase_receipt_line = models.ForeignKey(
        WarehousePurchaseReceiptLine, null=True, blank=True, on_delete=models.PROTECT
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    uom_code_snapshot = models.CharField(max_length=20)
    source_key = models.CharField(max_length=255, unique=True)
    sequence = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    total_value = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    posted_movement = models.OneToOneField(
        StockMovement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="supplier_return_line",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("supplier_return", "sequence"), name="wh_supplier_return_line_uq"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="wh_supplier_return_qty_positive"
            ),
        ]


# Public semantic aliases used by source adapters and downstream tests.  The
# concrete model names retain the Warehouse ownership boundary in Django's
# migration/app labels.
PurchaseReceipt = WarehousePurchaseReceipt
PurchaseReceiptLine = WarehousePurchaseReceiptLine
SubcontractWarehouseReceipt = WarehouseSubcontractReceipt
SubcontractWarehouseReceiptLine = WarehouseSubcontractReceiptLine
SalesIssue = WarehouseSalesIssue
SalesIssueLine = WarehouseSalesIssueLine
StockOpname = StockCount
StockOpnameLine = StockCountLine
