"""Read-only marketplace balance and settlement accounting selectors."""

from decimal import Decimal

from apps.finance.models import (
    MarketplaceAdjustmentPosting,
    MarketplaceBalanceDirection,
    MarketplaceBalanceEntry,
    MarketplacePayoutPosting,
    MarketplaceReturnPosting,
    MarketplaceSettlementPosting,
)


def marketplace_balance_entries(
    *,
    legal_entity,
    store=None,
    date=None,
    start=None,
    end=None,
    source_key=None,
    source_document_id=None,
    journal=None,
    direction=None,
):
    queryset = MarketplaceBalanceEntry.objects.filter(legal_entity=legal_entity).select_related(
        "store", "journal", "reversal_of"
    )
    if store:
        queryset = queryset.filter(store=store)
    if date:
        queryset = queryset.filter(transaction_date=date)
    if start:
        queryset = queryset.filter(transaction_date__gte=start)
    if end:
        queryset = queryset.filter(transaction_date__lte=end)
    if source_key:
        queryset = queryset.filter(source_key=source_key)
    if source_document_id:
        queryset = queryset.filter(source_document_id=str(source_document_id))
    if journal:
        queryset = queryset.filter(journal=journal)
    if direction:
        queryset = queryset.filter(direction=direction)
    return queryset.order_by("transaction_date", "posted_at", "pk")


def marketplace_balance(*, legal_entity, store=None, date=None, end=None, **filters):
    entries = marketplace_balance_entries(
        legal_entity=legal_entity,
        store=store,
        date=date,
        end=end,
        **filters,
    )
    return sum(
        (
            entry.amount if entry.direction == MarketplaceBalanceDirection.IN else -entry.amount
            for entry in entries
        ),
        Decimal("0"),
    )


def marketplace_settlements(
    *,
    legal_entity,
    store=None,
    start=None,
    end=None,
    state=None,
    source_settlement_identity=None,
    journal=None,
):
    queryset = MarketplaceSettlementPosting.objects.filter(
        legal_entity=legal_entity
    ).select_related(
        "store",
        "journal",
        "receivable",
        "receivable__journal",
        "marketplace_balance_entry",
        "reversal_of",
    )
    if store:
        queryset = queryset.filter(store=store)
    if start:
        queryset = queryset.filter(settlement_date__gte=start)
    if end:
        queryset = queryset.filter(settlement_date__lte=end)
    if state:
        queryset = queryset.filter(state=state)
    if source_settlement_identity:
        queryset = queryset.filter(source_settlement_identity=source_settlement_identity)
    if journal:
        queryset = queryset.filter(journal=journal)
    return queryset.order_by("settlement_date", "posted_at", "pk")


def marketplace_returns(
    *, legal_entity, store=None, start=None, end=None, treatment=None, state=None
):
    queryset = MarketplaceReturnPosting.objects.filter(legal_entity=legal_entity).select_related(
        "store",
        "journal",
        "receivable",
        "revenue_journal",
        "marketplace_balance_entry",
        "reversal_of",
    )
    if store:
        queryset = queryset.filter(store=store)
    if start:
        queryset = queryset.filter(transaction_date__gte=start)
    if end:
        queryset = queryset.filter(transaction_date__lte=end)
    if treatment:
        queryset = queryset.filter(treatment=treatment)
    if state:
        queryset = queryset.filter(state=state)
    return queryset.order_by("transaction_date", "posted_at", "pk")


def marketplace_adjustments(*, legal_entity, store=None, start=None, end=None, state=None):
    queryset = MarketplaceAdjustmentPosting.objects.filter(
        legal_entity=legal_entity
    ).select_related("store", "settlement_posting", "journal", "reversal_of")
    if store:
        queryset = queryset.filter(store=store)
    if start:
        queryset = queryset.filter(transaction_date__gte=start)
    if end:
        queryset = queryset.filter(transaction_date__lte=end)
    if state:
        queryset = queryset.filter(state=state)
    return queryset.order_by("transaction_date", "posted_at", "pk")


def marketplace_payouts(*, legal_entity, store=None, start=None, end=None, state=None):
    queryset = MarketplacePayoutPosting.objects.filter(legal_entity=legal_entity).select_related(
        "store",
        "liquidity_account",
        "journal",
        "marketplace_balance_entry",
        "liquidity_entry",
        "reversal_of",
    )
    if store:
        queryset = queryset.filter(store=store)
    if start:
        queryset = queryset.filter(payout_date__gte=start)
    if end:
        queryset = queryset.filter(payout_date__lte=end)
    if state:
        queryset = queryset.filter(state=state)
    return queryset.order_by("payout_date", "posted_at", "pk")
