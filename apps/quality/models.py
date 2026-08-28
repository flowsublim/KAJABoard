from django.db import models
from django.db.models import F, Q

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel


class InspectionType(models.TextChoices):
    PRODUCTION_FINISHED_GOODS = "PRODUCTION_FINISHED_GOODS", "Production finished goods"
    SUBCONTRACT_RECEIPT = "SUBCONTRACT_RECEIPT", "Subcontract receipt"
    SUPPLIER_INCOMING = "SUPPLIER_INCOMING", "Supplier incoming"
    CUSTOMER_RETURN = "CUSTOMER_RETURN", "Customer return"
    MARKETPLACE_RETURN = "MARKETPLACE_RETURN", "Marketplace return"
    RANDOM_INSPECTION = "RANDOM_INSPECTION", "Random inspection"


class QualityResult(models.TextChoices):
    PASS = "PASS", "Pass"
    HOLD = "HOLD", "Hold"
    REJECT = "REJECT", "Reject"
    REWORK = "REWORK", "Rework"
    LEGACY_UNMAPPED = "LEGACY_UNMAPPED", "Legacy unmapped"


class QualityDocumentState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class QualitySummaryStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    PARTIAL = "PARTIAL", "Partial"
    COMPLETED = "COMPLETED", "Completed"
    MIXED = "MIXED", "Mixed"


class QualityReason(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(
        "organizations.LegalEntity",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quality_reasons",
    )
    code = models.CharField(max_length=64)
    display_name = models.CharField(max_length=255)
    applies_to_result = models.CharField(max_length=24, choices=QualityResult.choices)
    active = models.BooleanField(default=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "code"), name="quality_reason_entity_code_uq"
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_from__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="quality_reason_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "active", "applies_to_result"),
                name="quality_reason_lookup_idx",
            )
        ]

    def __str__(self):
        return f"{self.code} - {self.display_name}"


class QualityInspection(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey(
        "organizations.LegalEntity", on_delete=models.PROTECT, related_name="quality_inspections"
    )
    inspection_type = models.CharField(max_length=32, choices=InspectionType.choices)
    source_module = models.CharField(max_length=64)
    source_type = models.CharField(max_length=64)
    source_document_id = models.CharField(max_length=64)
    source_key = models.CharField(max_length=255)
    inspection_date = models.DateField()
    state = models.CharField(
        max_length=12, choices=QualityDocumentState.choices, default=QualityDocumentState.DRAFT
    )
    inspector = models.ForeignKey(
        "accounts.Employee",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quality_inspections",
    )
    inspector_code_snapshot = models.CharField(max_length=64, blank=True)
    inspector_name_snapshot = models.CharField(max_length=255, blank=True)
    warehouse = models.ForeignKey(
        "organizations.Warehouse",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quality_inspections",
    )
    notes = models.TextField(blank=True)
    evidence_reference = models.CharField(max_length=500, blank=True)
    evidence_metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_quality_inspections",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_quality_inspections",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversed_quality_inspections",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.TextField(blank=True)

    class Meta:
        permissions = [
            ("post_qualityinspection", "Can post quality inspection"),
            ("reverse_qualityinspection", "Can reverse quality inspection"),
            ("view_qualitydashboard", "Can view quality dashboard"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "source_key"), name="quality_inspection_source_uq"
            )
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "state", "inspection_date"),
                name="quality_inspection_list_idx",
            ),
            models.Index(
                fields=("source_module", "source_type", "source_document_id"),
                name="quality_source_idx",
            ),
        ]

    @property
    def status(self):
        return self.state

    @status.setter
    def status(self, value):
        self.state = value

    @property
    def summary_status(self):
        lines = tuple(self.lines.filter(reversal__isnull=True))
        if not lines:
            return QualitySummaryStatus.OPEN
        if any(line.result_status in {"MIXED", QualityResult.LEGACY_UNMAPPED} for line in lines):
            return QualitySummaryStatus.MIXED
        if any(line.qty_hold or line.qty_reject or line.qty_rework for line in lines):
            return QualitySummaryStatus.MIXED
        if all(line.qty_inspected == line.qty_presented for line in lines):
            return QualitySummaryStatus.COMPLETED
        return QualitySummaryStatus.PARTIAL

    def __str__(self):
        return f"{self.inspection_type} / {self.source_key}"


class QualityInspectionLine(UUIDPrimaryKeyModel, TimeStampedModel):
    inspection = models.ForeignKey(
        QualityInspection, on_delete=models.PROTECT, related_name="lines"
    )
    source_line_id = models.CharField(max_length=64)
    production_handover_line = models.ForeignKey(
        "production.ProductionWarehouseHandoverLine",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quality_inspection_lines",
    )
    subcontract_receipt_line = models.ForeignKey(
        "purchasing.SubcontractReceiptOutputLine",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quality_inspection_lines",
    )
    work_order_output = models.ForeignKey(
        "purchasing.WorkOrderOutput",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quality_inspection_lines",
    )
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT, related_name="quality_lines")
    qty_presented = models.DecimalField(max_digits=18, decimal_places=6)
    qty_inspected = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    qty_pass = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    qty_hold = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    qty_reject = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    qty_rework = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    qty_legacy_unmapped = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    uom_code_snapshot = models.CharField(max_length=20)
    result = models.CharField(max_length=24, choices=QualityResult.choices, blank=True)
    reason_code_snapshot = models.CharField(max_length=64, blank=True)
    reason_text = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    sequence = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("inspection", "sequence"), name="quality_line_sequence_uq"
            ),
            models.CheckConstraint(
                condition=Q(qty_presented__gte=0), name="quality_presented_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(qty_inspected__gte=0), name="quality_inspected_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(qty_inspected__lte=F("qty_presented")),
                name="quality_inspected_lte_presented",
            ),
            models.CheckConstraint(condition=Q(qty_pass__gte=0), name="quality_pass_nonnegative"),
            models.CheckConstraint(condition=Q(qty_hold__gte=0), name="quality_hold_nonnegative"),
            models.CheckConstraint(
                condition=Q(qty_reject__gte=0), name="quality_reject_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(qty_rework__gte=0), name="quality_rework_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(qty_legacy_unmapped__gte=0), name="quality_legacy_nonnegative"
            ),
        ]
        indexes = [
            models.Index(fields=("source_line_id", "inspection"), name="quality_line_source_idx"),
            models.Index(fields=("item", "inspection"), name="quality_line_item_idx"),
        ]

    @property
    def reason(self):
        return self.reason_text

    @property
    def result_status(self):
        values = {
            QualityResult.PASS: self.qty_pass,
            QualityResult.HOLD: self.qty_hold,
            QualityResult.REJECT: self.qty_reject,
            QualityResult.REWORK: self.qty_rework,
            QualityResult.LEGACY_UNMAPPED: self.qty_legacy_unmapped,
        }
        active = [key for key, value in values.items() if value]
        if len(active) == 1:
            return active[0]
        if len(active) > 1:
            return "MIXED"
        return "PENDING"


class QualityInspectionLineReversal(UUIDPrimaryKeyModel):
    original_line = models.OneToOneField(
        QualityInspectionLine, on_delete=models.PROTECT, related_name="reversal"
    )
    reason = models.TextField()
    reversed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quality_line_reversals",
    )
    reversed_at = models.DateTimeField(auto_now_add=True)
    replacement_line = models.ForeignKey(
        QualityInspectionLine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="replacement_for_reversal",
    )

    class Meta:
        indexes = [models.Index(fields=("reversed_at",), name="quality_line_rev_time_idx")]
