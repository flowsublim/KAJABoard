from decimal import Decimal

from django.db.models import Sum

from apps.finance.models import (
    BankReconciliationMatch,
    BankReconciliationMatchState,
    BankStatement,
    LiquidityDirection,
)
from apps.finance.selectors.liquidity import bank_ledger


def bank_statements(*, legal_entity):
    return BankStatement.objects.filter(legal_entity=legal_entity).select_related(
        "liquidity_account"
    )


def bank_statement_reconciliation(*, statement):
    lines = statement.lines.all().prefetch_related("matches")
    incoming = sum(
        (line.amount for line in lines if line.direction == LiquidityDirection.IN), Decimal("0")
    )
    outgoing = sum(
        (line.amount for line in lines if line.direction == LiquidityDirection.OUT), Decimal("0")
    )
    arithmetic = (
        "PENDING_SOURCE"
        if statement.opening_balance is None or statement.closing_balance is None
        else "MATCH"
        if statement.opening_balance + incoming - outgoing == statement.closing_balance
        else "STATEMENT_DIFFERENCE"
    )
    matched = sum(
        (
            line.matches.filter(state=BankReconciliationMatchState.ACTIVE).aggregate(
                value=Sum("matched_amount")
            )["value"]
            or Decimal("0")
            for line in lines
        ),
        Decimal("0"),
    )
    ledger_entries = list(
        bank_ledger(
            legal_entity=statement.legal_entity,
            liquidity_account=statement.liquidity_account,
            start=statement.start_date,
            end=statement.end_date,
        )
    )
    allocations = (
        BankReconciliationMatch.objects.filter(
            liquidity_entry_id__in=[entry.pk for entry in ledger_entries],
            state=BankReconciliationMatchState.ACTIVE,
        )
        .values("liquidity_entry_id")
        .annotate(value=Sum("matched_amount"))
    )
    allocated_by_entry = {row["liquidity_entry_id"]: row["value"] for row in allocations}
    unmatched_ledger = sum(
        (entry.amount - allocated_by_entry.get(entry.pk, Decimal("0")) for entry in ledger_entries),
        Decimal("0"),
    )
    unmatched_statement = incoming + outgoing - matched
    return {
        "status": "MATCH"
        if arithmetic == "MATCH" and not unmatched_statement and not unmatched_ledger
        else "PENDING_SOURCE"
        if arithmetic == "PENDING_SOURCE"
        else "DIFFERENCE",
        "statement_arithmetic": arithmetic,
        "total_in": incoming,
        "total_out": outgoing,
        "matched_amount": matched,
        "unmatched_statement_amount": unmatched_statement,
        "unmatched_ledger_amount": unmatched_ledger,
        "ledger_entries": ledger_entries,
    }


def bank_match_candidates(*, statement_line):
    return bank_ledger(
        legal_entity=statement_line.statement.legal_entity,
        liquidity_account=statement_line.statement.liquidity_account,
    ).filter(direction=statement_line.direction, currency=statement_line.statement.currency)
