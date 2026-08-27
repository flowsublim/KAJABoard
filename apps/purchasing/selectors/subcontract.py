from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

from apps.organizations.selectors import accessible_legal_entities
from apps.purchasing.models import (
    SubcontractCostType,
    SubcontractDispatchState,
    SubcontractMaterialDispatch,
    SubcontractReceipt,
    SubcontractReceiptState,
    WorkOrder,
    WorkOrderState,
    WorkOrderType,
)


@dataclass(frozen=True)
class WarehouseCandidate:
    source_key: str
    source_type: str
    source_line_id: str
    work_order_id: str
    output_id: str
    quantity: Decimal
    uom: str
    active: bool


def _scope(user):
    return accessible_legal_entities(user)


def material_dispatches(user):
    return (
        SubcontractMaterialDispatch.objects.select_related("work_order", "vendor")
        .filter(legal_entity__in=_scope(user))
        .order_by("-dispatch_date", "-created_at")
    )


def subcontract_receipts(user):
    return (
        SubcontractReceipt.objects.select_related("work_order", "vendor")
        .filter(legal_entity__in=_scope(user))
        .order_by("-receipt_date", "-created_at")
    )


def dispatch_allowance(allocation):
    sent = allocation.dispatch_lines.filter(
        dispatch__state=SubcontractDispatchState.CONFIRMED
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    return allocation.planned_quantity - sent


def output_remaining(output):
    accepted = output.receipt_lines.filter(
        receipt__state=SubcontractReceiptState.ACCEPTED
    ).aggregate(total=Sum("accepted_quantity"))["total"] or Decimal("0")
    return output.target_quantity - accepted


def approved_subcontract_sources(user):
    return (
        WorkOrder.objects.select_related("vendor", "project", "sales_order")
        .prefetch_related("outputs__material_allocations")
        .filter(
            legal_entity__in=_scope(user),
            state=WorkOrderState.APPROVED,
            work_order_type=WorkOrderType.SUBCONTRACT,
        )
    )


def warehouse_material_issue_candidates(user):
    lines = (
        SubcontractMaterialDispatch.objects.filter(
            legal_entity__in=_scope(user), state=SubcontractDispatchState.CONFIRMED
        )
        .select_related("work_order", "work_order__project", "work_order__sales_order", "vendor")
        .prefetch_related("lines__allocation__output")
    )
    return tuple(
        WarehouseCandidate(
            source_key=f"PURCH_MATL_ISSUE|{line.pk}",
            source_type="PURCH_MATL_ISSUE",
            source_line_id=str(line.pk),
            work_order_id=str(line.dispatch.work_order_id),
            output_id=str(line.allocation.output_id),
            quantity=line.quantity,
            uom=line.uom_code_snapshot,
            active=True,
        )
        for dispatch in lines
        for line in dispatch.lines.all()
    )


def warehouse_subcontract_receipt_candidates(user):
    receipts = (
        SubcontractReceipt.objects.filter(
            legal_entity__in=_scope(user), state=SubcontractReceiptState.ACCEPTED
        )
        .select_related("work_order", "vendor")
        .prefetch_related("output_lines")
    )
    return tuple(
        WarehouseCandidate(
            source_key=f"PURCH_SUBCON_RECEIPT|{line.pk}",
            source_type="PURCH_SUBCON_RECEIPT",
            source_line_id=str(line.pk),
            work_order_id=str(receipt.work_order_id),
            output_id=str(line.output_id),
            quantity=line.accepted_quantity,
            uom=line.uom_code_snapshot,
            active=True,
        )
        for receipt in receipts
        for line in receipt.output_lines.all()
    )


def subcontract_fulfillment(work_order):
    if work_order.work_order_type != WorkOrderType.SUBCONTRACT:
        return {"status": "NOT_AVAILABLE", "outputs": ()}
    outputs = []
    complete = True
    any_accepted = False
    for output in work_order.outputs.all():
        remaining = output_remaining(output)
        accepted = output.target_quantity - remaining
        any_accepted |= accepted > 0
        complete &= remaining == 0
        outputs.append(
            {
                "output_id": str(output.pk),
                "target": output.target_quantity,
                "accepted": accepted,
                "remaining": remaining,
                "percent": (accepted / output.target_quantity * Decimal("100")),
            }
        )
    return {
        "status": "COMPLETE"
        if outputs and complete
        else "PARTIAL"
        if any_accepted
        else "NOT_STARTED",
        "outputs": tuple(outputs),
    }


def subcontract_hpp_sources(work_order):
    materials = []
    for allocation in work_order.material_allocations.all():
        dispatched = allocation.dispatch_lines.filter(
            dispatch__state=SubcontractDispatchState.CONFIRMED
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        materials.append(
            {
                "type": "MATERIAL_SUPPLIED",
                "allocation_id": str(allocation.pk),
                "output_id": str(allocation.output_id),
                "quantity": dispatched,
                "reference_cost": allocation.reference_cost,
                "provisional_value": dispatched * allocation.reference_cost
                if allocation.reference_cost is not None
                else None,
            }
        )
    costs = work_order.subcontract_receipts.filter(
        state=SubcontractReceiptState.ACCEPTED
    ).prefetch_related("cost_lines")
    specific, shared = [], []
    for receipt in costs:
        for line in receipt.cost_lines.all():
            target = specific if line.cost_type == SubcontractCostType.SPECIFIC_SERVICE else shared
            target.append(
                {
                    "cost_line_id": str(line.pk),
                    "receipt_id": str(receipt.pk),
                    "output_id": str(line.output_id) if line.output_id else None,
                    "amount": line.amount,
                }
            )
    return {
        "materials": tuple(materials),
        "specific_service": tuple(specific),
        "shared_service": tuple(shared),
    }
