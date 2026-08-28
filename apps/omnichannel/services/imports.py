from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.channels.models import ExternalSKUMap, Store
from apps.channels.selectors.channels import normalize_external_key
from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.omnichannel.models import (
    OmniException,
    OmniImportBatch,
    OmniImportBatchStatus,
    OmniImportRow,
    OmniMappingStatus,
    OmniOperationalStatus,
    OmniOrder,
    OmniOrderLine,
    OmniRowStatus,
)

SOURCE_TYPE_BIGSELLER = "BIGSELLER_ORDER"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50_000

HEADER_ALIASES = {
    "order_number": ("Nomor Pesanan", "No Pesanan", "Order Number", "Order No", "No. Pesanan"),
    "order_date": (
        "Waktu Pesanan Dibuat",
        "Order Creation Time",
        "Order Date",
        "Tanggal Pesanan",
        "Tanggal",
    ),
    "completion_date": ("Waktu Selesai", "Completion Time", "Completion Date", "Tanggal Selesai"),
    "status": ("Status Pesanan", "Order Status", "Status"),
    "store": ("Nama Panggilan Toko BigSeller", "Shop Name", "Store Name", "Toko"),
    "marketplace": ("Marketplace", "Platform", "Channel"),
    "sku": ("SKU", "Nomor Referensi SKU", "Marketplace SKU"),
    "product": ("Nama Produk", "Produk", "Product Name", "Marketplace Item Name"),
    "variation": ("Nama Variasi", "Variasi", "Varian", "Variation", "Marketplace Variation"),
    "quantity": ("Jumlah", "Quantity", "Qty"),
    "subtotal": ("Subtotal Produk", "Product Subtotal", "Subtotal", "Total"),
    "tracking": ("Nomor Resi", "Tracking Number", "Tracking No", "No Resi"),
    "source_line": ("Order Line ID", "Order Item ID", "Line ID", "ID Produk"),
}
REQUIRED_FIELDS = ("order_number", "order_date", "store", "sku", "quantity")


def _key(value) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split()).casefold()


def _text(value) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _decimal(value, *, field, required=False):
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError(f"{field} is required.")
        return None
    text = str(value).strip().replace("Rp", "").replace("rp", "").replace(" ", "")
    if "," in text and "." in text:
        text = (
            text.replace(".", "").replace(",", ".")
            if text.rfind(",") > text.rfind(".")
            else text.replace(",", "")
        )
    elif "," in text:
        parts = text.split(",")
        text = (
            parts[0] + "." + parts[1] if len(parts) == 2 and len(parts[1]) <= 2 else "".join(parts)
        )
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field} is invalid.") from error


def _date(value, *, field, required=False):
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError(f"{field} is required.")
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float, Decimal)):
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
    text = str(value).strip()
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
        "%d %b %Y %H:%M:%S",
        "%d %b %Y %H:%M",
        "%d %b %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{field} is invalid.")


def _normalized_status(value) -> str:
    text = _key(value)
    if any(token in text for token in ("batal", "cancel", "gagal")):
        return OmniOperationalStatus.CANCELLED
    if "refund" in text:
        return OmniOperationalStatus.REFUNDED
    if "retur" in text or "return" in text:
        return OmniOperationalStatus.RETURNED
    if any(token in text for token in ("selesai", "completed", "delivered")):
        return OmniOperationalStatus.COMPLETED
    if any(token in text for token in ("proses", "process", "dikirim", "kirim", "pickup")):
        return OmniOperationalStatus.PROCESSING
    return OmniOperationalStatus.PENDING if text else OmniOperationalStatus.UNKNOWN


def _xml_text(element, shared_strings):
    if element is None:
        return ""
    value = element.find("{*}v")
    if element.attrib.get("t") == "inlineStr":
        return "".join(value.text or "" for value in element.findall(".//{*}t"))
    raw = value.text if value is not None else ""
    if element.attrib.get("t") == "s" and raw:
        return shared_strings[int(raw)] if int(raw) < len(shared_strings) else ""
    return raw or ""


