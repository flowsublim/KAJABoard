from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel


class OmniImportBatchStatus(models.TextChoices):
    PREVIEW = "PREVIEW", "Preview"
    READY = "READY", "Ready"
    PARTIAL = "PARTIAL", "Partial"
    IMPORTED = "IMPORTED", "Imported"
    CONFLICT = "CONFLICT", "Conflict"


class OmniRowStatus(models.TextChoices):
    VALID = "VALID", "Valid"
    REJECTED = "REJECTED", "Rejected"
    IMPORTED = "IMPORTED", "Imported"


class OmniMappingStatus(models.TextChoices):
    READY = "READY", "Ready"
    UNMAPPED_STORE = "UNMAPPED_STORE", "Unmapped store"
    UNMAPPED_SKU = "UNMAPPED_SKU", "Unmapped SKU"
    INVALID_QTY = "INVALID_QTY", "Invalid quantity"
    INVALID_ORDER_DATE = "INVALID_ORDER_DATE", "Invalid order date"
    INVALID_COMPLETION_DATE = "INVALID_COMPLETION_DATE", "Invalid completion date"
    MAPPING_INACTIVE = "MAPPING_INACTIVE", "Mapping inactive"
    DUPLICATE_SOURCE = "DUPLICATE_SOURCE", "Duplicate source row"
    SOURCE_CHANGED = "SOURCE_CHANGED", "Source changed"


class OmniOperationalStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    RETURNED = "RETURNED", "Returned"
    REFUNDED = "REFUNDED", "Refunded"
    UNKNOWN = "UNKNOWN", "Unknown"


class OmniPackingState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    READY = "READY", "Ready"
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class OmniExceptionState(models.TextChoices):
    OPEN = "OPEN", "Open"
    RESOLVED = "RESOLVED", "Resolved"


class OmniImportBatch(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    source_type = models.CharField(max_length=60, default="BIGSELLER_ORDER")
    source_filename = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64)
    imported_at = models.DateTimeField(null=True, blank=True)
    imported_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_imports",
    )
    status = models.CharField(
        max_length=20, choices=OmniImportBatchStatus.choices, default=OmniImportBatchStatus.PREVIEW
    )
    row_count = models.PositiveIntegerField(default=0)
    accepted_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    replay_count = models.PositiveIntegerField(default=0)
    idempotency_key = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        permissions = [
            ("import_omniimportbatch", "Can import Omnichannel orders"),
            ("commit_omniimportbatch", "Can commit Omnichannel imports"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_type", "file_hash"),
                name="omni_import_entity_type_hash_uq",
            )
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "status", "-created_at"), name="omni_import_list_idx"
            )
        ]


class OmniImportRow(UUIDPrimaryKeyModel, TimeStampedModel):
    batch = models.ForeignKey(OmniImportBatch, on_delete=models.PROTECT, related_name="rows")
    row_number = models.PositiveIntegerField()
    source_row_key = models.CharField(max_length=255)
    external_order_number = models.CharField(max_length=150, blank=True)
    external_store_name = models.CharField(max_length=255, blank=True)
    marketplace = models.CharField(max_length=80, blank=True)
    external_sku = models.CharField(max_length=150, blank=True)
    external_sku_normalized = models.CharField(max_length=150, blank=True)
    product = models.CharField(max_length=255, blank=True)
    variation = models.CharField(max_length=255, blank=True)
    variation_normalized = models.CharField(max_length=255, blank=True)
    marketplace_quantity = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    source_subtotal = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    order_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    tracking_number = models.CharField(max_length=160, blank=True)
    raw_status = models.CharField(max_length=120, blank=True)
    normalized_status = models.CharField(
        max_length=20, choices=OmniOperationalStatus.choices, default=OmniOperationalStatus.UNKNOWN
    )
    resolved_store = models.ForeignKey(
        "channels.Store", null=True, blank=True, on_delete=models.PROTECT
    )
    resolved_mapping = models.ForeignKey(
        "channels.ExternalSKUMap", null=True, blank=True, on_delete=models.PROTECT
    )
    resolved_item = models.ForeignKey(
        "catalog.Item", null=True, blank=True, on_delete=models.PROTECT
    )
    conversion_quantity = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    mapping_status = models.CharField(max_length=32, choices=OmniMappingStatus.choices)
    row_status = models.CharField(max_length=12, choices=OmniRowStatus.choices)
    exception_code = models.CharField(max_length=40, blank=True)
    exception_message = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("batch", "source_row_key"), name="omni_import_row_identity_uq"
            ),
        ]
        indexes = [
            models.Index(fields=("batch", "row_status"), name="omni_import_row_status_idx"),
            models.Index(
                fields=("external_order_number", "external_sku_normalized"),
                name="omni_import_row_source_idx",
            ),
        ]


