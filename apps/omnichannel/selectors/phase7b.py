from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q

from apps.omnichannel.models import (
    OmniAdjustmentSource,
    OmniPayoutSource,
    OmniReconciliationStatus,
    OmniReturnSource,
    OmniRevenueEvent,
    OmniRevenueState,
    OmniSettlement,
)
from apps.organizations.selectors import accessible_legal_entities


def _scope(user):
    return accessible_legal_entities(user)


def revenue_events(user, *, start: date | None = None, end: date | None = None):
    queryset = (
        OmniRevenueEvent.objects.filter(legal_entity__in=_scope(user))
        .select_related("legal_entity", "store", "order")
        .order_by("-completion_date", "external_order_number")
    )
    if start:
        queryset = queryset.filter(completion_date__gte=start)
    if end:
        queryset = queryset.filter(completion_date__lte=end)
    return queryset


def settlement_sources(user, *, start: date | None = None, end: date | None = None):
    queryset = (
        OmniSettlement.objects.filter(legal_entity__in=_scope(user))
        .select_related("legal_entity", "store", "matched_revenue", "batch")
        .prefetch_related("fees")
        .order_by("-settlement_date", "external_order_number")
    )
    if start:
        queryset = queryset.filter(settlement_date__gte=start)
    if end:
        queryset = queryset.filter(settlement_date__lte=end)
    return queryset


def return_sources(user, *, start: date | None = None, end: date | None = None):
    queryset = (
        OmniReturnSource.objects.filter(legal_entity__in=_scope(user))
        .select_related(
            "legal_entity", "store", "original_order", "original_order_line", "resolved_item"
        )
        .order_by("-arrived_at", "external_order_number", "source_row_key")
    )
    if start:
        queryset = queryset.filter(Q(arrived_at__date__gte=start) | Q(order_date__date__gte=start))
    if end:
        queryset = queryset.filter(Q(arrived_at__date__lte=end) | Q(order_date__date__lte=end))
    return queryset


def adjustment_sources(user, *, start: date | None = None, end: date | None = None):
    queryset = (
        OmniAdjustmentSource.objects.filter(legal_entity__in=_scope(user))
        .select_related("legal_entity", "store", "settlement")
        .order_by("-transaction_date", "source_row_key")
    )
    if start:
        queryset = queryset.filter(transaction_date__gte=start)
    if end:
        queryset = queryset.filter(transaction_date__lte=end)
    return queryset


def payout_sources(user, *, start: date | None = None, end: date | None = None):
    queryset = (
        OmniPayoutSource.objects.filter(legal_entity__in=_scope(user))
        .select_related("legal_entity", "store")
        .order_by("-payout_date", "payout_reference")
    )
    if start:
        queryset = queryset.filter(payout_date__gte=start)
    if end:
        queryset = queryset.filter(payout_date__lte=end)
    return queryset


def revenue_settlement_state(event):
    if event.state != OmniRevenueState.ELIGIBLE:
        return OmniReconciliationStatus.BLOCKED_MAPPING
    settlements = list(event.settlements.filter(net_amount__isnull=False))
    if not settlements:
        return OmniReconciliationStatus.COMPLETED_NOT_SETTLED
    if event.gross_eligible_amount is None:
        return OmniReconciliationStatus.SETTLEMENT_PARTIAL
    settled = sum((settlement.net_amount for settlement in settlements), Decimal("0"))
    if settled > event.gross_eligible_amount:
        return OmniReconciliationStatus.SETTLEMENT_OVER
    if settled < event.gross_eligible_amount:
        return OmniReconciliationStatus.SETTLEMENT_PARTIAL
    return OmniReconciliationStatus.SETTLEMENT_MATCH


