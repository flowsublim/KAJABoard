"""Warehouse valuation boundary: no Finance-created stock or quantity ledger."""

from apps.finance.services.posting import post_journal
from apps.warehouse.models import MovementDirection, ValuationStatus


def warehouse_valuation_readiness(movement):
    """Return only authoritative Warehouse facts; posting needs explicit mapped event semantics."""
    if movement.valuation_status != ValuationStatus.READY or movement.total_value is None:
        return {"status": "PENDING_SOURCE", "movement_id": str(movement.pk)}
    return {
        "status": "READY",
        "movement_id": str(movement.pk),
        "accounting_date": movement.transaction_date,
        "valuation_amount": movement.total_value,
        "source_key": f"WAREHOUSE_VALUATION|{movement.pk}",
    }


def post_warehouse_valuation(movement, *, actor):
    readiness = warehouse_valuation_readiness(movement)
    if readiness["status"] != "READY":
        return readiness
    if movement.direction == MovementDirection.IN:
        lines = (
            {"line_role": "INVENTORY", "dc": "DEBIT", "amount": movement.total_value},
            {
                "line_role": "INVENTORY_OFFSET",
                "dc": "CREDIT",
                "amount": movement.total_value,
            },
        )
    else:
        lines = (
            {
                "line_role": "INVENTORY_OFFSET",
                "dc": "DEBIT",
                "amount": movement.total_value,
            },
            {"line_role": "INVENTORY", "dc": "CREDIT", "amount": movement.total_value},
        )
    return post_journal(
        legal_entity=movement.legal_entity,
        source_key=readiness["source_key"],
        source_module="WAREHOUSE",
        source_document_type="StockMovement",
        source_document_id=movement.pk,
        event_code="WAREHOUSE_VALUATION",
        accounting_date=movement.transaction_date,
        lines=lines,
        actor=actor,
        source_reference={
            "stock_movement_id": str(movement.pk),
            "warehouse_source_key": movement.source_key,
            "warehouse_id": str(movement.warehouse_id),
            "item_id": str(movement.item_id),
            "quantity": str(movement.quantity),
            "valuation_amount": str(movement.total_value),
        },
        description=f"Warehouse valuation {movement.source_key}",
    )