def _read_xlsx(payload: bytes):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(node.text or "" for node in si.findall(".//{*}t"))
                for si in root.findall("{*}si")
            ]
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in names:
            candidates = sorted(
                name
                for name in names
                if name.startswith("xl/worksheets/") and name.endswith(".xml")
            )
            if not candidates:
                raise ValidationError("XLSX does not contain a worksheet.")
            sheet_name = candidates[0]
        root = ElementTree.fromstring(archive.read(sheet_name))
        rows = []
        for row in root.findall(".//{*}row"):
            cells = {}
            for cell in row.findall("{*}c"):
                ref = cell.attrib.get("r", "A1")
                letters = "".join(char for char in ref if char.isalpha())
                index = 0
                for char in letters.upper():
                    index = index * 26 + ord(char) - 64
                cells[index - 1] = _xml_text(cell, shared)
            rows.append(cells)
    if not rows:
        return []
    width = max((max(row.keys(), default=-1) for row in rows), default=-1) + 1
    headers = [_text(rows[0].get(index, "")) for index in range(width)]
    return [
        {headers[index]: row.get(index, "") for index in range(width) if headers[index]}
        for row in rows[1:]
    ]


def _read_csv(payload: bytes):
    try:
        return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
    except UnicodeDecodeError as error:
        raise ValidationError("CSV must be UTF-8 encoded.") from error


def read_bigseller_rows(payload: bytes, source_filename: str):
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValidationError("Import file is too large.")
    suffix = source_filename.lower().rsplit(".", 1)[-1] if "." in source_filename else ""
    if suffix == "xlsx":
        rows = _read_xlsx(payload)
    elif suffix == "csv":
        rows = _read_csv(payload)
    else:
        raise ValidationError("BigSeller import supports XLSX and CSV files.")
    if len(rows) > MAX_ROWS:
        raise ValidationError(f"Import has too many rows. Maximum is {MAX_ROWS}.")
    if not rows:
        raise ValidationError("Import file has no data rows.")
    header_keys = {_key(header) for row in rows[:1] for header in row}
    missing = [
        field
        for field in REQUIRED_FIELDS
        if not any(_key(alias) in header_keys for alias in HEADER_ALIASES[field])
    ]
    if missing:
        raise ValidationError("Missing required BigSeller headers: " + ", ".join(missing))
    return rows


def _value(row, field):
    for alias in HEADER_ALIASES[field]:
        wanted = _key(alias)
        for key, value in row.items():
            if _key(key) == wanted:
                return value
    return ""


def _normalize_source_row(row, row_number):
    raw = {_text(key): _text(value) for key, value in row.items() if _text(key)}
    order_number = _text(_value(row, "order_number"))
    store = _text(_value(row, "store"))
    marketplace = _text(_value(row, "marketplace")).upper()
    sku = _text(_value(row, "sku"))
    product = _text(_value(row, "product"))
    variation = _text(_value(row, "variation"))
    if not sku:
        sku = variation or product
    order_date = _date(_value(row, "order_date"), field="order_date", required=True)
    completion_date = _date(_value(row, "completion_date"), field="completion_date")
    quantity = _decimal(_value(row, "quantity"), field="quantity", required=True)
    subtotal = _decimal(_value(row, "subtotal"), field="subtotal")
    source_line = _text(_value(row, "source_line"))
    source_row_key = source_line or f"ROW:{row_number}"
    if not order_number:
        raise ValueError("order_number is required.")
    if not store:
        raise ValueError("store is required.")
    if not sku:
        raise ValueError("sku is required.")
    if quantity is None or quantity <= 0:
        raise ValueError("quantity must be greater than zero.")
    return {
        "source_row_key": source_row_key[:255],
        "external_order_number": order_number[:150],
        "external_store_name": store[:255],
        "marketplace": marketplace[:80],
        "external_sku": sku[:150],
        "external_sku_normalized": normalize_external_key(sku)[:150],
        "product": product[:255],
        "variation": variation[:255],
        "variation_normalized": normalize_external_key(variation)[:255],
        "marketplace_quantity": quantity,
        "source_subtotal": subtotal,
        "order_date": order_date,
        "completion_date": completion_date,
        "tracking_number": _text(_value(row, "tracking"))[:160],
        "raw_status": _text(_value(row, "status"))[:120],
        "normalized_status": _normalized_status(_value(row, "status")),
        "raw_data": raw,
    }