class OmniOrder(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(
        "organizations.LegalEntity", on_delete=models.PROTECT, related_name="omni_orders"
    )
    source_batch = models.ForeignKey(
        OmniImportBatch, null=True, blank=True, on_delete=models.PROTECT, related_name="orders"
    )
    marketplace = models.CharField(max_length=80)
    external_store_name = models.CharField(max_length=255)
    store = models.ForeignKey(
        "channels.Store",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_orders",
    )
    store_code_snapshot = models.CharField(max_length=50, blank=True)
    store_name_snapshot = models.CharField(max_length=150, blank=True)
    store_channel_snapshot = models.CharField(max_length=50, blank=True)
    store_mapping_snapshot = models.JSONField(default=dict, blank=True)
    external_order_number = models.CharField(max_length=150)
    source_identity_key = models.CharField(max_length=400)
    order_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    raw_status = models.CharField(max_length=120, blank=True)
    normalized_status = models.CharField(
        max_length=20, choices=OmniOperationalStatus.choices, default=OmniOperationalStatus.UNKNOWN
    )
    tracking_number = models.CharField(max_length=160, blank=True)
    mapping_status = models.CharField(
        max_length=32, choices=OmniMappingStatus.choices, default=OmniMappingStatus.READY
    )
    source_sync_status = models.CharField(
        max_length=32, choices=OmniMappingStatus.choices, default=OmniMappingStatus.READY
    )
    last_source_hash = models.CharField(max_length=64, blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_identity_key"), name="omni_order_source_identity_uq"
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "order_date", "normalized_status"),
                name="omni_order_operational_idx",
            ),
            models.Index(fields=("legal_entity", "mapping_status"), name="omni_order_mapping_idx"),
        ]


class OmniOrderLine(UUIDPrimaryKeyModel, TimeStampedModel):
    order = models.ForeignKey(OmniOrder, on_delete=models.PROTECT, related_name="lines")
    source_row_key = models.CharField(max_length=255, blank=True)
    external_sku = models.CharField(max_length=150)
    external_sku_normalized = models.CharField(max_length=150)
    product = models.CharField(max_length=255, blank=True)
    variation = models.CharField(max_length=255, blank=True)
    variation_normalized = models.CharField(max_length=255)
    item = models.ForeignKey(
        "catalog.Item",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_order_lines",
    )
    item_code_snapshot = models.CharField(max_length=64, blank=True)
    item_name_snapshot = models.CharField(max_length=255, blank=True)
    mapping = models.ForeignKey(
        "channels.ExternalSKUMap",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_order_lines",
    )
    mapping_snapshot = models.JSONField(default=dict, blank=True)
    marketplace_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    conversion_quantity = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    internal_quantity = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    source_subtotal = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    raw_status = models.CharField(max_length=120, blank=True)
    normalized_status = models.CharField(
        max_length=20, choices=OmniOperationalStatus.choices, default=OmniOperationalStatus.UNKNOWN
    )
    mapping_status = models.CharField(max_length=32, choices=OmniMappingStatus.choices)
    source_sync_status = models.CharField(
        max_length=32, choices=OmniMappingStatus.choices, default=OmniMappingStatus.READY
    )
    source_row_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("order", "external_sku_normalized", "variation_normalized"),
                name="omni_order_line_identity_uq",
            ),
            models.CheckConstraint(
                condition=Q(marketplace_quantity__gt=0),
                name="omni_order_line_marketplace_qty_positive",
            ),
            models.CheckConstraint(
                condition=Q(conversion_quantity__isnull=True) | Q(conversion_quantity__gt=0),
                name="omni_order_line_conversion_positive",
            ),
            models.CheckConstraint(
                condition=Q(internal_quantity__isnull=True) | Q(internal_quantity__gt=0),
                name="omni_order_line_internal_qty_positive",
            ),
        ]
        indexes = [
            models.Index(fields=("order", "mapping_status"), name="omni_order_line_ready_idx"),
            models.Index(fields=("item", "normalized_status"), name="omni_order_line_item_idx"),
        ]


