from decimal import Decimal

from django.db.models import Q

from apps.finance.models import JournalLine, JournalState, PayableEntry, ReceivableEntry
from apps.finance.selectors.bank_reconciliation import (
    bank_statement_reconciliation,
    bank_statements,
)
from apps.finance.selectors.liquidity import bank_ledger, cash_ledger
from apps.finance.selectors.marketplace import marketplace_balance, marketplace_balance_entries
from apps.finance.selectors.wage_payables import wage_payable_reconciliation
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
    # Presentation GL deliberately shows only posted journals.  Controls must
    # additionally retain an original only when its immutable compensating
    # reversal is posted; together their signed effects net correctly.
    lines = list(general_ledger(legal_entity=legal_entity))
    reversed_lines = list(
        JournalLine.objects.filter(
            journal__legal_entity=legal_entity,
            journal__state=JournalState.REVERSED,
            journal__reversal__state=JournalState.POSTED,
        ).select_related("journal", "account")
    )
    control_lines = [*lines, *reversed_lines]
    debit = sum((line.debit for line in control_lines), Decimal("0"))
    credit = sum((line.credit for line in control_lines), Decimal("0"))
    ar_control = sum(
        (
            line.debit - line.credit
            for line in control_lines
            if line.line_role in {"AR_CONTROL", "RECEIVABLE"}
        ),
        Decimal("0"),
    )
    ar_rows = receivables(legal_entity=legal_entity)
    ar_detail = sum((row.open_amount for row in ar_rows), Decimal("0"))
    ap_rows = payables(legal_entity=legal_entity).filter(wage_accrual__isnull=True)
    ap_detail = sum((row.open_amount for row in ap_rows), Decimal("0"))
    ap_control = sum(
        (line.credit - line.debit for line in control_lines if line.line_role == "PAYABLE"),
        Decimal("0"),
    )
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
        (line.debit - line.credit for line in control_lines if line.line_role == "INVENTORY"),
        Decimal("0"),
    )
    if pending_valuation.exists():
        inventory_status = "PENDING_SOURCE"
    elif valued_movements.exists() or inventory_gl:
        inventory_status = "MATCH" if inventory_gl == warehouse_value else "DIFFERENCE"
    else:
        inventory_status = "PENDING_SOURCE"
    liquidity_entries = [
        *cash_ledger(legal_entity=legal_entity),
        *bank_ledger(legal_entity=legal_entity),
    ]
    liquidity_detail = sum(
        (entry.amount if entry.direction == "IN" else -entry.amount for entry in liquidity_entries),
        Decimal("0"),
    )
    marketplace_entries = marketplace_balance_entries(legal_entity=legal_entity)
    marketplace_detail = marketplace_balance(legal_entity=legal_entity)
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
        "ap": _fact(control=ap_control, detail=ap_detail, has_source=ap_rows.exists()),
        "inventory": {
            "status": inventory_status,
            "control": inventory_gl,
            "detail": warehouse_value,
        },
        "liquidity": _control_fact(
            lines=control_lines,
            line_role="LIQUIDITY",
            detail=liquidity_detail,
            has_source=bool(liquidity_entries),
        ),
        "marketplace_balance": _control_fact(
            lines=control_lines,
            line_role="MARKETPLACE_BALANCE",
            detail=marketplace_detail,
            has_source=marketplace_entries.exists(),
        ),
        "fixed_assets": _fixed_asset_reconciliation(legal_entity=legal_entity),
        "wage_payable": wage_payable_reconciliation(legal_entity=legal_entity),
        "bank_reconciliation": _bank_reconciliation(legal_entity=legal_entity),
    }


def _control_fact(*, lines, line_role, detail, has_source=False):
    control = sum(
        (line.debit - line.credit for line in lines if line.line_role == line_role),
        Decimal("0"),
    )
    has_fact = bool(control or detail or has_source)
    return {
        "status": (
            "MATCH"
            if has_fact and control == detail
            else "DIFFERENCE"
            if has_fact
            else "PENDING_SOURCE"
        ),
        "control": control,
        "detail": detail,
    }


def _fact(*, control, detail, has_source):
    return {
        "status": (
            "MATCH"
            if has_source and control == detail
            else "DIFFERENCE"
            if has_source
            else "PENDING_SOURCE"
        ),
        "control": control,
        "detail": detail,
    }


def _bank_reconciliation(*, legal_entity):
    facts = [
        bank_statement_reconciliation(statement=row)
        for row in bank_statements(legal_entity=legal_entity)
    ]
    if not facts:
        return {"status": "PENDING_SOURCE", "control": None, "detail": None, "statements": []}
    statuses = {row["status"] for row in facts}
    return {
        "status": (
            "DIFFERENCE"
            if "DIFFERENCE" in statuses
            else "PENDING_SOURCE"
            if "PENDING_SOURCE" in statuses
            else "MATCH"
        ),
        "control": sum((row["matched_amount"] for row in facts), Decimal("0")),
        "detail": sum((row["total_in"] + row["total_out"] for row in facts), Decimal("0")),
        "statements": facts,
    }


def _fixed_asset_reconciliation(*, legal_entity):
    from apps.finance.selectors.fixed_assets import fixed_asset_reconciliation

    return fixed_asset_reconciliation(legal_entity=legal_entity)