def _store_match(entity, raw_name, marketplace, business_date):
    key = normalize_external_key(raw_name)
    qs = Store.objects.filter(legal_entity=entity, effective_from__lte=business_date).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=business_date)
    )
    if marketplace:
        qs = qs.filter(channel=marketplace)
    matches = []
    for store in qs:
        identifiers = {
            normalize_external_key(store.code),
            normalize_external_key(store.name),
            normalize_external_key(store.external_account_id),
            *(normalize_external_key(alias) for alias in store.external_aliases),
        }
        if key and key in identifiers and (business_date < timezone.localdate() or store.is_active):
            matches.append(store)
    return matches


def _mapping_match(store, sku, variation, business_date):
    qs = (
        ExternalSKUMap.objects.filter(
            store=store,
            external_sku_normalized=normalize_external_key(sku),
            external_variation_normalized=normalize_external_key(variation),
            effective_from__lte=business_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=business_date))
        .select_related("item")
    )
    active = [
        mapping
        for mapping in qs
        if (
            business_date < timezone.localdate()
            or (mapping.is_active and mapping.item.is_active and store.is_active)
        )
    ]
    if len(active) == 1:
        return active[0], ""
    if len(active) > 1:
        return None, "MAPPING_INACTIVE"
    if qs.exists():
        return None, "MAPPING_INACTIVE"
    return None, "UNMAPPED_SKU"


def _resolve(normalized, entity):
    result = dict(normalized)
    result.update(
        {
            "resolved_store": None,
            "resolved_mapping": None,
            "resolved_item": None,
            "conversion_quantity": None,
            "mapping_status": OmniMappingStatus.READY,
            "exception_code": "",
            "exception_message": "",
        }
    )
    try:
        stores = _store_match(
            entity,
            normalized["external_store_name"],
            normalized["marketplace"],
            normalized["order_date"],
        )
        if len(stores) != 1:
            result["mapping_status"] = OmniMappingStatus.UNMAPPED_STORE
            result["exception_code"] = OmniMappingStatus.UNMAPPED_STORE
            result["exception_message"] = "Store alias is not uniquely mapped to an active Store."
            return result
        result["resolved_store"] = stores[0]
        mapping, issue = _mapping_match(
            stores[0], normalized["external_sku"], normalized["variation"], normalized["order_date"]
        )
        if mapping is None:
            result["mapping_status"] = issue
            result["exception_code"] = issue
            result["exception_message"] = (
                "External SKU and variation have no effective canonical Item mapping."
            )
            return result
        result["resolved_mapping"] = mapping
        result["resolved_item"] = mapping.item
        result["conversion_quantity"] = mapping.conversion_quantity
    except Exception as error:
        result["mapping_status"] = OmniMappingStatus.UNMAPPED_STORE
        result["exception_code"] = "UNMAPPED_STORE"
        result["exception_message"] = str(error)
    return result


def _audit(batch, action, actor=None, metadata=None):
    record_audit_event(
        action=action,
        target_type=batch._meta.label_lower,
        target_id=batch.pk,
        actor=actor,
        source="omnichannel.service",
        metadata=metadata or {},
    )


