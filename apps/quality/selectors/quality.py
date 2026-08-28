from decimal import Decimal

from django.db.models import Sum

from apps.organizations.selectors import accessible_legal_entities
from apps.quality.models import (
    InspectionType,
    QualityDocumentState,
    QualityInspection,
    QualityInspectionLine,
)

ZERO = Decimal("0")


def _sum(qs, field):
    return qs.aggregate(total=Sum(field))["total"] or ZERO


def quality_inspections(user):
    return (
        QualityInspection.objects.filter(legal_entity__in=accessible_legal_entities(user))
        .select_related("legal_entity", "inspector", "created_by", "posted_by")
        .prefetch_related("lines__item", "lines__production_handover_line")
        .order_by("-inspection_date", "-created_at")
    )


def _active_posted_lines(*, handover_line=None, subcontract_receipt_line=None, output=None):
    qs = QualityInspectionLine.objects.filter(
        inspection__state=QualityDocumentState.POSTED, reversal__isnull=True
    )
    if handover_line is not None:
        qs = qs.filter(production_handover_line=handover_line)
    if subcontract_receipt_line is not None:
        qs = qs.filter(subcontract_receipt_line=subcontract_receipt_line)
    if output is not None:
        qs = qs.filter(work_order_output=output)
    return qs


def quality_disposition_totals(
    source_line=None, *, handover_line=None, subcontract_receipt_line=None
):
    """Return active, posted quantities for one exact source line.

    This is a read contract. Reversed inspection lines and reversed documents never
    contribute to authorization.
    """
    handover_line = handover_line or (
        source_line
        if source_line is not None
        and source_line.__class__.__name__ == "ProductionWarehouseHandoverLine"
        else None
    )
    subcontract_receipt_line = subcontract_receipt_line or (
        source_line
        if source_line is not None
        and source_line.__class__.__name__ == "SubcontractReceiptOutputLine"
        else None
    )
    lines = _active_posted_lines(
        handover_line=handover_line, subcontract_receipt_line=subcontract_receipt_line
    )
    return {
        "presented_quantity": _sum(lines, "qty_presented"),
        "inspected_quantity": _sum(lines, "qty_inspected"),
        "pass_quantity": _sum(lines, "qty_pass"),
        "hold_quantity": _sum(lines, "qty_hold"),
        "reject_quantity": _sum(lines, "qty_reject"),
        "rework_quantity": _sum(lines, "qty_rework"),
        "legacy_unmapped_quantity": _sum(lines, "qty_legacy_unmapped"),
    }


def _warehouse_accepted(handover_line):
    from apps.warehouse.models import WarehouseDocumentState, WarehouseReceiptLine

    return (
        WarehouseReceiptLine.objects.filter(
            handover_line=handover_line,
            receipt__state=WarehouseDocumentState.POSTED,
        ).aggregate(total=Sum("accepted_quantity"))["total"]
        or ZERO
    )


def quality_pass_authorization(handover_line):
    """Public Warehouse contract for one Production handover line."""
    if not hasattr(handover_line, "handover_id"):
        from apps.production.models import ProductionWarehouseHandoverLine

        handover_line = ProductionWarehouseHandoverLine.objects.select_related(
            "handover", "output", "item"
        ).get(pk=handover_line)
    totals = quality_disposition_totals(handover_line=handover_line)
    accepted = _warehouse_accepted(handover_line)
    remaining = max(totals["pass_quantity"] - accepted, ZERO)
    return {
        "source_key": f"QUALITY_PASS|{handover_line.pk}",
        "source_module": "quality",
        "source_type": "PRODUCTION_FINISHED_GOODS",
        "source_line_id": str(handover_line.pk),
        "handover_line_id": handover_line.pk,
        "handover_id": handover_line.handover_id,
        "work_order_id": handover_line.handover.work_order_id,
        "work_order_output_id": handover_line.output_id,
        "item_id": handover_line.item_id,
        "legal_entity_id": handover_line.handover.legal_entity_id,
        "presented_quantity": handover_line.quantity,
        "posted_pass_quantity": totals["pass_quantity"],
        "posted_inspected_quantity": totals["inspected_quantity"],
        "posted_hold_quantity": totals["hold_quantity"],
        "posted_reject_quantity": totals["reject_quantity"],
        "posted_rework_quantity": totals["rework_quantity"],
        "posted_legacy_unmapped_quantity": totals["legacy_unmapped_quantity"],
        "warehouse_accepted_pass_quantity": accepted,
        "remaining_pass_quantity": remaining,
        "pending_inspection_quantity": max(
            handover_line.quantity - totals["inspected_quantity"], ZERO
        ),
        "active": remaining > ZERO,
    }


