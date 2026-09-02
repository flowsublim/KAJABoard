"""Read-only Finance liquidity and payment selectors."""

from decimal import Decimal

from apps.finance.models import LiquidityAccountType, LiquidityDirection, LiquidityEntry, Payment


def payments(*, legal_entity, start=None, end=None, liquidity_account=None, direction=None):
    queryset = (
        Payment.objects.filter(legal_entity=legal_entity)
        .select_related("liquidity_account", "partner", "store", "journal", "liquidity_entry")
        .prefetch_related("allocations__receivable", "allocations__payable")
    )
    if start:
        queryset = queryset.filter(payment_date__gte=start)
    if end:
        queryset = queryset.filter(payment_date__lte=end)
    if liquidity_account:
        queryset = queryset.filter(liquidity_account=liquidity_account)
    if direction:
        queryset = queryset.filter(direction=direction)
    return queryset.order_by("payment_date", "payment_number")


def _ledger(*, legal_entity, account_type, liquidity_account=None, start=None, end=None):
    queryset = LiquidityEntry.objects.filter(
        legal_entity=legal_entity, liquidity_account__account_type=account_type
    ).select_related("liquidity_account", "journal")
    if liquidity_account:
        queryset = queryset.filter(liquidity_account=liquidity_account)
    if start:
        queryset = queryset.filter(transaction_date__gte=start)
    if end:
        queryset = queryset.filter(transaction_date__lte=end)
    return queryset.order_by("transaction_date", "posted_at")


def cash_ledger(**kwargs):
    return _ledger(account_type=LiquidityAccountType.CASH, **kwargs)


def bank_ledger(**kwargs):
    return _ledger(account_type=LiquidityAccountType.BANK, **kwargs)


def liquidity_balance(*, legal_entity, liquidity_account, end=None):
    entries = _ledger(
        legal_entity=legal_entity,
        account_type=liquidity_account.account_type,
        liquidity_account=liquidity_account,
        end=end,
    )
    return sum(
        (
            entry.amount if entry.direction == LiquidityDirection.IN else -entry.amount
            for entry in entries
        ),
        Decimal("0"),
    )