@transaction.atomic
def preview_bigseller_import(*, legal_entity, payload, source_filename, actor=None):
    checksum = (
        hashlib.sha256(payload).hexdigest()
        if isinstance(payload, bytes)
        else hashlib.sha256(repr(payload).encode()).hexdigest()
    )
    existing = OmniImportBatch.objects.filter(
        legal_entity=legal_entity, source_type=SOURCE_TYPE_BIGSELLER, file_hash=checksum
    ).first()
    if existing:
        existing.replay_count += 1
        existing.save(update_fields=("replay_count", "updated_at"))
        _audit(existing, "omnichannel.import.replayed", actor)
        return existing
    rows = payload if isinstance(payload, list) else read_bigseller_rows(payload, source_filename)
    batch = OmniImportBatch.objects.create(
        legal_entity=legal_entity,
        source_type=SOURCE_TYPE_BIGSELLER,
        source_filename=source_filename[:255],
        file_hash=checksum,
        imported_by=actor,
        row_count=len(rows),
        status=OmniImportBatchStatus.PREVIEW,
    )
    objects = []
    rejected = 0
    seen_source_rows = set()
    for number, raw in enumerate(rows, start=2):
        try:
            normalized = _normalize_source_row(raw, number)
            if normalized["source_row_key"] in seen_source_rows:
                raise ValueError("DUPLICATE_SOURCE: source row identity is repeated in this file.")
            seen_source_rows.add(normalized["source_row_key"])
            normalized = _resolve(normalized, legal_entity)
            row_status = OmniRowStatus.VALID
            if normalized["mapping_status"] != OmniMappingStatus.READY:
                rejected += 1
                row_status = OmniRowStatus.REJECTED
        except ValueError as error:
            rejected += 1
            normalized = {
                "source_row_key": f"ROW:{number}",
                "external_order_number": _text(_value(raw, "order_number")),
                "external_store_name": _text(_value(raw, "store")),
                "marketplace": _text(_value(raw, "marketplace")).upper(),
                "external_sku": _text(_value(raw, "sku")),
                "raw_data": {_text(key): _text(value) for key, value in raw.items() if _text(key)},
                "mapping_status": OmniMappingStatus.DUPLICATE_SOURCE
                if "DUPLICATE_SOURCE" in str(error)
                else OmniMappingStatus.INVALID_QTY
                if "quantity" in str(error)
                else OmniMappingStatus.INVALID_ORDER_DATE
                if "order_date" in str(error)
                else OmniMappingStatus.INVALID_COMPLETION_DATE
                if "completion_date" in str(error)
                else OmniMappingStatus.UNMAPPED_SKU,
                "exception_code": (
                    OmniMappingStatus.DUPLICATE_SOURCE
                    if "DUPLICATE_SOURCE" in str(error)
                    else OmniMappingStatus.INVALID_QTY
                    if "quantity" in str(error)
                    else OmniMappingStatus.INVALID_ORDER_DATE
                    if "order_date" in str(error)
                    else OmniMappingStatus.INVALID_COMPLETION_DATE
                    if "completion_date" in str(error)
                    else "INVALID_ROW"
                ),
                "exception_message": str(error),
                "row_status": OmniRowStatus.REJECTED,
                "normalized_status": OmniOperationalStatus.UNKNOWN,
            }
            row_status = OmniRowStatus.REJECTED
        objects.append(
            OmniImportRow(
                batch=batch,
                row_number=number,
                row_status=row_status,
                **{
                    key: value
                    for key, value in normalized.items()
                    if key in {field.name for field in OmniImportRow._meta.fields}
                    and key not in {"batch", "row_status"}
                },
            )
        )
    OmniImportRow.objects.bulk_create(objects)
    batch.accepted_count = len(objects) - rejected
    batch.rejected_count = rejected
    batch.status = OmniImportBatchStatus.READY if rejected == 0 else OmniImportBatchStatus.PARTIAL
    batch.save(update_fields=("accepted_count", "rejected_count", "status", "updated_at"))
    _audit(batch, "omnichannel.import.previewed", actor, {"rows": len(rows), "rejected": rejected})
    return batch


def _snapshot_store(store, external_identifier=""):
    return {
        "id": str(store.pk),
        "code": store.code,
        "name": store.name,
        "channel": store.channel,
        "external_identifier": external_identifier,
        "mapping_rule": "exact_store_identifier",
        "effective_from": store.effective_from.isoformat(),
    }


def _snapshot_mapping(mapping):
    return {
        "id": str(mapping.pk),
        "store_id": str(mapping.store_id),
        "marketplace": mapping.store.channel,
        "external_sku": mapping.external_sku,
        "external_variation": mapping.external_variation,
        "item_id": str(mapping.item_id),
        "item_code": mapping.item.code,
        "item_name": mapping.item.name,
        "conversion_quantity": str(mapping.conversion_quantity),
        "effective_from": mapping.effective_from.isoformat(),
    }