def subcontract_pass_authorization(receipt_line):
    from apps.purchasing.models import SubcontractReceiptOutputLine

    if not hasattr(receipt_line, "receipt_id"):
        receipt_line = SubcontractReceiptOutputLine.objects.select_related(
            "receipt", "output", "item"
        ).get(pk=receipt_line)
    totals = quality_disposition_totals(subcontract_receipt_line=receipt_line)
    return {
        "source_key": f"QUALITY_PASS|SUBCONTRACT|{receipt_line.pk}",
        "source_module": "quality",
        "source_type": "SUBCONTRACT_RECEIPT",
        "source_document_id": str(receipt_line.receipt_id),
        "source_line_id": str(receipt_line.pk),
        "receipt_line_id": receipt_line.pk,
        "work_order_id": receipt_line.receipt.work_order_id,
        "work_order_output_id": receipt_line.output_id,
        "item_id": receipt_line.item_id,
        "legal_entity_id": receipt_line.receipt.legal_entity_id,
        "presented_quantity": receipt_line.accepted_quantity,
        "posted_pass_quantity": totals["pass_quantity"],
        "posted_inspected_quantity": totals["inspected_quantity"],
        "posted_hold_quantity": totals["hold_quantity"],
        "posted_reject_quantity": totals["reject_quantity"],
        "posted_rework_quantity": totals["rework_quantity"],
        "remaining_pass_quantity": totals["pass_quantity"],
        "pending_inspection_quantity": max(
            receipt_line.accepted_quantity - totals["inspected_quantity"], ZERO
        ),
        "warehouse_posting": "NOT_IMPLEMENTED",
        "active": totals["pass_quantity"] > ZERO,
    }


def warehouse_pass_authorizations(user=None, *, handover_line=None, subcontract_receipt_line=None):
    if subcontract_receipt_line is not None:
        return (subcontract_pass_authorization(subcontract_receipt_line),)
    from apps.production.models import ProductionHandoverState, ProductionWarehouseHandoverLine

    if handover_line is not None:
        return (quality_pass_authorization(handover_line),)
    qs = ProductionWarehouseHandoverLine.objects.filter(
        handover__state=ProductionHandoverState.READY_FOR_GUDANG,
        reversal__isnull=True,
    ).select_related("handover", "handover__work_order", "output", "item")
    if user is not None:
        qs = qs.filter(handover__legal_entity__in=accessible_legal_entities(user))
    return tuple(quality_pass_authorization(line) for line in qs)


def production_quality_queue(user):
    from apps.production.models import ProductionHandoverState, ProductionWarehouseHandoverLine

    rows = []
    lines = (
        ProductionWarehouseHandoverLine.objects.filter(
            handover__state=ProductionHandoverState.READY_FOR_GUDANG,
            reversal__isnull=True,
            handover__legal_entity__in=accessible_legal_entities(user),
        )
        .select_related("handover__work_order", "output", "item")
        .order_by("handover__handover_date", "handover__work_order__document_number", "sequence")
    )
    for line in lines:
        authorization = quality_pass_authorization(line)
        rows.append(
            {
                **authorization,
                "handover_line": line,
                "work_order_number": line.handover.work_order.document_number,
                "item_code_snapshot": line.item_code_snapshot,
                "item_name_snapshot": line.item_name_snapshot,
            }
        )
    return tuple(row for row in rows if row["pending_inspection_quantity"] > ZERO)


