from django.core.exceptions import ValidationError
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


class ProductionWageMethod(models.TextChoices):
    PIECE_RATE = "PIECE_RATE", "Borongan"
    NO_WAGE = "NO_WAGE", "Tanpa Upah"


class ProductionExtraCostCategory(models.TextChoices):
    MEAL_OPERATOR = "MEAL_OPERATOR", "Makan Operator"
    DAILY_WAGE = "DAILY_WAGE", "Upah Harian"
    ACCESSORY_ADVANCE = "ACCESSORY_ADVANCE", "Uang Muka Aksesoris"
    OTHER_DIRECT = "OTHER_DIRECT", "Lainnya Langsung"


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
    employee = models.ForeignKey(
        "accounts.Employee", null=True, blank=True, on_delete=models.PROTECT
    )
    wage_method = models.CharField(
        max_length=16, choices=ProductionWageMethod.choices, default=ProductionWageMethod.NO_WAGE
    )
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
    cpo_beneficiary = models.ForeignKey(
        "accounts.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cpo_production_handovers",
        help_text=(
            "Explicit beneficiary/SPV for CPO Finished Goods Fee associated "
            "with this Production → Warehouse handover."
        ),
    )

    def clean(self):
        errors = {}
        if self.cpo_beneficiary_id:
            if self.cpo_beneficiary.legal_entity_id != self.legal_entity_id:
                errors["cpo_beneficiary"] = "Beneficiary must belong to the same legal entity."
            elif not self.cpo_beneficiary.is_active:
                errors["cpo_beneficiary"] = "Beneficiary employee must be active."
        if self.pk:
            orig = (
                ProductionWarehouseHandover.objects.filter(pk=self.pk)
                .values("cpo_beneficiary_id")
                .first()
            )
            if orig and orig["cpo_beneficiary_id"] != self.cpo_beneficiary_id:
                from apps.incentives.models import IncentiveAccrual, IncentiveType
                from apps.warehouse.models import WarehouseReceiptLine

                line_ids = [
                    str(x)
                    for x in WarehouseReceiptLine.objects.filter(
                        receipt__handover_id=self.pk
                    ).values_list("id", flat=True)
                ]
                has_cpo = IncentiveAccrual.objects.filter(
                    incentive_type=IncentiveType.CPO_FEE,
                    source_module="warehouse",
                    source_type="WAREHOUSE_RECEIPT_LINE",
                    source_line_id__in=line_ids,
                ).exists()
                if has_cpo:
                    errors["cpo_beneficiary"] = (
                        "Cannot change CPO beneficiary after CPO fee accruals have been created."
                    )
        if errors:
            raise ValidationError(errors)

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


class ProductionTariff(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    stage = models.CharField(max_length=16, choices=ProductionStage.choices)
    item = models.ForeignKey("catalog.Item", on_delete=models.PROTECT)
    wage_method = models.CharField(max_length=16, choices=ProductionWageMethod.choices)
    rate_per_unit = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3, default="IDR")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("legal_entity", "stage", "item"), name="prod_tariff_lookup_idx")
        ]
        constraints = [
            models.CheckConstraint(condition=Q(rate_per_unit__gte=0), name="prod_tariff_rate_valid")
        ]


class ProductionLaborCost(UUIDPrimaryKeyModel, TimeStampedModel):
    source_line = models.ForeignKey(
        ProductionWorkLine, on_delete=models.PROTECT, related_name="labor_costs"
    )
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    work_order = models.ForeignKey("purchasing.WorkOrder", on_delete=models.PROTECT)
    output = models.ForeignKey("purchasing.WorkOrderOutput", on_delete=models.PROTECT)
    employee = models.ForeignKey(
        "accounts.Employee", null=True, blank=True, on_delete=models.PROTECT
    )
    employee_code_snapshot = models.CharField(max_length=64, blank=True)
    employee_name_snapshot = models.CharField(max_length=255, blank=True)
    stage_snapshot = models.CharField(max_length=16, choices=ProductionStage.choices)
    item_code_snapshot = models.CharField(max_length=64)
    quantity_snapshot = models.DecimalField(max_digits=18, decimal_places=6)
    wage_method = models.CharField(max_length=16, choices=ProductionWageMethod.choices)
    tariff = models.ForeignKey(ProductionTariff, null=True, blank=True, on_delete=models.PROTECT)
    tariff_rate_snapshot = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    production_date = models.DateField()
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("output", "reversed_at"), name="prod_labor_output_idx")]


