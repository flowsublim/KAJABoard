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