class OmniException(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    batch = models.ForeignKey(
        OmniImportBatch, null=True, blank=True, on_delete=models.PROTECT, related_name="exceptions"
    )
    order = models.ForeignKey(
        OmniOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="exceptions"
    )
    line = models.ForeignKey(
        OmniOrderLine, null=True, blank=True, on_delete=models.PROTECT, related_name="exceptions"
    )
    code = models.CharField(max_length=40)
    state = models.CharField(
        max_length=12, choices=OmniExceptionState.choices, default=OmniExceptionState.OPEN
    )
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("legal_entity", "state", "code"), name="omni_exception_list_idx")
        ]


class OmniPacking(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(
        "organizations.LegalEntity", on_delete=models.PROTECT, related_name="omni_packings"
    )
    store = models.ForeignKey(
        "channels.Store", on_delete=models.PROTECT, related_name="omni_packings"
    )
    marketplace = models.CharField(max_length=80)
    warehouse = models.ForeignKey(
        "organizations.Warehouse", on_delete=models.PROTECT, related_name="omni_packings"
    )
    packing_date = models.DateField()
    state = models.CharField(
        max_length=12, choices=OmniPackingState.choices, default=OmniPackingState.DRAFT
    )
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_omni_packings",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_omni_packings",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        permissions = [("post_omnipacking", "Can post Omnichannel packing")]
        indexes = [
            models.Index(
                fields=("legal_entity", "state", "packing_date"), name="omni_packing_list_idx"
            )
        ]


class OmniPackingLine(UUIDPrimaryKeyModel, TimeStampedModel):
    packing = models.ForeignKey(OmniPacking, on_delete=models.PROTECT, related_name="lines")
    order = models.ForeignKey(OmniOrder, on_delete=models.PROTECT, related_name="packing_lines")
    order_line = models.ForeignKey(
        OmniOrderLine, on_delete=models.PROTECT, related_name="packing_lines"
    )
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    item_code_snapshot = models.CharField(max_length=64)
    item_name_snapshot = models.CharField(max_length=255)
    requested_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    packed_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    source_key = models.CharField(max_length=255, unique=True)
    sequence = models.PositiveIntegerField()
    warehouse_movement = models.OneToOneField(
        "warehouse.StockMovement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_packing_line",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("packing", "sequence"), name="omni_packing_line_seq_uq"
            ),
            models.CheckConstraint(
                condition=Q(requested_quantity__gt=0), name="omni_packing_req_qty_positive"
            ),
            models.CheckConstraint(
                condition=Q(packed_quantity__gt=0), name="omni_packing_qty_positive"
            ),
        ]
        indexes = [models.Index(fields=("order_line",), name="omni_packing_order_line_idx")]


class OmniRevenueState(models.TextChoices):
    ELIGIBLE = "ELIGIBLE", "Eligible"
    BLOCKED_AMOUNT = "BLOCKED_AMOUNT", "Blocked amount"
    BLOCKED_MAPPING = "BLOCKED_MAPPING", "Blocked mapping"
    REVERSED = "REVERSED", "Reversed"


class OmniReconciliationStatus(models.TextChoices):
    READY = "READY", "Ready"
    COMPLETED_NOT_SETTLED = "COMPLETED_NOT_SETTLED", "Completed not settled"
    SETTLEMENT_MATCH = "SETTLEMENT_MATCH", "Settlement match"
    SETTLEMENT_PARTIAL = "SETTLEMENT_PARTIAL", "Settlement partial"
    SETTLEMENT_UNMATCHED = "SETTLEMENT_UNMATCHED", "Settlement unmatched"
    SETTLEMENT_OVER = "SETTLEMENT_OVER", "Settlement over"
    RETURN_PENDING = "RETURN_PENDING", "Return pending"
    REFUND_PENDING = "REFUND_PENDING", "Refund pending"
    ADJUSTMENT_PENDING = "ADJUSTMENT_PENDING", "Adjustment pending"
    PAYOUT_PENDING = "PAYOUT_PENDING", "Payout pending"
    PAYOUT_MATCH = "PAYOUT_MATCH", "Payout match"
    BLOCKED_MAPPING = "BLOCKED_MAPPING", "Blocked mapping"
    UNMATCHED_RETURN = "UNMATCHED_RETURN", "Unmatched return"
    AMBIGUOUS_ORDER_LINE = "AMBIGUOUS_ORDER_LINE", "Ambiguous order line"
    UNMATCHED_PAYOUT = "UNMATCHED_PAYOUT", "Unmatched payout"
    SOURCE_CHANGED = "SOURCE_CHANGED", "Source changed"