def _source_key(entity, row):
    marketplace = row.marketplace or (row.resolved_store.channel if row.resolved_store else "")
    store_identity = (
        str(row.resolved_store.pk) if row.resolved_store else _key(row.external_store_name)
    )
    return "|".join(
        (
            str(entity.pk),
            _key(marketplace),
            store_identity,
            _key(row.external_order_number),
        )
    )


@transaction.atomic
def commit_bigseller_import(*, batch, actor=None, idempotency_key=""):
    batch = OmniImportBatch.objects.select_for_update().get(pk=batch.pk)
    if batch.status == OmniImportBatchStatus.IMPORTED:
        return batch
    key = idempotency_key or f"OMNI_IMPORT|{batch.pk}"
    claim = claim_idempotency(
        namespace="omnichannel.import.commit",
        key=key,
        payload={"batch": str(batch.pk)},
        actor=actor,
    )
    if not claim.is_new:
        if claim.record.result_reference:
            return OmniImportBatch.objects.get(pk=claim.record.result_reference)
        raise ValidationError("The same import request is already in progress.")
    rows = list(
        batch.rows.select_for_update()
        .filter(
            Q(row_status=OmniRowStatus.VALID)
            | Q(
                mapping_status__in=[
                    OmniMappingStatus.UNMAPPED_STORE,
                    OmniMappingStatus.UNMAPPED_SKU,
                    OmniMappingStatus.MAPPING_INACTIVE,
                ]
            )
        )
        .exclude(marketplace_quantity__isnull=True)
        .exclude(order_date__isnull=True)
        .select_related("resolved_store", "resolved_mapping", "resolved_item")
    )
    grouped = {}
    for row in rows:
        grouped.setdefault(_source_key(batch.legal_entity, row), []).append(row)
    for order_key, source_rows in grouped.items():
        first = source_rows[0]
        source_changed = False
        order, _ = OmniOrder.objects.select_for_update().get_or_create(
            legal_entity=batch.legal_entity,
            source_identity_key=order_key,
            defaults={
                "external_order_number": first.external_order_number,
                "external_store_name": first.external_store_name,
                "marketplace": first.marketplace
                or (first.resolved_store.channel if first.resolved_store else "BIGSELLER"),
                "order_date": first.order_date,
                "completion_date": first.completion_date,
                "raw_status": first.raw_status,
                "normalized_status": first.normalized_status,
                "tracking_number": first.tracking_number,
                "store": first.resolved_store,
                "store_code_snapshot": first.resolved_store.code if first.resolved_store else "",
                "store_name_snapshot": first.resolved_store.name if first.resolved_store else "",
                "store_channel_snapshot": first.resolved_store.channel
                if first.resolved_store
                else "",
                "store_mapping_snapshot": _snapshot_store(
                    first.resolved_store, first.external_store_name
                )
                if first.resolved_store
                else {},
                "source_batch": batch,
                "last_source_hash": batch.file_hash,
            },
        )
        order.source_batch = batch
        order.external_store_name = first.external_store_name
        order.marketplace = first.marketplace or (
            first.resolved_store.channel
            if first.resolved_store
            else order.marketplace or "BIGSELLER"
        )
        order.store = first.resolved_store
        order.store_code_snapshot = first.resolved_store.code if first.resolved_store else ""
        order.store_name_snapshot = first.resolved_store.name if first.resolved_store else ""
        order.store_channel_snapshot = first.resolved_store.channel if first.resolved_store else ""
        order.store_mapping_snapshot = (
            _snapshot_store(first.resolved_store, first.external_store_name)
            if first.resolved_store
            else {}
        )
        (
            order.order_date,
            order.completion_date,
            order.raw_status,
            order.normalized_status,
            order.tracking_number,
        ) = (
            first.order_date,
            first.completion_date,
            first.raw_status,
            first.normalized_status,
            first.tracking_number,
        )
        order.last_source_hash = batch.file_hash
        order.save()
        lines = {}
        for row in source_rows:
            lines.setdefault((row.external_sku_normalized, row.variation_normalized), []).append(
                row
            )
        for identity, line_rows in lines.items():
            first_line = line_rows[0]
            qty = sum((line.marketplace_quantity for line in line_rows), Decimal("0"))
            subtotal_values = [
                line.source_subtotal for line in line_rows if line.source_subtotal is not None
            ]
            subtotal = sum(subtotal_values, Decimal("0")) if subtotal_values else None
            conversion = first_line.conversion_quantity
            values = {
                "source_row_key": "|".join(line.source_row_key for line in line_rows)[:255],
                "external_sku": first_line.external_sku,
                "external_sku_normalized": first_line.external_sku_normalized,
                "product": first_line.product,
                "variation": first_line.variation,
                "variation_normalized": first_line.variation_normalized,
                "item": first_line.resolved_item,
                "item_code_snapshot": first_line.resolved_item.code
                if first_line.resolved_item
                else "",
                "item_name_snapshot": first_line.resolved_item.name
                if first_line.resolved_item
                else "",
                "mapping": first_line.resolved_mapping,
                "mapping_snapshot": _snapshot_mapping(first_line.resolved_mapping)
                if first_line.resolved_mapping
                else {},
                "marketplace_quantity": qty,
                "conversion_quantity": conversion,
                "internal_quantity": qty * conversion if conversion else None,
                "source_subtotal": subtotal,
                "raw_status": first_line.raw_status,
                "normalized_status": first_line.normalized_status,
                "mapping_status": first_line.mapping_status,
                "source_row_metadata": {
                    "batch_id": str(batch.pk),
                    "rows": [line.row_number for line in line_rows],
                },
            }
            line, created = OmniOrderLine.objects.select_for_update().get_or_create(
                order=order,
                external_sku_normalized=identity[0],
                variation_normalized=identity[1],
                defaults=values,
            )
            packed = line.packing_lines.filter(warehouse_movement__isnull=False).exists()
            changed = any(
                getattr(line, field) != value
                for field, value in values.items()
                if field
                in {
                    "marketplace_quantity",
                    "conversion_quantity",
                    "internal_quantity",
                    "item_id",
                    "mapping_id",
                    "source_subtotal",
                    "raw_status",
                    "normalized_status",
                }
            )
            if not created and changed and packed:
                line.source_sync_status = OmniMappingStatus.SOURCE_CHANGED
                line.save(update_fields=("source_sync_status", "updated_at"))
                source_changed = True
                OmniException.objects.create(
                    legal_entity=batch.legal_entity,
                    batch=batch,
                    order=order,
                    line=line,
                    code=OmniMappingStatus.SOURCE_CHANGED,
                    message=(
                        "Source row changed after Warehouse packing; "
                        "physical history was preserved."
                    ),
                    metadata={"batch": str(batch.pk)},
                )
            elif not created:
                for field, value in values.items():
                    setattr(line, field, value)
                line.source_sync_status = OmniMappingStatus.READY
                line.save()
        line_statuses = set(order.lines.values_list("mapping_status", flat=True))
        order.mapping_status = (
            OmniMappingStatus.READY
            if line_statuses == {OmniMappingStatus.READY}
            else next(
                iter(line_statuses - {OmniMappingStatus.READY}), OmniMappingStatus.UNMAPPED_SKU
            )
        )
        order.source_sync_status = (
            OmniMappingStatus.SOURCE_CHANGED if source_changed else OmniMappingStatus.READY
        )
        order.save(update_fields=("mapping_status", "source_sync_status", "updated_at"))
    batch.status = (
        OmniImportBatchStatus.IMPORTED
        if batch.rejected_count == 0
        else OmniImportBatchStatus.PARTIAL
    )
    batch.imported_at = timezone.now()
    batch.save(update_fields=("status", "imported_at", "updated_at"))
    OmniImportRow.objects.filter(batch=batch, row_status=OmniRowStatus.VALID).update(
        row_status=OmniRowStatus.IMPORTED
    )
    _audit(batch, "omnichannel.import.committed", actor, {"orders": len(grouped)})
    complete_idempotency(claim.record.pk, result_reference=str(batch.pk))
    return batch
