"""Phase 7B source services.

These services deliberately stop at source events and handoff candidates. They
do not post Finance journals, AR, cash, bank, or Warehouse movements.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.channels.models import Store
from apps.channels.selectors.channels import normalize_external_key
from apps.core.services.audit import record_audit_event
from apps.finance.models import DCDirection
from apps.finance.services import FinanceMappingError, resolve_account_mapping
from apps.omnichannel.models import (
    OmniAdjustmentSource,
    OmniOrder,
    OmniPayoutSource,
    OmniReconciliationStatus,
    OmniReturnImportBatch,
    OmniReturnLinkageStatus,
    OmniReturnSource,
    OmniRevenueEvent,
    OmniRevenueState,
    OmniSettlement,
    OmniSettlementFee,
    OmniSettlementImportBatch,
)
from apps.omnichannel.services.imports import (
    _date,
    _decimal,
    _read_csv,
    _read_xlsx,
    _text,
)

REVENUE_EVENT_CODE = "OMNI_ORDER_COMPLETED"
SETTLEMENT_EVENT_CODE = "OMNI_SETTLEMENT"
RETURN_EVENT_CODE = "OMNI_RETURN"
ADJUSTMENT_EVENT_CODE = "OMNI_ADJUSTMENT"
PAYOUT_EVENT_CODE = "OMNI_PAYOUT"

SETTLEMENT_ALIASES = {
    "store": ("Toko", "Toko BigSeller", "Store", "Store Name"),
    "marketplace": ("Marketplace", "Platform", "Channel"),
    "order": ("No Pesanan", "Nomor Pesanan", "Order Number", "Order No"),
    "reference": (
        "Settlement Reference",
        "Settlement ID",
        "Nomor Settlement",
        "No Settlement",
        "ID Settlement",
        "Settlement Ref",
    ),
    "date": ("Tgl Pencairan", "Settlement Date", "Tanggal Settlement"),
    "gross": ("Gross Settlement", "Gross Amount", "Pendapatan Kotor"),
    "net": ("Pendapatan Bersih", "Settled Amount", "Net Amount", "Net Settlement"),
    "currency": ("Currency", "Mata Uang"),
    "admin": ("Biaya Admin", "Admin Fee"),
    "service": ("Biaya Layanan", "Service Fee", "Platform Fee"),
    "affiliate": ("Komisi Affiliate", "Affiliate Fee"),
    "shipping": ("Ongkir Penjual", "Seller Shipping Fee"),
    "refund": ("Refund", "Refund Deduction", "Pengembalian Dana"),
    "adjustment": ("Adjustment", "Marketplace Adjustment", "Penyesuaian"),
}

RETURN_ALIASES = {
    "marketplace": ("Marketplace", "Platform", "Channel"),
    "store": ("Toko BigSeller", "Toko", "Store", "Store Name"),
    "package": ("Nomor Paket", "Package Number", "Package"),
    "order": ("Nomor Pesanan", "No Pesanan", "Order Number", "Order No"),
    "return_id": ("ID Purna Jual", "Return ID", "After-sales ID"),
    "sku": ("SKU Toko", "SKU", "Marketplace SKU"),
    "warehouse_sku": ("SKU Gudang", "Warehouse SKU"),
    "quantity": ("Jumlah", "Qty", "Quantity"),
    "stock_quantity": ("Jumlah Penambahan Stok", "Stock Addition Quantity"),
    "stock_status": ("Status Penambahan Stok",),
    "order_status": ("Status Pesanan",),
    "shipping_status": ("Status Pengiriman Jasa Kirim",),
    "aftersales_status": ("Status Purna Jual",),
    "return_status": ("Status Pengembalian",),
    "return_type": ("Jenis Purna Jual",),
    "reason": ("Alasan Retur", "Return Reason"),
    "currency": ("Mata Uang", "Currency"),
    "refund": ("Dana Pengembalian", "Refund Amount"),
    "order_date": ("Waktu Pemesanan", "Order Date"),
    "requested_at": ("Waktu Permintaan Purna Jual", "Return Requested At"),
    "deadline": ("Batas Waktu", "Deadline"),
    "shipped_at": ("Waktu Dikirim", "Shipped At"),
    "arrived_at": ("Waktu Sampai Gudang", "Arrived At", "Return Arrival"),
    "stock_added_at": ("Waktu Penambahan Stok", "Stock Added At"),
}


def _value(row, aliases):
    wanted = {normalize_external_key(alias) for alias in aliases}
    for key, value in row.items():
        if normalize_external_key(key) in wanted:
            return value
    return ""


def _payload_rows(payload, source_filename):
    if isinstance(payload, (list, tuple)):
        return [dict(row) for row in payload]
    if not isinstance(payload, bytes):
        raise ValidationError("Source payload must be bytes or row dictionaries.")
    suffix = source_filename.lower().rsplit(".", 1)[-1] if "." in source_filename else ""
    if suffix == "xlsx":
        return _read_xlsx(payload)
    if suffix == "csv":
        return _read_csv(payload)
    raise ValidationError("Phase 7B source supports XLSX and CSV files.")


def _payload_hash(payload, rows):
    if isinstance(payload, bytes):
        return hashlib.sha256(payload).hexdigest()
    return hashlib.sha256(
        repr(sorted(tuple(sorted(row.items())) for row in rows)).encode()
    ).hexdigest()


def _json_safe(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "pk"):
        return str(value.pk)
    return value


def _source_datetime(value, field):
    if value is None or str(value).strip() == "":
        return None
    parsed_date = _date(value, field=field)
    if parsed_date is None:
        return None
    match = re.search(r"(\d{1,2}):(\d{2})", str(value))
    parsed_time = time(int(match.group(1)), int(match.group(2))) if match else time.min
    return timezone.make_aware(datetime.combine(parsed_date, parsed_time))


def _resolve_store(legal_entity, raw_name, marketplace="", business_date=None):
    raw_key = normalize_external_key(raw_name)
    if not raw_key:
        return None, "Store is blank."
    business_date = business_date or timezone.localdate()
    queryset = (
        Store.objects.filter(legal_entity=legal_entity, is_active=True)
        .filter(Q(effective_from__isnull=True) | Q(effective_from__lte=business_date))
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=business_date))
    )
    marketplace_key = normalize_external_key(marketplace)
    matches = []
    for store in queryset:
        identifiers = {
            normalize_external_key(store.code),
            normalize_external_key(store.name),
            normalize_external_key(store.external_account_id),
            *(normalize_external_key(value) for value in store.external_aliases or []),
        }
        if raw_key in identifiers and (
            not marketplace_key or normalize_external_key(store.channel) == marketplace_key
        ):
            matches.append(store)
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        return None, "Store identity is ambiguous."
    return None, "Store is not mapped for the source date."


def _audit(obj, action, actor=None, *, key="", metadata=None):
    record_audit_event(
        action=action,
        target_type=obj._meta.label_lower,
        target_id=obj.pk,
        actor=actor,
        source="omnichannel.phase7b",
        idempotency_key=key,
        metadata=metadata or {},
    )


def _finance_mapping_status(store, business_date):
    """Check Phase 2C mapping readiness without selecting or creating an account."""

    if not store or not (store.finance_dimension or store.revenue_mapping_key):
        return OmniReconciliationStatus.BLOCKED_MAPPING
    context = {"STORE": store.finance_dimension or store.revenue_mapping_key}
    try:
        resolve_account_mapping(
            legal_entity=store.legal_entity,
            module_code="OMNI",
            event_code=REVENUE_EVENT_CODE,
            line_role="RECEIVABLE",
            dc=DCDirection.DEBIT,
            business_date=business_date,
            context=context,
        )
        resolve_account_mapping(
            legal_entity=store.legal_entity,
            module_code="OMNI",
            event_code=REVENUE_EVENT_CODE,
            line_role="REVENUE",
            dc=DCDirection.CREDIT,
            business_date=business_date,
            context=context,
        )
    except FinanceMappingError:
        return OmniReconciliationStatus.BLOCKED_MAPPING
    return OmniReconciliationStatus.READY


@transaction.atomic
def create_revenue_event(order, *, actor=None):
    """Create one immutable order-level event from a completed order."""

    order = (
        OmniOrder.objects.select_for_update()
        .select_related("legal_entity", "store")
        .get(pk=order.pk)
    )
    if (
        order.normalized_status != "COMPLETED"
        or order.completion_date is None
        or order.store_id is None
    ):
        return None
    event_key = f"OMNI_REV|{order.store_id}|{order.external_order_number}"
    existing = OmniRevenueEvent.objects.filter(event_key=event_key).first()
    if existing:
        return existing
    lines = list(order.lines.order_by("id"))
    components = []
    missing_amount = False
    gross = Decimal("0")
    for line in lines:
        amount = line.source_subtotal
        if amount is None:
            missing_amount = True
        else:
            gross += amount
        components.append(
            {
                "line_id": str(line.pk),
                "external_sku": line.external_sku,
                "variation": line.variation,
                "marketplace_quantity": str(line.marketplace_quantity),
                "subtotal": str(amount) if amount is not None else None,
            }
        )
    event = OmniRevenueEvent.objects.create(
        legal_entity=order.legal_entity,
        store=order.store,
        marketplace=order.marketplace or order.store.channel,
        order=order,
        external_order_number=order.external_order_number,
        completion_date=order.completion_date,
        currency="IDR",
        gross_eligible_amount=None if missing_amount else gross,
        source_components={"line_components": components, "amount_available": not missing_amount},
        source_lineage={
            "order_id": str(order.pk),
            "source_batch_id": str(order.source_batch_id) if order.source_batch_id else None,
            "source_hash": order.last_source_hash,
        },
        state=OmniRevenueState.BLOCKED_AMOUNT if missing_amount else OmniRevenueState.ELIGIBLE,
        mapping_status=_finance_mapping_status(order.store, order.completion_date),
        event_key=event_key,
        created_by=actor,
    )
    _audit(event, "omnichannel.revenue_event.created", actor)
    return event


def revenue_finance_candidate(event):
    event = OmniRevenueEvent.objects.select_related("legal_entity", "store", "order").get(
        pk=event.pk
    )
    return {
        "event_code": REVENUE_EVENT_CODE,
        "event_id": str(event.pk),
        "event_key": event.event_key,
        "legal_entity_id": str(event.legal_entity_id),
        "store_id": str(event.store_id),
        "store_dimension": event.store.finance_dimension or event.store.revenue_mapping_key,
        "marketplace": event.marketplace,
        "order_id": str(event.order_id),
        "external_order_number": event.external_order_number,
        "completion_date": event.completion_date,
        "currency": event.currency,
        "gross_revenue": event.gross_eligible_amount,
        "amount_components": event.source_components,
        "mapping_status": event.mapping_status,
        "mapping_context": {
            "STORE": event.store.finance_dimension or event.store.revenue_mapping_key
        },
        "mapping_keys": {
            "module_code": "OMNI",
            "event_code": REVENUE_EVENT_CODE,
            "line_roles": ("RECEIVABLE", "REVENUE"),
        },
        "source_lineage": event.source_lineage,
    }


def _settlement_values(row):
    fees = {}
    for name in ("admin", "service", "affiliate", "shipping"):
        value = _decimal(_value(row, SETTLEMENT_ALIASES[name]), field=name)
        if value is not None:
            fees[name] = value
    fee_total = sum(fees.values(), Decimal("0")) if fees else None
    return {
        "store_name": _text(_value(row, SETTLEMENT_ALIASES["store"])),
        "marketplace": _text(_value(row, SETTLEMENT_ALIASES["marketplace"])).upper(),
        "order": _text(_value(row, SETTLEMENT_ALIASES["order"])),
        "reference": _text(_value(row, SETTLEMENT_ALIASES["reference"])),
        "date": _date(
            _value(row, SETTLEMENT_ALIASES["date"]), field="settlement_date", required=True
        ),
        "gross": _decimal(_value(row, SETTLEMENT_ALIASES["gross"]), field="gross_amount"),
        "net": _decimal(_value(row, SETTLEMENT_ALIASES["net"]), field="settled_amount"),
        "currency": _text(_value(row, SETTLEMENT_ALIASES["currency"])),
        "fees": fees,
        "fee_total": fee_total,
        "refund": _decimal(_value(row, SETTLEMENT_ALIASES["refund"]), field="refund_amount"),
        "adjustment": _decimal(
            _value(row, SETTLEMENT_ALIASES["adjustment"]), field="adjustment_amount"
        ),
    }


def _settlement_identity(values, source_row_key):
    return "|".join(
        (
            SETTLEMENT_EVENT_CODE,
            normalize_external_key(values["marketplace"]),
            normalize_external_key(values["store_name"]),
            normalize_external_key(values["reference"] or source_row_key),
            normalize_external_key(values["order"]),
            values["date"].isoformat(),
            source_row_key,
        )
    )[:500]


def _match_settlement(settlement):
    if not settlement.store or not settlement.external_order_number:
        return
    order = (
        OmniOrder.objects.filter(
            legal_entity=settlement.legal_entity,
            store=settlement.store,
            external_order_number=settlement.external_order_number,
        )
        .select_related("store")
        .first()
    )
    if order is None:
        settlement.reconciliation_status = OmniReconciliationStatus.SETTLEMENT_UNMATCHED
        settlement.reconciliation_message = (
            "No canonical order matched the Store and order reference."
        )
        settlement.save(
            update_fields=("reconciliation_status", "reconciliation_message", "updated_at")
        )
        return
    event = OmniRevenueEvent.objects.filter(
        order=order, state__in=[OmniRevenueState.ELIGIBLE, OmniRevenueState.BLOCKED_MAPPING]
    ).first()
    if event is None:
        settlement.reconciliation_status = OmniReconciliationStatus.SETTLEMENT_UNMATCHED
        settlement.reconciliation_message = (
            "Order exists but no completed revenue source event is available."
        )
    else:
        settlement.matched_revenue = event
        settlement.reconciliation_status = OmniReconciliationStatus.SETTLEMENT_MATCH
        settlement.reconciliation_message = (
            "Matched by legal entity, Store, marketplace scope, and order number."
        )
    settlement.save(
        update_fields=(
            "matched_revenue",
            "reconciliation_status",
            "reconciliation_message",
            "updated_at",
        )
    )


def refresh_settlement_reconciliation(event):
    event = OmniRevenueEvent.objects.get(pk=event.pk)
    settlements = list(event.settlements.filter(net_amount__isnull=False))
    if not settlements:
        return OmniReconciliationStatus.COMPLETED_NOT_SETTLED
    settled = sum((row.net_amount for row in settlements), Decimal("0"))
    if event.gross_eligible_amount is None:
        return OmniReconciliationStatus.SETTLEMENT_PARTIAL
    if settled > event.gross_eligible_amount:
        return OmniReconciliationStatus.SETTLEMENT_OVER
    if settled < event.gross_eligible_amount:
        return OmniReconciliationStatus.SETTLEMENT_PARTIAL
    return OmniReconciliationStatus.SETTLEMENT_MATCH


@transaction.atomic
def import_settlement_source(*, legal_entity, payload, source_filename, actor=None):
    rows = _payload_rows(payload, source_filename)
    if not rows:
        raise ValidationError("Settlement source has no rows.")
    file_hash = _payload_hash(payload, rows)
    batch, created = OmniSettlementImportBatch.objects.get_or_create(
        legal_entity=legal_entity,
        source_type="BIGSELLER_SETTLEMENT",
        file_hash=file_hash,
        defaults={
            "source_filename": source_filename,
            "row_count": len(rows),
            "imported_at": timezone.now(),
            "imported_by": actor,
        },
    )
    if not created:
        return batch
    for row_number, row in enumerate(rows, 2):
        values = _settlement_values(row)
        source_row_key = (
            _text(_value(row, ("Source Row ID", "Row ID", "Import_ID"))) or f"ROW:{row_number}"
        )
        identity = _settlement_identity(values, source_row_key)
        store, _ = _resolve_store(
            legal_entity, values["store_name"], values["marketplace"], values["date"]
        )
        existing = OmniSettlement.objects.filter(
            legal_entity=legal_entity, source_identity_key=identity
        ).first()
        defaults = {
            "batch": batch,
            "store": store,
            "external_store_name": values["store_name"],
            "marketplace": values["marketplace"] or (store.channel if store else ""),
            "settlement_reference": values["reference"],
            "external_order_number": values["order"],
            "settlement_date": values["date"],
            "currency": values["currency"],
            "gross_amount": values["gross"],
            "settled_amount": values["net"],
            "fee_amount": values["fee_total"],
            "refund_amount": values["refund"],
            "adjustment_amount": values["adjustment"],
            "net_amount": values["net"],
            "fee_components": {key: str(value) for key, value in values["fees"].items()},
            "raw_data": {str(key): _text(value) for key, value in row.items()},
            "source_row_key": source_row_key,
        }
        if existing:
            if existing.raw_data != defaults["raw_data"]:
                conflict_identity = f"{identity}|CONFLICT|{file_hash}"[:500]
                defaults.update(
                    source_identity_key=conflict_identity,
                    reconciliation_status=OmniReconciliationStatus.SOURCE_CHANGED,
                    reconciliation_message=(
                        "A later source changed an accepted settlement identity."
                    ),
                    conflict_of=existing,
                )
                settlement = OmniSettlement.objects.create(legal_entity=legal_entity, **defaults)
                _audit(settlement, "omnichannel.settlement_source.changed", actor)
                continue
            else:
                settlement = existing
        else:
            settlement = OmniSettlement.objects.create(
                legal_entity=legal_entity, source_identity_key=identity, **defaults
            )
        for fee_type, amount in values["fees"].items():
            OmniSettlementFee.objects.get_or_create(
                source_key=f"{settlement.source_identity_key}|FEE|{fee_type}",
                defaults={
                    "settlement": settlement,
                    "fee_type": fee_type,
                    "amount": amount,
                    "source_row_key": source_row_key,
                    "raw_data": {str(key): _text(value) for key, value in row.items()},
                },
            )
        _match_settlement(settlement)
        if settlement.matched_revenue_id:
            status = refresh_settlement_reconciliation(settlement.matched_revenue)
            OmniSettlement.objects.filter(matched_revenue=settlement.matched_revenue).update(
                reconciliation_status=status
            )
    _audit(batch, "omnichannel.settlement.imported", actor)
    return batch


def settlement_finance_candidate(settlement):
    settlement = OmniSettlement.objects.select_related(
        "legal_entity", "store", "matched_revenue"
    ).get(pk=settlement.pk)
    return {
        "event_code": SETTLEMENT_EVENT_CODE,
        "source_id": str(settlement.pk),
        "source_key": settlement.source_identity_key,
        "legal_entity_id": str(settlement.legal_entity_id),
        "store_id": str(settlement.store_id) if settlement.store_id else None,
        "marketplace": settlement.marketplace,
        "order_id": str(settlement.matched_revenue.order_id)
        if settlement.matched_revenue
        else None,
        "settlement_date": settlement.settlement_date,
        "gross_amount": settlement.gross_amount,
        "settled_amount": settlement.settled_amount,
        "fee_amount": settlement.fee_amount,
        "fee_components": settlement.fee_components,
        "refund_amount": settlement.refund_amount,
        "adjustment_amount": settlement.adjustment_amount,
        "currency": settlement.currency,
        "reconciliation_status": settlement.reconciliation_status,
        "source_lineage": {"batch_id": str(settlement.batch_id), "row": settlement.source_row_key},
    }


def _return_values(row):
    quantity = _decimal(
        _value(row, RETURN_ALIASES["quantity"]), field="return_quantity", required=True
    )
    if quantity is None or quantity <= 0:
        raise ValidationError("Return quantity must be positive.")
    return {
        "marketplace": _text(_value(row, RETURN_ALIASES["marketplace"])).upper(),
        "store_name": _text(_value(row, RETURN_ALIASES["store"])),
        "package": _text(_value(row, RETURN_ALIASES["package"])),
        "order": _text(_value(row, RETURN_ALIASES["order"])),
        "return_id": _text(_value(row, RETURN_ALIASES["return_id"])),
        "sku": _text(_value(row, RETURN_ALIASES["sku"])),
        "warehouse_sku": _text(_value(row, RETURN_ALIASES["warehouse_sku"])),
        "quantity": quantity,
        "stock_quantity": _decimal(
            _value(row, RETURN_ALIASES["stock_quantity"]), field="stock_quantity"
        ),
        "stock_status": _text(_value(row, RETURN_ALIASES["stock_status"])),
        "order_status": _text(_value(row, RETURN_ALIASES["order_status"])),
        "shipping_status": _text(_value(row, RETURN_ALIASES["shipping_status"])),
        "aftersales_status": _text(_value(row, RETURN_ALIASES["aftersales_status"])),
        "return_status": _text(_value(row, RETURN_ALIASES["return_status"])),
        "return_type": _text(_value(row, RETURN_ALIASES["return_type"])),
        "reason": _text(_value(row, RETURN_ALIASES["reason"])),
        "currency": _text(_value(row, RETURN_ALIASES["currency"])),
        "refund": _decimal(_value(row, RETURN_ALIASES["refund"]), field="refund_amount"),
        "order_date": _source_datetime(_value(row, RETURN_ALIASES["order_date"]), "order_date"),
        "requested_at": _source_datetime(
            _value(row, RETURN_ALIASES["requested_at"]), "requested_at"
        ),
        "deadline": _source_datetime(_value(row, RETURN_ALIASES["deadline"]), "deadline"),
        "shipped_at": _source_datetime(_value(row, RETURN_ALIASES["shipped_at"]), "shipped_at"),
        "arrived_at": _source_datetime(_value(row, RETURN_ALIASES["arrived_at"]), "arrived_at"),
        "stock_added_at": _source_datetime(
            _value(row, RETURN_ALIASES["stock_added_at"]), "stock_added_at"
        ),
    }


def _return_identity(values, source_row_key):
    return f"{RETURN_EVENT_CODE}|{source_row_key}"[:500]


def _link_return(source):
    if source.store is None:
        source.linkage_status = OmniReturnLinkageStatus.BLOCKED_MAPPING
        source.linkage_message = "Store is not mapped; original order cannot be resolved safely."
        source.save(update_fields=("linkage_status", "linkage_message", "updated_at"))
        return
    orders = OmniOrder.objects.filter(
        legal_entity=source.legal_entity,
        store=source.store,
        external_order_number=source.external_order_number,
    )
    if source.marketplace:
        orders = orders.filter(Q(marketplace=source.marketplace) | Q(marketplace=""))
    if orders.count() != 1:
        source.linkage_status = OmniReturnLinkageStatus.UNMATCHED_ORDER
        source.linkage_message = (
            "No unique canonical order matched Store, marketplace, and order number."
        )
        source.save(update_fields=("linkage_status", "linkage_message", "updated_at"))
        return
    order = orders.first()
    source.original_order = order
    lines = list(
        order.lines.filter(
            external_sku_normalized=normalize_external_key(source.external_sku)
        ).order_by("id")
    )
    if not lines:
        source.linkage_status = OmniReturnLinkageStatus.UNMATCHED_SKU
        source.linkage_message = "Original order matched, but SKU did not resolve to an order line."
    elif len(lines) > 1:
        source.linkage_status = OmniReturnLinkageStatus.AMBIGUOUS_ORDER_LINE
        source.linkage_message = (
            "Return source has no Variation column and cannot disambiguate multiple SKU lines."
        )
    else:
        source.original_order_line = lines[0]
        source.resolved_item = lines[0].item
        source.linkage_status = OmniReturnLinkageStatus.MATCHED
        source.linkage_message = (
            "Matched by Store, marketplace, order number, and exact SKU. Variation was unavailable."
        )
    source.save(
        update_fields=(
            "original_order",
            "original_order_line",
            "resolved_item",
            "linkage_status",
            "linkage_message",
            "updated_at",
        )
    )


@transaction.atomic
def import_return_source(*, legal_entity, payload, source_filename, actor=None):
    rows = _payload_rows(payload, source_filename)
    if not rows:
        raise ValidationError("Return source has no rows.")
    file_hash = _payload_hash(payload, rows)
    batch, created = OmniReturnImportBatch.objects.get_or_create(
        legal_entity=legal_entity,
        source_type="BIGSELLER_RETURN",
        file_hash=file_hash,
        defaults={
            "source_filename": source_filename,
            "row_count": len(rows),
            "imported_at": timezone.now(),
            "imported_by": actor,
        },
    )
    if not created:
        return batch
    for row_number, row in enumerate(rows, 2):
        values = _return_values(row)
        source_row_key = f"ROW:{row_number}"
        identity = _return_identity(values, source_row_key)
        store_date = (values["order_date"] or values["arrived_at"] or timezone.now()).date()
        store, store_message = _resolve_store(
            legal_entity, values["store_name"], values["marketplace"], store_date
        )
        source = OmniReturnSource.objects.create(
            batch=batch,
            legal_entity=legal_entity,
            marketplace=values["marketplace"] or (store.channel if store else ""),
            external_store_name=values["store_name"],
            store=store,
            package_number=values["package"],
            external_order_number=values["order"],
            external_return_id=values["return_id"],
            external_sku=values["sku"],
            warehouse_sku=values["warehouse_sku"],
            quantity=values["quantity"],
            stock_addition_quantity=values["stock_quantity"],
            refund_amount=values["refund"],
            currency=values["currency"],
            order_status=values["order_status"],
            shipping_status=values["shipping_status"],
            aftersales_status=values["aftersales_status"],
            return_status=values["return_status"],
            stock_addition_status=values["stock_status"],
            return_type=values["return_type"],
            return_reason=values["reason"],
            order_date=values["order_date"],
            return_requested_at=values["requested_at"],
            deadline_at=values["deadline"],
            shipped_at=values["shipped_at"],
            arrived_at=values["arrived_at"],
            stock_added_at=values["stock_added_at"],
            linkage_status=(
                OmniReturnLinkageStatus.BLOCKED_MAPPING
                if store is None
                else OmniReturnLinkageStatus.UNMATCHED_ORDER
            ),
            linkage_message=store_message,
            source_row_key=source_row_key,
            source_identity_key=identity,
            raw_data={str(key): _text(value) for key, value in row.items()},
        )
        _link_return(source)
        _audit(source, "omnichannel.return_source.imported", actor)
    _audit(batch, "omnichannel.return_batch.imported", actor)
    return batch


@transaction.atomic
def create_return_quality_candidate(return_source, *, warehouse=None, actor=None):
    """Create a draft Quality candidate only for an unambiguous mapped return."""

    from apps.quality.models import InspectionType
    from apps.quality.services.quality import add_inspection_line, create_inspection

    source = (
        OmniReturnSource.objects.select_for_update()
        .select_related("resolved_item")
        .get(pk=return_source.pk)
    )
    if source.linkage_status != OmniReturnLinkageStatus.MATCHED or source.resolved_item is None:
        raise ValidationError("Only an unambiguous mapped return can enter Quality.")
    if source.quality_inspection_line_id:
        return source.quality_inspection_line.inspection
    inspection = create_inspection(
        legal_entity=source.legal_entity,
        inspection_type=InspectionType.MARKETPLACE_RETURN,
        source_module="omnichannel",
        source_type="OMNI_RETURN",
        source_document_id=source.pk,
        source_key=f"QUALITY|OMNI_RETURN|{source.pk}",
        inspection_date=(source.arrived_at or timezone.now()).date(),
        warehouse=warehouse,
        evidence_reference=source.source_identity_key,
        evidence_metadata={"return_source_id": str(source.pk)},
        actor=actor,
    )
    line = add_inspection_line(
        inspection,
        source_line_id=str(source.pk),
        item=source.resolved_item,
        qty_presented=source.quantity,
        actor=actor,
    )
    source.quality_inspection_line = line
    source.save(update_fields=("quality_inspection_line", "updated_at"))
    _audit(source, "omnichannel.return_quality_candidate.created", actor)
    return inspection


def return_finance_candidate(source):
    source = OmniReturnSource.objects.select_related(
        "legal_entity", "store", "original_order", "original_order_line"
    ).get(pk=source.pk)
    return {
        "event_code": RETURN_EVENT_CODE,
        "source_id": str(source.pk),
        "source_key": source.source_identity_key,
        "legal_entity_id": str(source.legal_entity_id),
        "store_id": str(source.store_id) if source.store_id else None,
        "marketplace": source.marketplace,
        "order_id": str(source.original_order_id) if source.original_order_id else None,
        "revenue_event_id": (
            str(source.original_order.revenue_events.first().pk)
            if source.original_order and source.original_order.revenue_events.exists()
            else None
        ),
        "amount": source.refund_amount,
        "currency": source.currency,
        "transaction_date": (source.arrived_at or source.order_date).date()
        if (source.arrived_at or source.order_date)
        else None,
        "reason": source.return_reason,
        "linkage_status": source.linkage_status,
        "source_lineage": {"batch_id": str(source.batch_id), "row": source.source_row_key},
    }


@transaction.atomic
def create_adjustment_source(*, legal_entity, data, actor=None):
    data = dict(data)
    raw_data = _json_safe(data)
    adjustment_type = _text(data.get("adjustment_type") or data.get("type"))
    if not adjustment_type:
        raise ValidationError("Adjustment type is required.")
    source_row_key = _text(data.get("source_row_key")) or "ROW:1"
    reference = _text(data.get("reference") or data.get("adjustment_reference"))
    order_number = _text(data.get("external_order_number") or data.get("order"))
    identity = "|".join(
        (
            ADJUSTMENT_EVENT_CODE,
            normalize_external_key(reference or source_row_key),
            normalize_external_key(adjustment_type),
            normalize_external_key(order_number),
        )
    )[:500]
    existing = OmniAdjustmentSource.objects.filter(
        legal_entity=legal_entity, source_identity_key=identity
    ).first()
    if existing:
        if existing.raw_data != raw_data:
            raise ValidationError("Adjustment identity already exists with different source data.")
        return existing
    store = data.get("store")
    if not isinstance(store, Store):
        store, _ = _resolve_store(
            legal_entity,
            _text(data.get("store_name")),
            _text(data.get("marketplace")),
            data.get("transaction_date"),
        )
    adjustment = OmniAdjustmentSource.objects.create(
        legal_entity=legal_entity,
        store=store,
        marketplace=_text(data.get("marketplace")),
        external_order_number=order_number,
        settlement=data.get("settlement"),
        adjustment_type=adjustment_type,
        amount=_decimal(data.get("amount"), field="adjustment_amount"),
        transaction_date=data.get("transaction_date"),
        source_batch=data.get("source_batch"),
        source_row_key=source_row_key,
        source_identity_key=identity,
        reconciliation_status=(OmniReconciliationStatus.ADJUSTMENT_PENDING),
        raw_data=raw_data,
    )
    _audit(adjustment, "omnichannel.adjustment_source.created", actor)
    return adjustment


@transaction.atomic
def create_payout_source(*, legal_entity, data, actor=None):
    data = dict(data)
    raw_data = _json_safe(data)
    reference = _text(data.get("payout_reference") or data.get("reference"))
    if not reference:
        raise ValidationError("Payout reference is required.")
    source_row_key = _text(data.get("source_row_key")) or "ROW:1"
    identity = f"{PAYOUT_EVENT_CODE}|{normalize_external_key(reference)}|{source_row_key}"[:500]
    existing = OmniPayoutSource.objects.filter(
        legal_entity=legal_entity, source_identity_key=identity
    ).first()
    if existing:
        if existing.raw_data != raw_data:
            raise ValidationError("Payout identity already exists with different source data.")
        return existing
    store = data.get("store")
    if not isinstance(store, Store):
        store, _ = _resolve_store(
            legal_entity,
            _text(data.get("store_name")),
            _text(data.get("marketplace")),
            data.get("payout_date"),
        )
    payout = OmniPayoutSource.objects.create(
        legal_entity=legal_entity,
        store=store,
        marketplace=_text(data.get("marketplace")),
        payout_reference=reference,
        payout_date=data.get("payout_date"),
        amount=_decimal(data.get("amount"), field="payout_amount"),
        currency=_text(data.get("currency")),
        settlement_references=list(data.get("settlement_references") or []),
        source_filename=_text(data.get("source_filename")),
        source_row_key=source_row_key,
        source_identity_key=identity,
        reconciliation_status=OmniReconciliationStatus.UNMATCHED_PAYOUT,
        raw_data=raw_data,
        created_by=actor,
    )
    if payout.store_id and payout.settlement_references:
        total = OmniSettlement.objects.filter(
            legal_entity=legal_entity,
            store=payout.store,
            settlement_reference__in=payout.settlement_references,
        ).aggregate(total=Sum("net_amount"))["total"]
        if total is not None and payout.amount is not None:
            payout.reconciliation_status = (
                OmniReconciliationStatus.PAYOUT_MATCH
                if total == payout.amount
                else OmniReconciliationStatus.PAYOUT_PENDING
            )
            payout.reconciliation_message = (
                "Payout matches referenced settlement source amount."
                if total == payout.amount
                else "Payout amount differs from referenced settlement sources."
            )
            payout.save(
                update_fields=("reconciliation_status", "reconciliation_message", "updated_at")
            )
    _audit(payout, "omnichannel.payout_source.created", actor)
    return payout


def import_payout_sources(*, legal_entity, rows, actor=None):
    return tuple(
        create_payout_source(legal_entity=legal_entity, data=row, actor=actor) for row in rows
    )