class OmniReturnLinkageStatus(models.TextChoices):
    MATCHED = "MATCHED", "Matched"
    UNMATCHED_ORDER = "UNMATCHED_ORDER", "Unmatched order"
    UNMATCHED_SKU = "UNMATCHED_SKU", "Unmatched SKU"
    AMBIGUOUS_ORDER_LINE = "AMBIGUOUS_ORDER_LINE", "Ambiguous order line"
    BLOCKED_MAPPING = "BLOCKED_MAPPING", "Blocked mapping"


class OmniRevenueEvent(UUIDPrimaryKeyModel, TimeStampedModel):
    """Immutable completion-date revenue source; Finance consumes a candidate later."""

    legal_entity = models.ForeignKey(
        "organizations.LegalEntity", on_delete=models.PROTECT, related_name="omni_revenue_events"
    )
    store = models.ForeignKey(
        "channels.Store", on_delete=models.PROTECT, related_name="omni_revenue_events"
    )
    marketplace = models.CharField(max_length=80)
    order = models.ForeignKey(OmniOrder, on_delete=models.PROTECT, related_name="revenue_events")
    external_order_number = models.CharField(max_length=150)
    completion_date = models.DateField()
    currency = models.CharField(max_length=12, default="IDR")
    gross_eligible_amount = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    source_components = models.JSONField(default=dict, blank=True)
    source_lineage = models.JSONField(default=dict, blank=True)
    state = models.CharField(
        max_length=24, choices=OmniRevenueState.choices, default=OmniRevenueState.ELIGIBLE
    )
    mapping_status = models.CharField(
        max_length=24,
        choices=OmniReconciliationStatus.choices,
        default=OmniReconciliationStatus.BLOCKED_MAPPING,
    )
    event_key = models.CharField(max_length=400, unique=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_omni_revenue_events",
    )
    reversal_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversals"
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "order"), name="omni_revenue_entity_order_uq"
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "completion_date", "state"),
                name="omni_revenue_date_state_idx",
            ),
            models.Index(
                fields=("legal_entity", "store", "marketplace"), name="omni_revenue_store_idx"
            ),
        ]


class OmniSettlementImportBatch(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(
        "organizations.LegalEntity",
        on_delete=models.PROTECT,
        related_name="omni_settlement_batches",
    )
    source_type = models.CharField(max_length=60, default="BIGSELLER_SETTLEMENT")
    source_filename = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64)
    row_count = models.PositiveIntegerField(default=0)
    imported_at = models.DateTimeField(null=True, blank=True)
    imported_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_settlement_imports",
    )
    status = models.CharField(max_length=24, default="IMPORTED")
    idempotency_key = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        permissions = [
            ("import_omnisettlement", "Can import marketplace settlements"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_type", "file_hash"),
                name="omni_settle_batch_hash_uq",
            )
        ]


class OmniSettlement(UUIDPrimaryKeyModel, TimeStampedModel):
    batch = models.ForeignKey(
        OmniSettlementImportBatch, on_delete=models.PROTECT, related_name="settlements"
    )
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    store = models.ForeignKey(
        "channels.Store",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_settlements",
    )
    external_store_name = models.CharField(max_length=255, blank=True)
    marketplace = models.CharField(max_length=80, blank=True)
    settlement_reference = models.CharField(max_length=180, blank=True)
    external_order_number = models.CharField(max_length=150, blank=True)
    settlement_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=12, blank=True)
    gross_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    settled_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    fee_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    refund_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    adjustment_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    net_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    fee_components = models.JSONField(default=dict, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    source_row_key = models.CharField(max_length=255)
    source_identity_key = models.CharField(max_length=500)
    reconciliation_status = models.CharField(
        max_length=32,
        choices=OmniReconciliationStatus.choices,
        default=OmniReconciliationStatus.SETTLEMENT_UNMATCHED,
    )
    reconciliation_message = models.TextField(blank=True)
    matched_revenue = models.ForeignKey(
        OmniRevenueEvent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="settlements",
    )
    conflict_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="conflicts"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_identity_key"),
                name="omni_settle_source_identity_uq",
            )
        ]
        indexes = [
            models.Index(fields=("legal_entity", "settlement_date"), name="omni_settle_date_idx"),
            models.Index(fields=("matched_revenue",), name="omni_settle_revenue_idx"),
        ]


