from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel


class ProductionStage(models.TextChoices):
    CUT = "CUT", "Potong"
    SEW = "SEW", "Jahit"
    QC_PACKING = "QC_PACKING", "QC & Packing"


class ProductionEntryState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"


class ProductionHandoverState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    READY_FOR_GUDANG = "READY_FOR_GUDANG", "Siap Gudang"


class ProductionWorkEntry(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    work_order = models.ForeignKey(
        "purchasing.WorkOrder", on_delete=models.PROTECT, related_name="production_work_entries"
    )
    production_date = models.DateField()
    stage = models.CharField(max_length=16, choices=ProductionStage.choices)
    notes = models.TextField(blank=True)
    state = models.CharField(
        max_length=12, choices=ProductionEntryState.choices, default=ProductionEntryState.DRAFT
    )
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_production_work_entries",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_production_work_entries",
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("legal_entity", "state", "production_date"), name="prod_work_list_idx"
            ),
            models.Index(fields=("work_order", "stage", "state"), name="prod_work_wostage_idx"),
        ]
        permissions = [
            ("post_productionworkentry", "Can post production work entry"),
            ("reverse_productionworkline", "Can reverse production work line"),
        ]


class ProductionWorkLine(UUIDPrimaryKeyModel, TimeStampedModel):
    entry = models.ForeignKey(ProductionWorkEntry, on_delete=models.PROTECT, related_name="lines")
    output = models.ForeignKey(
        "purchasing.WorkOrderOutput", on_delete=models.PROTECT, related_name="production_work_lines"
    )
    item = models.ForeignKey(
        "catalog.Item", on_delete=models.PROTECT, related_name="production_work_lines"
    )
    item_code_snapshot = models.CharField(max_length=64)
    item_name_snapshot = models.CharField(max_length=255)
    uom_code_snapshot = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    sequence = models.PositiveIntegerField()
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entry", "sequence"), name="prod_work_line_seq_uq"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="prod_work_line_qty_pos"),
        ]
        indexes = [models.Index(fields=("output",), name="prod_work_line_output_idx")]


class ProductionWorkLineReversal(UUIDPrimaryKeyModel):
    original_line = models.OneToOneField(
        ProductionWorkLine, on_delete=models.PROTECT, related_name="reversal"
    )
    reason = models.TextField()
    reversed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="production_work_reversals",
    )
    reversed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("reversed_at",), name="prod_work_rev_time_idx")]


class ProductionRejectEntry(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    work_order = models.ForeignKey(
        "purchasing.WorkOrder", on_delete=models.PROTECT, related_name="production_reject_entries"
    )
    production_date = models.DateField()
    notes = models.TextField(blank=True)
    state = models.CharField(
        max_length=12, choices=ProductionEntryState.choices, default=ProductionEntryState.DRAFT
    )
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_production_reject_entries",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_production_reject_entries",
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("legal_entity", "state", "production_date"), name="prod_reject_list_idx"
            )
        ]
        permissions = [
            ("post_productionrejectentry", "Can post production reject entry"),
            ("reverse_productionrejectline", "Can reverse production reject line"),
        ]


class ProductionRejectLine(UUIDPrimaryKeyModel, TimeStampedModel):
    entry = models.ForeignKey(ProductionRejectEntry, on_delete=models.PROTECT, related_name="lines")
    output = models.ForeignKey(
        "purchasing.WorkOrderOutput",
        on_delete=models.PROTECT,
        related_name="production_reject_lines",
    )
    stage = models.CharField(max_length=16, choices=ProductionStage.choices)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    reason = models.TextField()
    notes = models.TextField(blank=True)
    sequence = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entry", "sequence"), name="prod_reject_line_seq_uq"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="prod_rej_line_qty_pos"),
        ]
        indexes = [models.Index(fields=("output", "stage"), name="prod_rej_line_outstage_idx")]


class ProductionRejectLineReversal(UUIDPrimaryKeyModel):
    original_line = models.OneToOneField(
        ProductionRejectLine, on_delete=models.PROTECT, related_name="reversal"
    )
    reason = models.TextField()
    reversed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="production_reject_reversals",
    )
    reversed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("reversed_at",), name="prod_rej_rev_time_idx")]


class ProductionWarehouseHandover(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    work_order = models.ForeignKey(
        "purchasing.WorkOrder", on_delete=models.PROTECT, related_name="production_handovers"
    )
    handover_date = models.DateField()
    notes = models.TextField(blank=True)
    state = models.CharField(
        max_length=20,
        choices=ProductionHandoverState.choices,
        default=ProductionHandoverState.DRAFT,
    )
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_production_handovers",
    )
    ready_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ready_production_handovers",
    )
    ready_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("legal_entity", "state", "handover_date"), name="prod_handover_list_idx"
            ),
            models.Index(fields=("work_order", "state"), name="prod_handover_wo_idx"),
        ]
        permissions = [
            ("ready_productionwarehousehandover", "Can mark production handover ready"),
            ("reverse_productionhandoverline", "Can reverse production handover line"),
        ]


class ProductionWarehouseHandoverLine(UUIDPrimaryKeyModel, TimeStampedModel):
    handover = models.ForeignKey(
        ProductionWarehouseHandover, on_delete=models.PROTECT, related_name="lines"
    )
    output = models.ForeignKey(
        "purchasing.WorkOrderOutput",
        on_delete=models.PROTECT,
        related_name="production_handover_lines",
    )
    item = models.ForeignKey(
        "catalog.Item", on_delete=models.PROTECT, related_name="production_handover_lines"
    )
    item_code_snapshot = models.CharField(max_length=64)
    item_name_snapshot = models.CharField(max_length=255)
    uom_code_snapshot = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    sequence = models.PositiveIntegerField()
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("handover", "sequence"), name="prod_handover_line_seq_uq"
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="prod_handover_line_qty_pos"),
        ]
        indexes = [models.Index(fields=("output",), name="prod_handover_line_out_idx")]


class ProductionWarehouseHandoverLineReversal(UUIDPrimaryKeyModel):
    original_line = models.OneToOneField(
        ProductionWarehouseHandoverLine, on_delete=models.PROTECT, related_name="reversal"
    )
    reason = models.TextField()
    reversed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="production_handover_reversals",
    )
    reversed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("reversed_at",), name="prod_hand_rev_time_idx")]
