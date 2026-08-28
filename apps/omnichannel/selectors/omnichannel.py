from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.omnichannel.models import (
    OmniException,
    OmniExceptionState,
    OmniImportBatch,
    OmniMappingStatus,
    OmniOperationalStatus,
    OmniOrder,
    OmniOrderLine,
    OmniPacking,
    OmniPackingState,
)
from apps.organizations.selectors import accessible_legal_entities
from apps.warehouse.models import InventoryValuationState, ValuationStatus


def import_batches(user):
    return (
        OmniImportBatch.objects.filter(legal_entity__in=accessible_legal_entities(user))
        .select_related("legal_entity", "imported_by")
        .order_by("-created_at")
    )


def omni_orders(user, *, search="", normalized_status=""):
    qs = (
        OmniOrder.objects.filter(legal_entity__in=accessible_legal_entities(user))
        .select_related("legal_entity", "store", "source_batch")
        .prefetch_related("lines", "lines__item")
    )
    if search:
        qs = qs.filter(
            Q(external_order_number__icontains=search) | Q(external_store_name__icontains=search)
        )
    if normalized_status:
        qs = qs.filter(normalized_status=normalized_status)
    return qs.order_by("-order_date", "external_order_number")


def warehouse_demand(user, *, warehouse=None):
    qs = (
        OmniOrderLine.objects.filter(
            order__legal_entity__in=accessible_legal_entities(user),
            item__isnull=False,
            mapping_status=OmniMappingStatus.READY,
            source_sync_status=OmniMappingStatus.READY,
        )
        .exclude(
            order__normalized_status__in=[
                OmniOperationalStatus.CANCELLED,
                OmniOperationalStatus.RETURNED,
                OmniOperationalStatus.REFUNDED,
            ]
        )
        .annotate(
            packed=Coalesce(
                Sum(
                    "packing_lines__packed_quantity",
                    filter=Q(
                        packing_lines__packing__state=OmniPackingState.POSTED,
                        packing_lines__warehouse_movement__isnull=False,
                    ),
                ),
                Value(Decimal("0"), output_field=DecimalField(max_digits=18, decimal_places=6)),
            )
        )
        .select_related("order", "order__store", "item", "item__uom")
    )
    lines = list(qs.order_by("order__order_date", "order__external_order_number", "id"))
    states = {}
    if warehouse:
        states = {
            state.item_id: state
            for state in InventoryValuationState.objects.filter(
                legal_entity__in=accessible_legal_entities(user),
                warehouse=warehouse,
                item_id__in={line.item_id for line in lines},
            )
        }
    output = []
    for line in lines:
        packed = line.packed or Decimal("0")
        remaining = line.internal_quantity - packed
        if remaining <= 0:
            continue
        state = None
        available = None
        valuation_status = ValuationStatus.READY
        if warehouse is not None:
            state = states.get(line.item_id)
            available = state.quantity_on_hand if state else Decimal("0")
            valuation_status = (
                state.valuation_status if state else ValuationStatus.PENDING_VALUATION
            )
        shortage = max(remaining - available, Decimal("0")) if available is not None else None
        output.append(
            {
                "order": line.order,
                "order_line": line,
                "item": line.item,
                "store": line.order.store,
                "required_quantity": line.internal_quantity,
                "packed_quantity": packed,
                "remaining_quantity": remaining,
                "available_quantity": available,
                "shortage_quantity": shortage,
                "valuation_status": valuation_status,
                "eligible": not shortage and valuation_status == ValuationStatus.READY
                if available is not None
                else True,
            }
        )
    return tuple(output)


def packing_documents(user):
    return (
        OmniPacking.objects.filter(legal_entity__in=accessible_legal_entities(user))
        .select_related("store", "warehouse", "created_by", "posted_by")
        .prefetch_related("lines", "lines__item")
        .order_by("-packing_date", "-created_at")
    )


def omni_exceptions(user):
    return (
        OmniException.objects.filter(
            legal_entity__in=accessible_legal_entities(user), state=OmniExceptionState.OPEN
        )
        .select_related("batch", "order", "line")
        .order_by("-created_at")
    )


def operational_summary(user):
    orders = omni_orders(user)
    today = orders.filter(
        order_date__gte=__import__("django.utils.timezone", fromlist=["localdate"]).localdate()
    ).count()
    return {
        "orders": orders.count(),
        "orders_today": today,
        "pending_demand": sum(1 for row in warehouse_demand(user) if row["remaining_quantity"] > 0),
        "unmapped_store": OmniImportBatch.objects.filter(
            legal_entity__in=accessible_legal_entities(user),
            rows__mapping_status=OmniMappingStatus.UNMAPPED_STORE,
        )
        .distinct()
        .count(),
        "unmapped_sku": OmniImportBatch.objects.filter(
            legal_entity__in=accessible_legal_entities(user),
            rows__mapping_status__in=[
                OmniMappingStatus.UNMAPPED_SKU,
                OmniMappingStatus.MAPPING_INACTIVE,
            ],
        )
        .distinct()
        .count(),
        "packing_pending": packing_documents(user).filter(state=OmniPackingState.DRAFT).count(),
        "exceptions": omni_exceptions(user).count(),
    }


def order_daily_store_summary(user):
    """Read-only operational summary keyed exclusively by Order Date."""
    grouped = defaultdict(
        lambda: {
            "order_count": 0,
            "line_count": 0,
            "marketplace_quantity": Decimal("0"),
            "internal_quantity": Decimal("0"),
        }
    )
    for order in omni_orders(user):
        if not order.order_date:
            continue
        key = (
            order.order_date,
            order.store_id,
            order.store_code_snapshot or order.external_store_name,
        )
        grouped[key]["order_count"] += 1
        for line in order.lines.all():
            grouped[key]["line_count"] += 1
            grouped[key]["marketplace_quantity"] += line.marketplace_quantity
            if line.internal_quantity is not None:
                grouped[key]["internal_quantity"] += line.internal_quantity
    return tuple(
        {"order_date": key[0], "store_id": key[1], "store": key[2], **values}
        for key, values in sorted(grouped.items(), key=lambda entry: (entry[0][0], entry[0][2]))
    )