class OmniSettlementFee(UUIDPrimaryKeyModel, TimeStampedModel):
    settlement = models.ForeignKey(OmniSettlement, on_delete=models.PROTECT, related_name="fees")
    fee_type = models.CharField(max_length=80)
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    source_key = models.CharField(max_length=500, unique=True)
    source_row_key = models.CharField(max_length=255)
    raw_data = models.JSONField(default=dict, blank=True)
    mapping_status = models.CharField(max_length=24, default="BLOCKED_MAPPING")


class OmniReturnImportBatch(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(
        "organizations.LegalEntity", on_delete=models.PROTECT, related_name="omni_return_batches"
    )
    source_type = models.CharField(max_length=60, default="BIGSELLER_RETURN")
    source_filename = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64)
    row_count = models.PositiveIntegerField(default=0)
    imported_at = models.DateTimeField(null=True, blank=True)
    imported_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_return_imports",
    )
    status = models.CharField(max_length=24, default="IMPORTED")
    idempotency_key = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        permissions = [
            ("import_omnireturnsource", "Can import marketplace returns"),
            ("manage_omnireturnsource", "Can manage marketplace returns"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_type", "file_hash"),
                name="omni_return_batch_hash_uq",
            )
        ]


class OmniReturnSource(UUIDPrimaryKeyModel, TimeStampedModel):
    batch = models.ForeignKey(
        OmniReturnImportBatch, on_delete=models.PROTECT, related_name="returns"
    )
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    marketplace = models.CharField(max_length=80, blank=True)
    external_store_name = models.CharField(max_length=255, blank=True)
    store = models.ForeignKey(
        "channels.Store",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_returns",
    )
    package_number = models.CharField(max_length=180, blank=True)
    external_order_number = models.CharField(max_length=150, blank=True)
    external_return_id = models.CharField(max_length=180, blank=True)
    external_sku = models.CharField(max_length=150, blank=True)
    warehouse_sku = models.CharField(max_length=150, blank=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    stock_addition_quantity = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    inspected_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    quality_accepted_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    warehouse_returned_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    refunded_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    refund_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=12, blank=True)
    order_status = models.CharField(max_length=120, blank=True)
    shipping_status = models.CharField(max_length=120, blank=True)
    aftersales_status = models.CharField(max_length=120, blank=True)
    return_status = models.CharField(max_length=120, blank=True)
    stock_addition_status = models.CharField(max_length=120, blank=True)
    return_type = models.CharField(max_length=120, blank=True)
    return_reason = models.CharField(max_length=255, blank=True)
    order_date = models.DateTimeField(null=True, blank=True)
    return_requested_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    stock_added_at = models.DateTimeField(null=True, blank=True)
    original_order = models.ForeignKey(
        OmniOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="return_sources"
    )
    original_order_line = models.ForeignKey(
        OmniOrderLine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="return_sources",
    )
    resolved_item = models.ForeignKey(
        "catalog.Item",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_return_sources",
    )
    quality_inspection_line = models.ForeignKey(
        "quality.QualityInspectionLine",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_return_sources",
    )
    linkage_status = models.CharField(
        max_length=32,
        choices=OmniReturnLinkageStatus.choices,
        default=OmniReturnLinkageStatus.UNMATCHED_ORDER,
    )
    linkage_message = models.TextField(blank=True)
    source_row_key = models.CharField(max_length=255)
    source_identity_key = models.CharField(max_length=500)
    raw_data = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_identity_key"),
                name="omni_return_source_identity_uq",
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="omni_return_qty_positive"),
            models.CheckConstraint(
                condition=Q(inspected_quantity__gte=0)
                & Q(quality_accepted_quantity__gte=0)
                & Q(warehouse_returned_quantity__gte=0)
                & Q(refunded_quantity__gte=0),
                name="omni_return_followup_qty_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=("legal_entity", "arrived_at"), name="omni_return_arrival_idx"),
            models.Index(fields=("legal_entity", "linkage_status"), name="omni_return_link_idx"),
            models.Index(
                fields=("original_order", "external_sku"), name="omni_return_order_sku_idx"
            ),
        ]