def subcontract_quality_candidates(user):
    from apps.purchasing.models import SubcontractReceiptOutputLine, SubcontractReceiptState

    lines = (
        SubcontractReceiptOutputLine.objects.filter(
            receipt__legal_entity__in=accessible_legal_entities(user),
            receipt__state=SubcontractReceiptState.ACCEPTED,
        )
        .select_related("receipt__work_order", "output", "item")
        .order_by("receipt__receipt_date", "receipt__document_number", "line_number")
    )
    rows = []
    for line in lines:
        authorization = subcontract_pass_authorization(line)
        rows.append(
            {
                "source_key": f"PURCH_SUBCON_RECEIPT|{line.pk}",
                "source_module": "purchasing",
                "source_type": "SUBCONTRACT_RECEIPT",
                "source_document_id": str(line.receipt_id),
                "source_line_id": str(line.pk),
                "receipt_line": line,
                "work_order_id": line.receipt.work_order_id,
                "work_order_output_id": line.output_id,
                "item_id": line.item_id,
                "presented_quantity": authorization["presented_quantity"],
                "pass_quantity": authorization["posted_pass_quantity"],
                "hold_quantity": authorization["posted_hold_quantity"],
                "reject_quantity": authorization["posted_reject_quantity"],
                "rework_quantity": authorization["posted_rework_quantity"],
                "pending_inspection_quantity": authorization["pending_inspection_quantity"],
                "remaining_pass_quantity": authorization["remaining_pass_quantity"],
                "warehouse_posting": "NOT_IMPLEMENTED",
            }
        )
    return tuple(row for row in rows if row["pending_inspection_quantity"] > ZERO)


def rework_candidates(user=None):
    qs = QualityInspectionLine.objects.filter(
        inspection__state=QualityDocumentState.POSTED,
        inspection__inspection_type=InspectionType.PRODUCTION_FINISHED_GOODS,
        reversal__isnull=True,
        qty_rework__gt=ZERO,
    ).select_related(
        "inspection__legal_entity",
        "production_handover_line__handover__work_order",
        "work_order_output",
        "item",
    )
    if user is not None:
        qs = qs.filter(inspection__legal_entity__in=accessible_legal_entities(user))
    return tuple(
        {
            "source_key": f"QUALITY_REWORK|{line.pk}",
            "legal_entity_id": line.inspection.legal_entity_id,
            "source_inspection_id": line.inspection_id,
            "source_line_id": line.pk,
            "work_order_id": (
                line.production_handover_line.handover.work_order_id
                if line.production_handover_line_id
                else line.work_order_output.work_order_id
                if line.work_order_output_id
                else None
            ),
            "work_order_output_id": line.work_order_output_id,
            "item_id": line.item_id,
            "quantity": line.qty_rework,
            "reason_code": line.reason_code_snapshot,
            "reason": line.reason_text,
            "active": True,
        }
        for line in qs.order_by("inspection__inspection_date", "sequence")
    )


def return_quality_source_contract(
    *,
    legal_entity_id,
    source_module,
    source_type,
    source_document_id,
    source_key,
    source_line_id,
    item_id,
    quantity,
):
    """Source-neutral return contract; registration creates no stock effect."""
    return {
        "legal_entity_id": legal_entity_id,
        "source_module": source_module,
        "source_type": source_type,
        "source_document_id": str(source_document_id),
        "source_key": source_key,
        "source_line_id": str(source_line_id),
        "item_id": item_id,
        "presented_quantity": Decimal(str(quantity)),
        "warehouse_disposition": "PASS_ONLY_FUTURE_RETURN_IN",
        "stock_effect": "NONE",
    }
