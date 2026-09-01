from decimal import Decimal

from django.db.models import Q

from apps.finance.models import JournalLine, PayableEntry, ReceivableEntry
from apps.warehouse.models import MovementDirection, StockMovement, ValuationStatus


def general_ledger(*, legal_entity, start=None, end=None, account=None, event_code=None):
    queryset = JournalLine.objects.filter(
        journal__legal_entity=legal_entity, journal__state="POSTED"
    ).select_related("journal", "account")
    if start:
        queryset = queryset.filter(journal__accounting_date__gte=start)
    if end:
        queryset = queryset.filter(journal__accounting_date__lte=end)
    if account:
        queryset = queryset.filter(account=account)
    if event_code:
        queryset = queryset.filter(journal__event_code=event_code)
    return queryset.order_by("journal__accounting_date", "journal__journal_number", "sequence")


def receivables(*, legal_entity):
    return (
        ReceivableEntry.objects.filter(legal_entity=legal_entity)
        .select_related("journal", "partner", "store")
        .order_by("accounting_date")
    )


def payables(*, legal_entity):
    return (
        PayableEntry.objects.filter(legal_entity=legal_entity)
        .select_related("journal", "partner")
        .order_by("accounting_date")
    )


def reconciliation(*, legal_entity):
    lines = general_ledger(legal_entity=legal_entity)
    debit = sum((line.debit for line in lines), Decimal("0"))
    credit = sum((line.credit for line in lines), Decimal("0"))
    ar_control = sum(
        (
            line.debit - line.credit
            for line in lines
            if line.line_role in {"AR_CONTROL", "RECEIVABLE"}
        ),
        Decimal("0"),
    )
    ar_rows = receivables(legal_entity=legal_entity)
    ar_detail = sum((row.open_amount for row in ar_rows), Decimal("0"))
    valued_movements = StockMovement.objects.filter(
        legal_entity=legal_entity,
        state="POSTED",
        valuation_status=ValuationStatus.READY,
        total_value__isnull=False,
    )
    pending_valuation = StockMovement.objects.filter(legal_entity=legal_entity).filter(
        Q(total_value__isnull=True) | ~Q(valuation_status=ValuationStatus.READY)
    )
    warehouse_value = sum(
        (
            movement.total_value
            if movement.direction == MovementDirection.IN
            else -movement.total_value
            for movement in valued_movements
        ),
        Decimal("0"),
    )
    inventory_gl = sum(
        (line.debit - line.credit for line in lines if line.line_role == "INVENTORY"),
        Decimal("0"),
    )
    if pending_valuation.exists():
        inventory_status = "PENDING_SOURCE"
    elif valued_movements.exists() or inventory_gl:
        inventory_status = "MATCH" if inventory_gl == warehouse_value else "DIFFERENCE"
    else:
        inventory_status = "PENDING_SOURCE"
    return {
        "journal": {
            "status": "MATCH" if debit == credit else "DIFFERENCE",
            "debit": debit,
            "credit": credit,
        },
        "ar": {
            "status": (
                "MATCH"
                if (ar_rows.exists() or ar_control) and ar_control == ar_detail
                else "DIFFERENCE"
                if ar_rows.exists() or ar_control
                else "PENDING_SOURCE"
            ),
            "control": ar_control,
            "detail": ar_detail,
        },
        "ap": {"status": "PENDING_SOURCE", "reason": "No approved AP source integrated."},
        "inventory": {
            "status": inventory_status,
            "control": inventory_gl,
            "detail": warehouse_value,
        },
    }