class OmniAdjustmentSource(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(
        "organizations.LegalEntity", on_delete=models.PROTECT, related_name="omni_adjustments"
    )
    store = models.ForeignKey(
        "channels.Store",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_adjustments",
    )
    marketplace = models.CharField(max_length=80, blank=True)
    external_order_number = models.CharField(max_length=150, blank=True)
    settlement = models.ForeignKey(
        OmniSettlement, null=True, blank=True, on_delete=models.PROTECT, related_name="adjustments"
    )
    adjustment_type = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    transaction_date = models.DateField(null=True, blank=True)
    source_batch = models.ForeignKey(
        OmniSettlementImportBatch,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="adjustment_sources",
    )
    source_row_key = models.CharField(max_length=255)
    source_identity_key = models.CharField(max_length=500)
    reconciliation_status = models.CharField(
        max_length=32,
        choices=OmniReconciliationStatus.choices,
        default=OmniReconciliationStatus.ADJUSTMENT_PENDING,
    )
    raw_data = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_identity_key"), name="omni_adjustment_identity_uq"
            )
        ]


class OmniPayoutSource(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(
        "organizations.LegalEntity", on_delete=models.PROTECT, related_name="omni_payouts"
    )
    store = models.ForeignKey(
        "channels.Store",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="omni_payouts",
    )
    marketplace = models.CharField(max_length=80, blank=True)
    payout_reference = models.CharField(max_length=180)
    payout_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=12, blank=True)
    settlement_references = models.JSONField(default=list, blank=True)
    source_filename = models.CharField(max_length=255, blank=True)
    source_row_key = models.CharField(max_length=255, blank=True)
    source_identity_key = models.CharField(max_length=500)
    reconciliation_status = models.CharField(
        max_length=32,
        choices=OmniReconciliationStatus.choices,
        default=OmniReconciliationStatus.UNMATCHED_PAYOUT,
    )
    reconciliation_message = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_omni_payouts",
    )

    class Meta:
        permissions = [
            ("manage_omnipayoutsource", "Can manage marketplace payout handoff"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_identity_key"), name="omni_payout_identity_uq"
            )
        ]


class PosSaleState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"
    CANCELLED = "CANCELLED", "Cancelled"


class PosTenderMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    QRIS = "QRIS", "QRIS"
    OTHER = "OTHER", "Other configured method"


class PosCashSessionState(models.TextChoices):
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"


class PosReturnState(models.TextChoices):
    RECORDED = "RECORDED", "Recorded"
    CANCELLED = "CANCELLED", "Cancelled"


class PosFinanceSourceState(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    REVERSED = "REVERSED", "Reversed"
    BLOCKED_MAPPING = "BLOCKED_MAPPING", "Blocked mapping"
    PENDING_VALUATION = "PENDING_VALUATION", "Pending valuation"


class PosCashSession(UUIDPrimaryKeyModel, TimeStampedModel):
    """Operational cash control only; Finance owns the eventual cash ledger."""

    legal_entity = models.ForeignKey(
        "organizations.LegalEntity", on_delete=models.PROTECT, related_name="pos_cash_sessions"
    )
    store = models.ForeignKey(
        "channels.Store", on_delete=models.PROTECT, related_name="pos_cash_sessions"
    )
    opened_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="opened_pos_cash_sessions"
    )
    opened_at = models.DateTimeField()
    opening_cash_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    state = models.CharField(
        max_length=12, choices=PosCashSessionState.choices, default=PosCashSessionState.OPEN
    )
    closed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="closed_pos_cash_sessions",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    expected_cash_amount = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    counted_cash_amount = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    variance_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    source_key = models.CharField(max_length=255, unique=True)
    close_idempotency_key = models.CharField(max_length=255, blank=True)

    class Meta:
        permissions = [
            ("open_poscashsession", "Can open POS cash session"),
            ("close_poscashsession", "Can close POS cash session"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "store"),
                condition=Q(state=PosCashSessionState.OPEN),
                name="pos_cash_one_open_store_uq",
            ),
            models.CheckConstraint(
                condition=Q(opening_cash_amount__gte=0), name="pos_cash_opening_nonnegative"
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "store", "state"), name="pos_cash_session_scope_idx"
            )
        ]


