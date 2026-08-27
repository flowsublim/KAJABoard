from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

from apps.organizations.selectors import accessible_legal_entities
from apps.production.models import (
    ProductionEntryState,
    ProductionRejectLine,
    ProductionStage,
    ProductionWorkLine,
)
from apps.purchasing.models import WorkOrder, WorkOrderState, WorkOrderType

ZERO = Decimal("0")


@dataclass(frozen=True)
class OutputWIP:
    output_id: object
    target_quantity: Decimal
    cut_quantity: Decimal
    sew_quantity: Decimal
    qc_quantity: Decimal
    reject_cut_quantity: Decimal
    reject_sew_quantity: Decimal
    reject_qc_quantity: Decimal

    @property
    def available_sewing(self):
        return self.cut_quantity - self.sew_quantity - self.reject_cut_quantity

    @property
    def available_qc(self):
        return self.sew_quantity - self.qc_quantity - self.reject_sew_quantity

    @property
    def qc_ready_quantity(self):
        return self.qc_quantity - self.reject_qc_quantity


def _sum(queryset):
    return queryset.aggregate(total=Sum("quantity"))["total"] or ZERO


def active_work_lines(*, output=None, stage=None):
    queryset = ProductionWorkLine.objects.filter(
        entry__state=ProductionEntryState.POSTED, reversal__isnull=True
    )
    if output is not None:
        queryset = queryset.filter(output=output)
    if stage:
        queryset = queryset.filter(entry__stage=stage)
    return queryset


def active_reject_lines(*, output=None, stage=None):
    queryset = ProductionRejectLine.objects.filter(
        entry__state=ProductionEntryState.POSTED, reversal__isnull=True
    )
    if output is not None:
        queryset = queryset.filter(output=output)
    if stage:
        queryset = queryset.filter(stage=stage)
    return queryset


def output_wip(output) -> OutputWIP:
    return OutputWIP(
        output_id=output.pk,
        target_quantity=output.target_quantity,
        cut_quantity=_sum(active_work_lines(output=output, stage=ProductionStage.CUT)),
        sew_quantity=_sum(active_work_lines(output=output, stage=ProductionStage.SEW)),
        qc_quantity=_sum(active_work_lines(output=output, stage=ProductionStage.QC_PACKING)),
        reject_cut_quantity=_sum(active_reject_lines(output=output, stage=ProductionStage.CUT)),
        reject_sew_quantity=_sum(active_reject_lines(output=output, stage=ProductionStage.SEW)),
        reject_qc_quantity=_sum(
            active_reject_lines(output=output, stage=ProductionStage.QC_PACKING)
        ),
    )


def output_wip_summaries(work_order):
    return tuple(output_wip(output) for output in work_order.outputs.order_by("line_number"))


def work_order_progress(work_order):
    summaries = output_wip_summaries(work_order)
    return (
        "IN_PROGRESS"
        if any(
            summary.cut_quantity or summary.sew_quantity or summary.qc_quantity
            for summary in summaries
        )
        else "NOT_STARTED"
    )


def eligible_internal_work_orders(user):
    return (
        WorkOrder.objects.filter(
            legal_entity__in=accessible_legal_entities(user),
            state=WorkOrderState.APPROVED,
            work_order_type=WorkOrderType.INTERNAL,
        )
        .select_related("legal_entity", "sales_order", "project")
        .prefetch_related("outputs")
        .order_by("-document_date", "-created_at")
    )


def production_work_entries(user):
    from apps.production.models import ProductionWorkEntry

    return (
        ProductionWorkEntry.objects.filter(legal_entity__in=accessible_legal_entities(user))
        .select_related("legal_entity", "work_order")
        .order_by("-production_date", "-created_at")
    )


def production_reject_entries(user):
    from apps.production.models import ProductionRejectEntry

    return (
        ProductionRejectEntry.objects.filter(legal_entity__in=accessible_legal_entities(user))
        .select_related("legal_entity", "work_order")
        .order_by("-production_date", "-created_at")
    )


def material_issue_candidates(user, *, work_order=None):
    """Read-only future Warehouse source contract; it creates no stock effect."""
    orders = eligible_internal_work_orders(user)
    if work_order is not None:
        orders = orders.filter(pk=work_order.pk)
    candidates = []
    for order in orders.prefetch_related(
        "material_allocations__output", "material_allocations__material_item"
    ):
        for allocation in order.material_allocations.all():
            candidates.append(
                {
                    "source_key": f"PROD_MATERIAL_REQ|{allocation.pk}",
                    "work_order_id": order.pk,
                    "work_order_number": order.document_number,
                    "output_id": allocation.output_id,
                    "allocation_id": allocation.pk,
                    "legal_entity_id": order.legal_entity_id,
                    "project_id": order.project_id,
                    "sales_order_id": order.sales_order_id,
                    "material_item_id": allocation.material_item_id,
                    "material_code_snapshot": allocation.material_code_snapshot,
                    "material_name_snapshot": allocation.material_name_snapshot,
                    "planned_quantity": allocation.planned_quantity,
                    "uom_code_snapshot": allocation.uom_code_snapshot,
                    "reference_cost": allocation.reference_cost,
                    "state": "ACTIVE",
                }
            )
    return tuple(candidates)
