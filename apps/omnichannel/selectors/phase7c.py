"""Read-only Phase 7C Store/channel/SKU source analytics."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from apps.omnichannel.models import (
    OmniAdjustmentSource,
    OmniOrder,
    OmniPayoutSource,
    OmniReturnSource,
    OmniRevenueEvent,
    OmniSettlement,
    PosReturn,
    PosSale,
    PosSaleState,
)
from apps.organizations.selectors import accessible_legal_entities

ZERO = Decimal("0")


def _scope(user):
    return accessible_legal_entities(user)


def pos_sales(user, *, start: date | None = None, end: date | None = None):
    queryset = (
        PosSale.objects.filter(legal_entity__in=_scope(user))
        .select_related("legal_entity", "store", "warehouse", "tender")
        .prefetch_related("lines__item", "lines__warehouse_movement", "finance_sources")
        .order_by("-transaction_at", "-document_number")
    )
    if start:
        queryset = queryset.filter(transaction_date__gte=start)
    if end:
        queryset = queryset.filter(transaction_date__lte=end)
    return queryset


def pos_cash_sessions(user, *, start: date | None = None, end: date | None = None):
    from apps.omnichannel.models import PosCashSession

    queryset = (
        PosCashSession.objects.filter(legal_entity__in=_scope(user))
        .select_related("legal_entity", "store", "opened_by", "closed_by")
        .order_by("-opened_at")
    )
    if start:
        queryset = queryset.filter(opened_at__date__gte=start)
    if end:
        queryset = queryset.filter(opened_at__date__lte=end)
    return queryset


def pos_returns(user, *, start: date | None = None, end: date | None = None):

    queryset = (
        PosReturn.objects.filter(legal_entity__in=_scope(user))
        .select_related("store", "warehouse", "original_sale", "cash_session")
        .prefetch_related("lines__item", "lines__quality_inspection_line")
        .order_by("-return_at", "-document_number")
    )
    if start:
        queryset = queryset.filter(return_date__gte=start)
    if end:
        queryset = queryset.filter(return_date__lte=end)
    return queryset


def _bucket(store, item=None):
    return {
        "store_id": store.pk,
        "store_code": store.code,
        "store_name": store.name,
        "sales_channel": store.channel,
        "item_id": item.pk if item else None,
        "item_code": item.code if item else "",
        "item_name": item.name if item else "",
        "marketplace_order_count": 0,
        "marketplace_ordered_quantity": ZERO,
        "marketplace_internal_quantity": ZERO,
        "marketplace_internal_quantity_known": True,
        "marketplace_completed_revenue": ZERO,
        "marketplace_completed_revenue_known": True,
        "pos_revenue": ZERO,
        "pos_units_sold": ZERO,
        "warehouse_cogs": ZERO,
        "warehouse_cogs_known": True,
        "marketplace_fees": ZERO,
        "marketplace_fees_known": True,
        "refund_amount": ZERO,
        "refund_amount_known": True,
        "adjustment_amount": ZERO,
        "adjustment_amount_known": True,
        "settlement_amount": ZERO,
        "settlement_amount_known": True,
        "payout_amount": ZERO,
        "payout_amount_known": True,
        "return_quantity": ZERO,
        "stock_exception_count": 0,
        "drilldown": defaultdict(list),
    }


def store_channel_sku_analytics(user, *, start: date | None = None, end: date | None = None):
    """Aggregate durable source facts without inventing Finance facts or costs."""

    rows = {}

    def row(store, item=None):
        key = (store.pk, item.pk if item else None)
        if key not in rows:
            rows[key] = _bucket(store, item)
        return rows[key]

    entities = _scope(user)
    orders = OmniOrder.objects.filter(
        legal_entity__in=entities, store__isnull=False
    ).select_related("store")
    if start:
        orders = orders.filter(order_date__gte=start)
    if end:
        orders = orders.filter(order_date__lte=end)
    for order in orders.prefetch_related("lines__item"):
        store_row = row(order.store)
        store_row["marketplace_order_count"] += 1
        store_row["drilldown"]["marketplace_orders"].append(str(order.pk))
        for line in order.lines.all():
            if line.item_id is None:
                store_row["stock_exception_count"] += 1
                continue
            item_row = row(order.store, line.item)
            for target in (store_row, item_row):
                target["marketplace_ordered_quantity"] += line.marketplace_quantity
                if line.internal_quantity is None:
                    target["marketplace_internal_quantity_known"] = False
                else:
                    target["marketplace_internal_quantity"] += line.internal_quantity
                target["drilldown"]["marketplace_order_lines"].append(str(line.pk))

    events = OmniRevenueEvent.objects.filter(legal_entity__in=entities).select_related(
        "store", "order"
    )
    if start:
        events = events.filter(completion_date__gte=start)
    if end:
        events = events.filter(completion_date__lte=end)
    for event in events.prefetch_related("order__lines__item"):
        store_row = row(event.store)
        if event.gross_eligible_amount is None:
            store_row["marketplace_completed_revenue_known"] = False
        else:
            store_row["marketplace_completed_revenue"] += event.gross_eligible_amount
        store_row["drilldown"]["revenue_events"].append(str(event.pk))
        for line in event.order.lines.all():
            if line.item_id is None:
                continue
            item_row = row(event.store, line.item)
            if line.source_subtotal is None:
                item_row["marketplace_completed_revenue_known"] = False
            else:
                item_row["marketplace_completed_revenue"] += line.source_subtotal
            item_row["drilldown"]["revenue_events"].append(str(event.pk))

    settlements = OmniSettlement.objects.filter(
        legal_entity__in=entities, store__isnull=False
    ).select_related("store")
    if start:
        settlements = settlements.filter(settlement_date__gte=start)
    if end:
        settlements = settlements.filter(settlement_date__lte=end)
    for settlement in settlements:
        store_row = row(settlement.store)
        if settlement.net_amount is None:
            store_row["settlement_amount_known"] = False
        else:
            store_row["settlement_amount"] += settlement.net_amount
        if settlement.fee_amount is None:
            store_row["marketplace_fees_known"] = False
        else:
            store_row["marketplace_fees"] += settlement.fee_amount
        store_row["drilldown"]["settlements"].append(str(settlement.pk))

    adjustments = OmniAdjustmentSource.objects.filter(
        legal_entity__in=entities, store__isnull=False
    ).select_related("store")
    if start:
        adjustments = adjustments.filter(transaction_date__gte=start)
    if end:
        adjustments = adjustments.filter(transaction_date__lte=end)
    for adjustment in adjustments:
        store_row = row(adjustment.store)
        if adjustment.amount is None:
            store_row["adjustment_amount_known"] = False
        else:
            store_row["adjustment_amount"] += adjustment.amount
        store_row["drilldown"]["adjustments"].append(str(adjustment.pk))

    payouts = OmniPayoutSource.objects.filter(
        legal_entity__in=entities, store__isnull=False
    ).select_related("store")
    if start:
        payouts = payouts.filter(payout_date__gte=start)
    if end:
        payouts = payouts.filter(payout_date__lte=end)
    for payout in payouts:
        store_row = row(payout.store)
        if payout.amount is None:
            store_row["payout_amount_known"] = False
        else:
            store_row["payout_amount"] += payout.amount
        store_row["drilldown"]["payouts"].append(str(payout.pk))

    marketplace_returns = OmniReturnSource.objects.filter(
        legal_entity__in=entities, store__isnull=False
    ).select_related("store", "resolved_item")
    if start:
        marketplace_returns = marketplace_returns.filter(arrived_at__date__gte=start)
    if end:
        marketplace_returns = marketplace_returns.filter(arrived_at__date__lte=end)
    for source in marketplace_returns:
        store_row = row(source.store)
        store_row["return_quantity"] += source.quantity
        if source.refund_amount is None:
            store_row["refund_amount_known"] = False
        else:
            store_row["refund_amount"] += source.refund_amount
        store_row["drilldown"]["marketplace_returns"].append(str(source.pk))
        if source.resolved_item_id:
            item_row = row(source.store, source.resolved_item)
            item_row["return_quantity"] += source.quantity
            item_row["drilldown"]["marketplace_returns"].append(str(source.pk))

    for sale in pos_sales(user, start=start, end=end).filter(state=PosSaleState.POSTED):
        store_row = row(sale.store)
        store_row["pos_revenue"] += sale.grand_total_amount
        store_row["drilldown"]["pos_sales"].append(str(sale.pk))
        for line in sale.lines.all():
            item_row = row(sale.store, line.item)
            for target in (store_row, item_row):
                target["pos_units_sold"] += line.quantity
                if line.cogs_amount is None:
                    target["warehouse_cogs_known"] = False
                else:
                    target["warehouse_cogs"] += line.cogs_amount
                target["drilldown"]["pos_sale_lines"].append(str(line.pk))
            item_row["pos_revenue"] += line.line_amount

    for pos_return in pos_returns(user, start=start, end=end).filter(state="RECORDED"):
        store_row = row(pos_return.store)
        if pos_return.refund_amount is None:
            store_row["refund_amount_known"] = False
        else:
            store_row["refund_amount"] += pos_return.refunded_amount
        store_row["drilldown"]["pos_returns"].append(str(pos_return.pk))
        for line in pos_return.lines.all():
            item_row = row(pos_return.store, line.item)
            for target in (store_row, item_row):
                target["return_quantity"] += line.quantity
                target["drilldown"]["pos_return_lines"].append(str(line.pk))

    output = []
    for values in rows.values():
        revenue_known = values["marketplace_completed_revenue_known"]
        cogs_known = values["warehouse_cogs_known"]
        fees_known = values["marketplace_fees_known"]
        values["marketplace_internal_quantity"] = (
            values["marketplace_internal_quantity"]
            if values.pop("marketplace_internal_quantity_known")
            else None
        )
        values["marketplace_completed_revenue"] = (
            values["marketplace_completed_revenue"] if revenue_known else None
        )
        values["warehouse_cogs"] = values["warehouse_cogs"] if cogs_known else None
        values["marketplace_fees"] = values["marketplace_fees"] if fees_known else None
        values["refund_amount"] = (
            values["refund_amount"] if values.pop("refund_amount_known") else None
        )
        values["adjustment_amount"] = (
            values["adjustment_amount"] if values.pop("adjustment_amount_known") else None
        )
        values["settlement_amount"] = (
            values["settlement_amount"] if values.pop("settlement_amount_known") else None
        )
        values["payout_amount"] = (
            values["payout_amount"] if values.pop("payout_amount_known") else None
        )
        revenue = (
            values["marketplace_completed_revenue"] + values["pos_revenue"]
            if values["marketplace_completed_revenue"] is not None
            else None
        )
        values["revenue_source"] = revenue
        values["gross_profit_source"] = (
            revenue - values["warehouse_cogs"] - values["marketplace_fees"]
            if revenue is not None
            and values["warehouse_cogs"] is not None
            and values["marketplace_fees"] is not None
            else None
        )
        values["drilldown"] = {
            key: tuple(source_ids) for key, source_ids in values["drilldown"].items()
        }
        output.append(values)
    return tuple(sorted(output, key=lambda value: (value["store_code"], value["item_code"])))


def phase7_channel_reconciliation(user, *, start: date | None = None, end: date | None = None):
    """Combined read model without pretending marketplace and POS have identical lifecycles."""

    return {
        "rows": store_channel_sku_analytics(user, start=start, end=end),
        "marketplace_lifecycle": "order -> completion -> settlement -> payout",
        "pos_lifecycle": "sale -> tender -> cash session/payment handoff",
        "returns_note": "Returns are separate follow-up sources and do not erase revenue history.",
    }