class PosSale(UUIDPrimaryKeyModel, TimeStampedModel):
    """Strict canonical-Item POS source document; stock is posted by Warehouse."""

    legal_entity = models.ForeignKey(
        "organizations.LegalEntity", on_delete=models.PROTECT, related_name="pos_sales"
    )
    document_number = models.CharField(max_length=80)
    store = models.ForeignKey("channels.Store", on_delete=models.PROTECT, related_name="pos_sales")
    warehouse = models.ForeignKey(
        "organizations.Warehouse", on_delete=models.PROTECT, related_name="pos_sales"
    )
    sales_channel = models.CharField(max_length=50, default="POS")
    transaction_at = models.DateTimeField()
    transaction_date = models.DateField()
    state = models.CharField(
        max_length=12, choices=PosSaleState.choices, default=PosSaleState.DRAFT
    )
    currency = models.CharField(max_length=12, default="IDR")
    subtotal_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    grand_total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    source_key = models.CharField(max_length=255, unique=True)
    idempotency_key = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_pos_sales",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_pos_sales",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cancelled_pos_sales",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        permissions = [
            ("post_possale", "Can post POS sale"),
            ("reverse_possale", "Can reverse POS sale"),
            ("view_storeanalytics", "Can view Store analytics"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "document_number"), name="pos_sale_document_number_uq"
            ),
            models.CheckConstraint(
                condition=Q(subtotal_amount__gte=0)
                & Q(discount_amount__gte=0)
                & Q(grand_total_amount__gte=0),
                name="pos_sale_amounts_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "store", "transaction_date", "state"),
                name="pos_sale_analytics_idx",
            )
        ]


class PosSaleLine(UUIDPrimaryKeyModel, TimeStampedModel):
    sale = models.ForeignKey(PosSale, on_delete=models.PROTECT, related_name="lines")
    item = models.ForeignKey(
        "catalog.Item", on_delete=models.PROTECT, related_name="pos_sale_lines"
    )
    item_code_snapshot = models.CharField(max_length=64)
    item_name_snapshot = models.CharField(max_length=255)
    uom_code_snapshot = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    unit_price_amount = models.DecimalField(max_digits=18, decimal_places=2)
    line_amount = models.DecimalField(max_digits=18, decimal_places=2)
    warehouse_unit_cost = models.DecimalField(
        max_digits=24, decimal_places=6, null=True, blank=True
    )
    cogs_amount = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    valuation_status = models.CharField(max_length=24, default="PENDING_VALUATION")
    source_key = models.CharField(max_length=255, unique=True)
    sequence = models.PositiveIntegerField()
    warehouse_movement = models.OneToOneField(
        "warehouse.StockMovement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pos_sale_line",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("sale", "sequence"), name="pos_sale_line_sequence_uq"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="pos_sale_line_qty_positive"),
            models.CheckConstraint(
                condition=Q(unit_price_amount__gte=0), name="pos_sale_line_price_nonnegative"
            ),
        ]


class PosTender(UUIDPrimaryKeyModel, TimeStampedModel):
    sale = models.OneToOneField(PosSale, on_delete=models.PROTECT, related_name="tender")
    method = models.CharField(max_length=20, choices=PosTenderMethod.choices)
    method_reference = models.CharField(max_length=160, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=12, default="IDR")
    transaction_at = models.DateTimeField()
    cash_session = models.ForeignKey(
        PosCashSession,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tenders",
    )
    source_key = models.CharField(max_length=255, unique=True)
    mapping_status = models.CharField(max_length=24, default="BLOCKED_MAPPING")

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="pos_tender_amount_nonnegative")
        ]


