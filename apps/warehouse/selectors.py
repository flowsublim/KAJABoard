from decimal import Decimal

from django.db.models import Sum

from apps.organizations.selectors import accessible_legal_entities
from apps.warehouse.models import (
    InternalConsumption,
    InventoryAdjustment,
    InventoryValuationState,
    MovementDirection,
    StockCount,
    StockMovement,
    SupplierReturn,
    ValuationStatus,
    WarehouseMaterialIssueLine,
    WarehousePurchaseReceiptLine,
    WarehouseReceiptLine,
    WarehouseSalesIssueLine,
    WarehouseSubcontractReceiptLine,
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
    ready_rows = rows.filter(valuation_status=ValuationStatus.READY, total_value__isnull=False)
    incoming_value = ready_rows.filter(direction=MovementDirection.IN).aggregate(
        value=Sum("total_value")
    )["value"] or Decimal("0")
    outgoing_value = ready_rows.filter(direction=MovementDirection.OUT).aggregate(
        value=Sum("total_value")
    )["value"] or Decimal("0")
    return {
        "quantity_on_hand": incoming - outgoing,
        "inventory_value": incoming_value - outgoing_value,
        "valuation_status": ValuationStatus.PENDING_VALUATION
        if rows.filter(valuation_status=ValuationStatus.PENDING_VALUATION).exists()
        else ValuationStatus.READY,
        "last_movement_sequence": rows.order_by("-posting_sequence")
        .values_list("posting_sequence", flat=True)
        .first()
        or 0,
    }


def purchase_receipt_candidates(user, *, purchase_order=None):
    from apps.purchasing.models import AccountingTreatment, PurchaseOrderLine, PurchaseOrderState

    qs = PurchaseOrderLine.objects.filter(
        purchase_order__legal_entity__in=accessible_legal_entities(user),
        purchase_order__state=PurchaseOrderState.CONFIRMED,
        accounting_treatment_snapshot=AccountingTreatment.INVENTORY,
        item__isnull=False,
        item__inventory_eligible=True,
    ).select_related("purchase_order", "purchase_order__vendor", "item", "purchase_category")
    if purchase_order is not None:
        qs = qs.filter(purchase_order=purchase_order)
    rows = []
    for line in qs.order_by(
        "purchase_order__document_date", "purchase_order__document_number", "line_number"
    ):
        received = _active_sum(
            WarehousePurchaseReceiptLine,
            "quantity",
            purchase_order_line=line,
            receipt__state="POSTED",
        )
        remaining = line.quantity - received
        if remaining > 0:
            rows.append(
                {
                    "source_key": f"PURCHASE_ORDER_LINE|{line.pk}",
                    "purchase_order": line.purchase_order,
                    "purchase_order_line": line,
                    "purchase_order_id": line.purchase_order_id,
                    "purchase_order_line_id": line.pk,
                    "legal_entity_id": line.purchase_order.legal_entity_id,
                    "vendor": line.purchase_order.vendor,
                    "item": line.item,
                    "item_id": line.item_id,
                    "ordered_quantity": line.quantity,
                    "received_quantity": received,
                    "remaining_quantity": remaining,
                    "unit_cost": line.unit_price,
                    "accounting_treatment": line.accounting_treatment_snapshot,
                    "category_snapshot": line.category_code_snapshot,
                }
            )
    return tuple(rows)


def _active_sum(model, field, **filters):
    return model.objects.filter(**filters).aggregate(total=Sum(field))["total"] or Decimal("0")


def subcontract_receipt_candidates(user):
    from apps.purchasing.models import SubcontractReceipt, SubcontractReceiptState
    from apps.quality.selectors import subcontract_pass_authorization

    rows = []
    for receipt in (
        SubcontractReceipt.objects.filter(
            legal_entity__in=accessible_legal_entities(user), state=SubcontractReceiptState.ACCEPTED
        )
        .select_related("work_order", "vendor")
        .prefetch_related("output_lines__item", "output_lines__output")
    ):
        for source in receipt.output_lines.all():
            if source.item.item_kind == "SERVICE" or not source.item.inventory_eligible:
                continue
            auth = subcontract_pass_authorization(source)
            posted = _active_sum(
                WarehouseSubcontractReceiptLine,
                "quantity",
                subcontract_receipt_line=source,
                receipt__state="POSTED",
            )
            remaining = min(auth["remaining_pass_quantity"], source.accepted_quantity - posted)
            if remaining > 0:
                rows.append(
                    {
                        "source_key": f"PURCH_SUBCON_RECEIPT|{source.pk}",
                        "receipt": receipt,
                        "receipt_line": source,
                        "receipt_id": receipt.pk,
                        "receipt_line_id": source.pk,
                        "work_order": receipt.work_order,
                        "vendor": receipt.vendor,
                        "item": source.item,
                        "item_id": source.item_id,
                        "presented_quantity": source.accepted_quantity,
                        "quality_pass_quantity": auth["posted_pass_quantity"],
                        "received_quantity": posted,
                        "remaining_quantity": remaining,
                        "valuation_status": "READY"
                        if _subcontract_cost(source.output) is not None
                        else "PENDING_VALUATION",
                    }
                )
    return tuple(rows)


def _subcontract_cost(output):
    from apps.production.models import ProductionCostSnapshot

    return (
        ProductionCostSnapshot.objects.filter(output=output, status="READY", unit_hpp__isnull=False)
        .order_by("-version")
        .values_list("unit_hpp", flat=True)
        .first()
    )


def sales_issue_candidates(user, *, warehouse=None, delivery=None):
    from apps.sales.models import SalesDeliveryLine, SalesDeliveryState

    qs = SalesDeliveryLine.objects.filter(
        sales_delivery__legal_entity__in=accessible_legal_entities(user),
        sales_delivery__state=SalesDeliveryState.POSTED,
    ).select_related(
        "sales_delivery", "sales_delivery__customer", "source_sales_order_line__sales_order", "item"
    )
    if delivery is not None:
        qs = qs.filter(sales_delivery=delivery)
    rows = []
    for line in qs.order_by(
        "sales_delivery__delivery_date", "sales_delivery__document_number", "line_number"
    ):
        issued = _active_sum(
            WarehouseSalesIssueLine, "quantity", sales_delivery_line=line, issue__state="POSTED"
        )
        remaining = line.quantity - issued
        available = None
        if warehouse is not None:
            state = InventoryValuationState.objects.filter(
                legal_entity=line.sales_delivery.legal_entity, warehouse=warehouse, item=line.item
            ).first()
            available = state.quantity_on_hand if state else Decimal("0")
        if remaining > 0:
            rows.append(
                {
                    "source_key": f"SALES_DELIVERY_LINE|{line.pk}",
                    "delivery": line.sales_delivery,
                    "delivery_line": line,
                    "delivery_id": line.sales_delivery_id,
                    "delivery_line_id": line.pk,
                    "sales_order": line.source_sales_order_line.sales_order,
                    "customer": line.sales_delivery.customer,
                    "item": line.item,
                    "delivery_quantity": line.quantity,
                    "issued_quantity": issued,
                    "remaining_quantity": remaining,
                    "available_quantity": available,
                }
            )
    return tuple(rows)


def operational_documents(user):
    entities = accessible_legal_entities(user)
    return {
        "purchase_receipts": WarehousePurchaseReceiptLine.objects.filter(
            receipt__legal_entity__in=entities
        ).select_related("receipt", "item"),
        "subcontract_receipts": WarehouseSubcontractReceiptLine.objects.filter(
            receipt__legal_entity__in=entities
        ).select_related("receipt", "item"),
        "sales_issues": WarehouseSalesIssueLine.objects.filter(
            issue__legal_entity__in=entities
        ).select_related("issue", "item"),
        "stock_counts": StockCount.objects.filter(legal_entity__in=entities).select_related(
            "warehouse"
        ),
        "adjustments": InventoryAdjustment.objects.filter(legal_entity__in=entities).select_related(
            "warehouse"
        ),
        "internal_consumptions": InternalConsumption.objects.filter(
            legal_entity__in=entities
        ).select_related("warehouse"),
        "supplier_returns": SupplierReturn.objects.filter(legal_entity__in=entities).select_related(
            "warehouse", "supplier"
        ),
    }


def reconciliation_rows(user, *, warehouse=None, item=None):
    entities = accessible_legal_entities(user)
    states = InventoryValuationState.objects.filter(legal_entity__in=entities).select_related(
        "legal_entity", "warehouse", "item"
    )
    if warehouse is not None:
        states = states.filter(warehouse=warehouse)
    if item is not None:
        states = states.filter(item=item)
    rows = []
    for state in states:
        computed = recomputed_balance(
            legal_entity=state.legal_entity, warehouse=state.warehouse, item=state.item
        )
        pending = (
            computed["valuation_status"] == ValuationStatus.PENDING_VALUATION
            or state.valuation_status == ValuationStatus.PENDING_VALUATION
        )
        status = "PENDING_VALUATION" if pending else "MATCH"
        if not pending and state.quantity_on_hand != computed["quantity_on_hand"]:
            status = "QTY_MISMATCH"
        elif not pending and state.inventory_value != computed["inventory_value"]:
            status = "VALUE_MISMATCH"
        rows.append(
            {
                "legal_entity": state.legal_entity,
                "warehouse": state.warehouse,
                "item": state.item,
                "state": state,
                "recomputed": computed,
                "status": status,
            }
        )
    return tuple(rows)


def finance_candidates(user, *, movement_type=None):
    qs = StockMovement.objects.filter(
        legal_entity__in=accessible_legal_entities(user), state="POSTED"
    ).select_related("legal_entity", "warehouse", "item")
    if movement_type:
        qs = qs.filter(movement_type=movement_type)
    event_by_type = {
        "PURCHASE_RECEIPT": "WAREHOUSE_PURCHASE_RECEIPT",
        "SUBCONTRACT_RECEIPT": "WAREHOUSE_SUBCONTRACT_RECEIPT",
        "SALES_DELIVERY_ISSUE": "WAREHOUSE_SALES_ISSUE",
        "INTERNAL_CONSUMPTION": "WAREHOUSE_INTERNAL_CONSUMPTION",
        "SUPPLIER_RETURN": "WAREHOUSE_SUPPLIER_RETURN",
        "OPNAME_GAIN": "WAREHOUSE_OPNAME_GAIN",
        "OPNAME_LOSS": "WAREHOUSE_OPNAME_LOSS",
        "INVENTORY_ADJUSTMENT": "WAREHOUSE_ADJUSTMENT",
        "PRODUCTION_MATERIAL_ISSUE": "WAREHOUSE_PRODUCTION_MATERIAL_ISSUE",
        "PRODUCTION_FINISHED_GOODS_RECEIPT": "WAREHOUSE_PRODUCTION_RECEIPT",
    }
    return tuple(
        {
            "event_key": f"{event_by_type.get(row.movement_type, 'WAREHOUSE_MOVEMENT')}|{row.pk}",
            "event_code": event_by_type.get(row.movement_type, "WAREHOUSE_MOVEMENT"),
            "legal_entity_id": row.legal_entity_id,
            "source_module": row.source_module,
            "source_type": row.source_type,
            "source_document_id": row.source_document_id,
            "source_line_id": row.source_line_id,
            "movement_id": row.pk,
            "item_id": row.item_id,
            "warehouse_id": row.warehouse_id,
            "quantity": row.quantity,
            "unit_cost": row.unit_cost,
            "value": row.total_value,
            "transaction_date": row.transaction_date,
            "active": row.state == "POSTED",
            "mapping_readiness": "BLOCKED_MAPPING",
        }
        for row in qs.order_by("posting_sequence")
    )


warehouse_finance_candidates = finance_candidates
inventory_reconciliation = reconciliation_rows
purchase_receipt_queue = purchase_receipt_candidates
subcontract_receipt_queue = subcontract_receipt_candidates
sales_issue_queue = sales_issue_candidates


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