def reconciliation_summary(user, *, start: date | None = None, end: date | None = None):
    """Read-only source reconciliation; no Finance or Warehouse balances are inferred."""

    groups = defaultdict(
        lambda: {
            "completed_revenue": Decimal("0"),
            "completed_revenue_known": True,
            "settled_amount": Decimal("0"),
            "settled_amount_known": True,
            "marketplace_fees": Decimal("0"),
            "returns_quantity": Decimal("0"),
            "refund_amount": Decimal("0"),
            "refund_amount_known": True,
            "adjustments": Decimal("0"),
            "adjustments_known": True,
            "payout_amount": Decimal("0"),
            "payout_amount_known": True,
            "events": [],
            "exceptions": [],
        }
    )
    for event in revenue_events(user, start=start, end=end):
        key = event.store_id
        row = groups[key]
        if event.gross_eligible_amount is None:
            row["completed_revenue_known"] = False
        else:
            row["completed_revenue"] += event.gross_eligible_amount
        settlements = list(event.settlements.all())
        for settlement in settlements:
            if settlement.net_amount is None:
                row["settled_amount_known"] = False
            else:
                row["settled_amount"] += settlement.net_amount
            if settlement.fee_amount is not None:
                row["marketplace_fees"] += settlement.fee_amount
        state = revenue_settlement_state(event)
        row["events"].append(event)
        if state != OmniReconciliationStatus.SETTLEMENT_MATCH:
            row["exceptions"].append(state)
    for settlement in settlement_sources(user, start=start, end=end):
        if settlement.store_id not in groups:
            groups[settlement.store_id]
        if settlement.fee_amount is not None:
            groups[settlement.store_id]["marketplace_fees"] += settlement.fee_amount
        if settlement.matched_revenue_id is None:
            groups[settlement.store_id]["exceptions"].append(
                OmniReconciliationStatus.SETTLEMENT_UNMATCHED
            )
    for source in return_sources(user, start=start, end=end):
        row = groups[source.store_id]
        row["returns_quantity"] += source.quantity
        if source.refund_amount is None:
            row["refund_amount_known"] = False
        else:
            row["refund_amount"] += source.refund_amount
        if source.linkage_status != "MATCHED":
            row["exceptions"].append(source.linkage_status)
    for adjustment in adjustment_sources(user, start=start, end=end):
        row = groups[adjustment.store_id]
        if adjustment.amount is None:
            row["adjustments_known"] = False
        else:
            row["adjustments"] += adjustment.amount
    for payout in payout_sources(user, start=start, end=end):
        row = groups[payout.store_id]
        if payout.amount is None:
            row["payout_amount_known"] = False
        else:
            row["payout_amount"] += payout.amount
        if payout.reconciliation_status != OmniReconciliationStatus.PAYOUT_MATCH:
            row["exceptions"].append(payout.reconciliation_status)
    output = []
    for store_id, values in groups.items():
        revenue = values.pop("completed_revenue") if values.pop("completed_revenue_known") else None
        settled = values.pop("settled_amount") if values.pop("settled_amount_known") else None
        refunds = values.pop("refund_amount") if values.pop("refund_amount_known") else None
        adjustments = values.pop("adjustments") if values.pop("adjustments_known") else None
        payout = values.pop("payout_amount") if values.pop("payout_amount_known") else None
        values["unsettled_amount"] = (
            revenue - settled if revenue is not None and settled is not None else None
        )
        values["unpaid_marketplace_balance"] = (
            (settled - payout) if settled is not None and payout is not None else None
        )
        values["completed_revenue"] = revenue
        values["settled_amount"] = settled
        values["refund_amount"] = refunds
        values["adjustments"] = adjustments
        values["payout_amount"] = payout
        values["exceptions"] = tuple(dict.fromkeys(values["exceptions"]))
        output.append({"store_id": store_id, **values})
    return tuple(sorted(output, key=lambda row: str(row["store_id"] or "")))


def reconciliation_dashboard(user, *, start: date | None = None, end: date | None = None):
    rows = reconciliation_summary(user, start=start, end=end)
    cards = defaultdict(int)
    for row in rows:
        for exception in row["exceptions"]:
            cards[exception] += 1
    return {"rows": rows, "exception_cards": dict(cards)}
