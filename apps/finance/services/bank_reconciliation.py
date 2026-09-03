from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.finance.models import (
    BankReconciliationMatch,
    BankReconciliationMatchState,
    BankStatement,
    BankStatementLine,
    LiquidityAccountType,
    LiquidityDirection,
)


def _whole(value):
    value = Decimal(str(value))
    if value <= 0 or value != value.to_integral_value():
        raise ValidationError("Amount must be positive whole Rupiah.")
    return value


@transaction.atomic
def create_bank_statement(
    *,
    legal_entity,
    liquidity_account,
    statement_reference,
    start_date,
    end_date,
    closing_balance=None,
    opening_balance=None,
    currency="IDR",
    actor=None,
    **kwargs,
):
    if (
        liquidity_account.legal_entity_id != legal_entity.pk
        or liquidity_account.account_type != LiquidityAccountType.BANK
    ):
        raise ValidationError(
            "Bank statements require a BANK liquidity account belonging to the entity."
        )
    if liquidity_account.currency != currency:
        raise ValidationError("Statement currency must match the BANK liquidity account.")
    statement, _ = BankStatement.objects.get_or_create(
        legal_entity=legal_entity,
        liquidity_account=liquidity_account,
        statement_reference=statement_reference,
        defaults={
            "start_date": start_date,
            "end_date": end_date,
            "opening_balance": opening_balance,
            "closing_balance": closing_balance,
            "currency": currency,
            "imported_by": actor,
            **kwargs,
        },
    )
    return statement


@transaction.atomic
def add_bank_statement_line(
    *,
    statement,
    source_identity,
    transaction_date,
    direction,
    amount,
    sequence,
    actor=None,
    **kwargs,
):
    statement = BankStatement.objects.select_for_update().get(pk=statement.pk)
    if direction not in {LiquidityDirection.IN, LiquidityDirection.OUT}:
        raise ValidationError("Statement line direction must be IN or OUT.")
    line, _ = BankStatementLine.objects.get_or_create(
        statement=statement,
        source_identity=source_identity,
        defaults={
            "transaction_date": transaction_date,
            "direction": direction,
            "amount": _whole(amount),
            "sequence": sequence,
            **kwargs,
        },
    )
    return line


@transaction.atomic
def match_bank_statement_line(*, statement_line, liquidity_entry, amount, source_key, actor):
    line = (
        BankStatementLine.objects.select_for_update()
        .select_related("statement__liquidity_account")
        .get(pk=statement_line.pk)
    )
    entry = (
        type(liquidity_entry)
        .objects.select_for_update()
        .select_related("liquidity_account")
        .get(pk=liquidity_entry.pk)
    )
    existing = (
        BankReconciliationMatch.objects.select_for_update().filter(source_key=source_key).first()
    )
    if existing:
        return existing
    if (
        entry.legal_entity_id != line.statement.legal_entity_id
        or entry.liquidity_account_id != line.statement.liquidity_account_id
    ):
        raise ValidationError(
            "Bank reconciliation match must use the same entity and BANK account."
        )
    if entry.currency != line.statement.currency or entry.direction != line.direction:
        raise ValidationError("Bank reconciliation currency and direction must match.")
    amount = _whole(amount)
    line_used = line.matches.filter(state=BankReconciliationMatchState.ACTIVE).aggregate(
        total=Sum("matched_amount")
    )["total"] or Decimal("0")
    entry_used = entry.bank_matches.filter(state=BankReconciliationMatchState.ACTIVE).aggregate(
        total=Sum("matched_amount")
    )["total"] or Decimal("0")
    if line_used + amount > line.amount or entry_used + amount > entry.amount:
        raise ValidationError("Bank reconciliation allocation exceeds available amount.")
    return BankReconciliationMatch.objects.create(
        bank_statement_line=line,
        liquidity_entry=entry,
        matched_amount=amount,
        source_key=source_key,
        matched_by=actor,
    )


@transaction.atomic
def unmatch_bank_statement_line(match, *, actor, reason):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to unmatch bank evidence."})
    match = BankReconciliationMatch.objects.select_for_update().get(pk=match.pk)
    if match.state == BankReconciliationMatchState.REVERSED:
        return match
    match.state = BankReconciliationMatchState.REVERSED
    match.reason = reason
    match.reversed_by = actor
    match.reversed_at = timezone.now()
    match.save(update_fields=("state", "reason", "reversed_by", "reversed_at", "updated_at"))
    return match