class PosSaleReversal(UUIDPrimaryKeyModel, TimeStampedModel):
    original_sale = models.OneToOneField(PosSale, on_delete=models.PROTECT, related_name="reversal")
    reversal_date = models.DateField()
    reason = models.TextField()
    source_key = models.CharField(max_length=255, unique=True)
    idempotency_key = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_pos_sale_reversals",
    )


class PosReturn(UUIDPrimaryKeyModel, TimeStampedModel):
    """Commercial POS return source. Quality and Warehouse control physical disposition."""

    legal_entity = models.ForeignKey(
        "organizations.LegalEntity", on_delete=models.PROTECT, related_name="pos_returns"
    )
    document_number = models.CharField(max_length=80)
    original_sale = models.ForeignKey(PosSale, on_delete=models.PROTECT, related_name="returns")
    store = models.ForeignKey(
        "channels.Store", on_delete=models.PROTECT, related_name="pos_returns"
    )
    warehouse = models.ForeignKey(
        "organizations.Warehouse", on_delete=models.PROTECT, related_name="pos_returns"
    )
    return_at = models.DateTimeField()
    return_date = models.DateField()
    state = models.CharField(
        max_length=12, choices=PosReturnState.choices, default=PosReturnState.RECORDED
    )
    currency = models.CharField(max_length=12, default="IDR")
    refund_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    refunded_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    cash_session = models.ForeignKey(
        PosCashSession,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pos_refunds",
    )
    source_key = models.CharField(max_length=255, unique=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_pos_returns",
    )
    notes = models.TextField(blank=True)

    class Meta:
        permissions = [("manage_posreturn", "Can manage POS return")]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "document_number"), name="pos_return_document_number_uq"
            ),
            models.CheckConstraint(
                condition=Q(refunded_amount__gte=0), name="pos_return_refunded_nonnegative"
            ),
        ]


class PosReturnLine(UUIDPrimaryKeyModel, TimeStampedModel):
    pos_return = models.ForeignKey(PosReturn, on_delete=models.PROTECT, related_name="lines")
    original_sale_line = models.ForeignKey(
        PosSaleLine, on_delete=models.PROTECT, related_name="return_lines"
    )
    item = models.ForeignKey(
        "catalog.Item", on_delete=models.PROTECT, related_name="pos_return_lines"
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    inspected_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    quality_accepted_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    warehouse_returned_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    refunded_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    refund_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    quality_inspection_line = models.ForeignKey(
        "quality.QualityInspectionLine",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pos_return_lines",
    )
    source_key = models.CharField(max_length=255, unique=True)
    sequence = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("pos_return", "sequence"), name="pos_return_line_sequence_uq"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="pos_return_line_qty_positive"
            ),
            models.CheckConstraint(
                condition=Q(inspected_quantity__gte=0)
                & Q(quality_accepted_quantity__gte=0)
                & Q(warehouse_returned_quantity__gte=0)
                & Q(refunded_quantity__gte=0),
                name="pos_return_line_followup_nonnegative",
            ),
        ]


class PosFinanceSource(UUIDPrimaryKeyModel, TimeStampedModel):
    """Immutable Finance handoff candidate; never a JournalEntry or cash ledger."""

    legal_entity = models.ForeignKey(
        "organizations.LegalEntity", on_delete=models.PROTECT, related_name="pos_finance_sources"
    )
    store = models.ForeignKey(
        "channels.Store", on_delete=models.PROTECT, related_name="pos_finance_sources"
    )
    sale = models.ForeignKey(
        PosSale,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="finance_sources",
    )
    sale_line = models.ForeignKey(
        PosSaleLine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="finance_sources",
    )
    pos_return = models.ForeignKey(
        PosReturn,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="finance_sources",
    )
    cash_session = models.ForeignKey(
        PosCashSession,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="finance_sources",
    )
    event_code = models.CharField(max_length=64)
    transaction_date = models.DateField()
    amount = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    currency = models.CharField(max_length=12, default="IDR")
    mapping_status = models.CharField(max_length=24, default="BLOCKED_MAPPING")
    source_key = models.CharField(max_length=255, unique=True)
    state = models.CharField(
        max_length=24, choices=PosFinanceSourceState.choices, default=PosFinanceSourceState.ACTIVE
    )
    reversal_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversals"
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("legal_entity", "store", "transaction_date", "event_code"),
                name="pos_finance_analytics_idx",
            )
        ]
