from decimal import Decimal

from django.db.models import Sum

from apps.organizations.selectors import accessible_legal_entities
from apps.warehouse.models import (
    InventoryValuationState,
    MovementDirection,
    StockMovement,
    ValuationStatus,
    WarehouseMaterialIssueLine,
    WarehouseReceiptLine,
)


def stock_balances(user, *, warehouse=None, item=None):
    qs = InventoryValuationState.objects.filter(
        legal_entity__in=accessible_legal_entities(user)
    ).select_related("warehouse", "item", "legal_entity")
    if warehouse is not None:
        qs = qs.filter(warehouse=warehouse)
    if item is not None:
        qs = qs.filter(item=item)
    return qs.order_by("warehouse__code", "item__code")


def stock_movements(user, *, warehouse=None, item=None):
    qs = StockMovement.objects.filter(
        legal_entity__in=accessible_legal_entities(user)
    ).select_related("warehouse", "item", "posted_by", "reversal_of")
    if warehouse is not None:
        qs = qs.filter(warehouse=warehouse)
    if item is not None:
        qs = qs.filter(item=item)
    return qs.order_by("-posting_sequence")


def recomputed_balance(*, legal_entity, warehouse, item):
    rows = StockMovement.objects.filter(
        legal_entity=legal_entity,
        warehouse=warehouse,
        item=item,
        state="POSTED",
    )
    incoming = rows.filter(direction=MovementDirection.IN).aggregate(qty=Sum("quantity"))[
        "qty"
    ] or Decimal("0")
    outgoing = rows.filter(direction=MovementDirection.OUT).aggregate(qty=Sum("quantity"))[
        "qty"
    ] or Decimal("0")
    values = rows.filter(valuation_status=ValuationStatus.READY).aggregate(
        value=Sum("total_value")
    )["value"]
    return {"quantity_on_hand": incoming - outgoing, "inventory_value": values}


def production_material_issue_candidates(user, *, work_order=None):
    from apps.production.selectors.wip import material_issue_candidates

    candidates = list(material_issue_candidates(user, work_order=work_order))
    for row in candidates:
        issued = WarehouseMaterialIssueLine.objects.filter(
            allocation_id=row["allocation_id"], issue__state="POSTED"
        ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        row["issued_quantity"] = issued
        row["remaining_quantity"] = row["planned_quantity"] - issued
    return tuple(row for row in candidates if row["remaining_quantity"] > 0)


def production_receipt_candidates(user, *, work_order=None):
    from apps.production.selectors.wip import warehouse_receipt_candidates
    from apps.quality.selectors import quality_pass_authorization

    candidates = []
    for row in warehouse_receipt_candidates(user, work_order=work_order):
        accepted = WarehouseReceiptLine.objects.filter(
            handover_line_id=row["handover_line_id"], receipt__state="POSTED"
        ).aggregate(total=Sum("accepted_quantity"))["total"] or Decimal("0")
        row = dict(row)
        row["accepted_quantity"] = accepted
        row["remaining_quantity"] = row["quantity"] - accepted
        authorization = quality_pass_authorization(row["handover_line_id"])
        row["quality_pass_quantity"] = authorization["posted_pass_quantity"]
        row["quality_remaining_pass_quantity"] = authorization["remaining_pass_quantity"]
        row["pending_inspection_quantity"] = authorization["pending_inspection_quantity"]
        row["remaining_quantity"] = min(
            row["remaining_quantity"], authorization["remaining_pass_quantity"]
        )
        candidates.append(row)
    return tuple(
        row
        for row in candidates
        if row["remaining_quantity"] > 0 and row["quality_remaining_pass_quantity"] > 0
    )


def production_material_actual_cost(*, output):
    rows = StockMovement.objects.filter(
        movement_type="PRODUCTION_MATERIAL_ISSUE",
        direction=MovementDirection.OUT,
        state="POSTED",
        source_line_id=str(output.pk),
    )
    return rows.filter(valuation_status=ValuationStatus.READY).aggregate(total=Sum("total_value"))[
        "total"
    ]


def posted_production_receipt_quantity(handover_line):
    """Public read contract used by Quality's downstream dependency guard."""
    return WarehouseReceiptLine.objects.filter(
        handover_line=handover_line,
        receipt__state="POSTED",
    ).aggregate(total=Sum("accepted_quantity"))["total"] or Decimal("0")