class ProductionLaborCostReversal(UUIDPrimaryKeyModel):
    original = models.OneToOneField(
        ProductionLaborCost, on_delete=models.PROTECT, related_name="reversal"
    )
    replacement = models.ForeignKey(
        ProductionLaborCost,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversal_sources",
    )
    reason = models.TextField()
    reversed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT
    )
    reversed_at = models.DateTimeField(auto_now_add=True)


class ProductionDirectExtraCost(UUIDPrimaryKeyModel, TimeStampedModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    work_order = models.ForeignKey("purchasing.WorkOrder", on_delete=models.PROTECT)
    output = models.ForeignKey("purchasing.WorkOrderOutput", on_delete=models.PROTECT)
    cost_date = models.DateField()
    category = models.CharField(max_length=24, choices=ProductionExtraCostCategory.choices)
    employee = models.ForeignKey(
        "accounts.Employee", null=True, blank=True, on_delete=models.PROTECT
    )
    description = models.TextField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    notes = models.TextField(blank=True)
    state = models.CharField(
        max_length=12, choices=ProductionEntryState.choices, default=ProductionEntryState.DRAFT
    )
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_production_extra_costs",
    )
    posted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="posted_production_extra_costs",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="prod_extra_amount_pos")
        ]
        permissions = [("post_productiondirectextracost", "Can post production direct extra cost")]


class ProductionDirectExtraCostReversal(UUIDPrimaryKeyModel):
    original = models.OneToOneField(
        ProductionDirectExtraCost, on_delete=models.PROTECT, related_name="reversal"
    )
    replacement = models.ForeignKey(
        ProductionDirectExtraCost,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversal_sources",
    )
    reason = models.TextField()
    reversed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT
    )
    reversed_at = models.DateTimeField(auto_now_add=True)


class ProductionOverheadSnapshot(UUIDPrimaryKeyModel):
    source_key = models.CharField(max_length=255, unique=True)
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    source_module = models.CharField(max_length=64)
    source_type = models.CharField(max_length=64)
    source_document_id = models.CharField(max_length=64)
    source_line_id = models.CharField(max_length=64)
    category_snapshot = models.CharField(max_length=128, blank=True)
    accounting_treatment_snapshot = models.CharField(max_length=16, blank=True)
    cost_center_snapshot = models.CharField(max_length=128, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    posting_date = models.DateField()
    source_status = models.CharField(max_length=32)
    source_reversal_status = models.CharField(max_length=32, default="ACTIVE")
    metadata_snapshot = models.JSONField(default=dict)
    captured_at = models.DateTimeField(auto_now_add=True)
    captured_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="captured_production_overheads",
    )


class ProductionCostAllocationRun(UUIDPrimaryKeyModel):
    legal_entity = models.ForeignKey("organizations.LegalEntity", on_delete=models.PROTECT)
    allocation_month = models.DateField()
    rule_code = models.CharField(max_length=32, default="CUT_QTY_MONTHLY")
    status = models.CharField(max_length=32, default="READY")
    created_at = models.DateTimeField(auto_now_add=True)
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)


class ProductionCostAllocationLine(UUIDPrimaryKeyModel):
    run = models.ForeignKey(
        ProductionCostAllocationRun, on_delete=models.PROTECT, related_name="lines"
    )
    source = models.ForeignKey(ProductionOverheadSnapshot, on_delete=models.PROTECT)
    output = models.ForeignKey("purchasing.WorkOrderOutput", on_delete=models.PROTECT)
    driver_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    driver_total = models.DecimalField(max_digits=18, decimal_places=6)
    ratio = models.DecimalField(max_digits=24, decimal_places=12)
    source_amount = models.DecimalField(max_digits=18, decimal_places=2)
    allocated_amount = models.DecimalField(max_digits=18, decimal_places=2)


class ProductionCostSnapshot(UUIDPrimaryKeyModel):
    work_order = models.ForeignKey("purchasing.WorkOrder", on_delete=models.PROTECT)
    output = models.ForeignKey("purchasing.WorkOrderOutput", on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    as_of_date = models.DateField()
    material_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    labor_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    direct_extra_amount = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    overhead_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    total_cogm = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    unit_hpp = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=32, default="INCOMPLETE")
    component_status = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("output", "version"), name="prod_cost_snapshot_ver_uq")
        ]
