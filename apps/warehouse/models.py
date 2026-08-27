from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel


class MovementDirection(models.TextChoices):
    IN = "IN", "Masuk"
    OUT = "OUT", "Keluar"


class MovementType(models.TextChoices):
    PRODUCTION_MATERIAL_ISSUE = "PRODUCTION_MATERIAL_ISSUE", "Issue Bahan Produksi"
    PRODUCTION_FINISHED_GOODS_RECEIPT = "PRODUCTION_FINISHED_GOODS_RECEIPT", "Terima Hasil Produksi"


class WarehouseDocumentState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class ValuationStatus(models.TextChoices):
    READY = "READY", "Ready"
    PENDING_VALUATION = "PENDING_VALUATION", "Menunggu Valuasi"
    BLOCKED = "BLOCKED", "Blocked"


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
