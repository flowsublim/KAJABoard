from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import IdempotencyStatus
from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.core.services.numbering import allocate_document_number
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.organizations.models import LegalEntity
from apps.partners.models import BusinessPartner
from apps.sales.models import (
    SalesDelivery,
    SalesDeliveryLine,
    SalesDeliveryState,
    SalesOrderLine,
    SalesOrderState,
)

SALES_DELIVERY_DOCUMENT_TYPE = "SALES_DELIVERY"


def _text(value) -> str:
    return " ".join(str(value or "").split())


def _quantity(value) -> Decimal:
    return Decimal(str(value or 0))


def _audit(instance, *, action, actor=None, reason="", before=None, metadata=None):
    after = model_snapshot(instance)
    record_audit_event(
        action=action,
        target_type=instance._meta.label_lower,
        target_id=instance.pk,
        actor=actor,
        source="sales.delivery_service",
        reason=reason,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after) if before else sorted(after),
        metadata=metadata or {},
    )


def _assert_draft(delivery: SalesDelivery):
    if delivery.state != SalesDeliveryState.DRAFT:
        raise ValidationError("Only DRAFT Sales Deliveries can be edited.")


def _validate_customer(customer, entity):
    if customer.legal_entity_id != entity.id:
        raise ValidationError({"customer": "Customer must belong to the delivery legal entity."})


def _delivery_payload(entity, customer, delivery_date, values):
    return {
        "legal_entity": str(entity.pk),
        "customer": str(customer.pk),
        "delivery_date": delivery_date.isoformat(),
        "destination": _text(values.get("destination_snapshot")),
        "expedition": _text(values.get("expedition_reference")),
        "notes": _text(values.get("notes")),
    }


def _claim_or_replay(*, key, payload, actor):
    if not key:
        return None, None
    claim = claim_idempotency(
        namespace="sales.delivery.create", key=key, payload=payload, actor=actor
    )
    if claim.is_new:
        return claim, None
    if claim.record.status != IdempotencyStatus.COMPLETED or not claim.record.result_reference:
        raise ValidationError(
            "A prior delivery request with this idempotency key is still in progress."
        )
    return claim, SalesDelivery.objects.get(pk=claim.record.result_reference)


def _snapshot_customer(delivery: SalesDelivery):
    delivery.customer_code_snapshot = delivery.customer.code
    delivery.customer_name_snapshot = delivery.customer.display_name
    delivery.customer_legal_name_snapshot = delivery.customer.legal_name


@transaction.atomic
def create_draft_delivery(*, actor=None, idempotency_key="", **values) -> SalesDelivery:
    entity = LegalEntity.objects.select_for_update().get(pk=values["legal_entity"].pk)
    customer = BusinessPartner.objects.get(pk=values["customer"].pk)
    delivery_date = values["delivery_date"]
    _validate_customer(customer, entity)
    payload = _delivery_payload(entity, customer, delivery_date, values)
    claim, replay = _claim_or_replay(key=idempotency_key, payload=payload, actor=actor)
    if replay:
        return replay
    allocation = allocate_document_number(
        entity,
        SALES_DELIVERY_DOCUMENT_TYPE,
        business_date=delivery_date,
        request_key=f"sales-delivery:{idempotency_key}" if idempotency_key else "",
        actor=actor,
    )
    delivery = SalesDelivery(
        legal_entity=entity,
        document_allocation=allocation,
        document_number=allocation.number,
        delivery_date=delivery_date,
        customer=customer,
        destination_snapshot=_text(values.get("destination_snapshot")),
        expedition_reference=_text(values.get("expedition_reference")),
        notes=str(values.get("notes", "") or "").strip(),
        created_by=actor,
    )
    _snapshot_customer(delivery)
    delivery.full_clean()
    delivery.save()
    _audit(delivery, action="sales.salesdelivery.created", actor=actor)
    if claim:
        complete_idempotency(
            claim.record.pk,
            result_reference=str(delivery.pk),
            response={
                "sales_delivery_id": str(delivery.pk),
                "document_number": delivery.document_number,
            },
        )
    return delivery


def _validate_source_line(delivery: SalesDelivery, source_line: SalesOrderLine):
    order = source_line.sales_order
    if order.legal_entity_id != delivery.legal_entity_id:
        raise ValidationError("Sales Order line must belong to the delivery legal entity.")
    if order.customer_id != delivery.customer_id:
        raise ValidationError("All delivery lines must belong to the selected customer.")
    if order.state != SalesOrderState.CONFIRMED:
        raise ValidationError("Only CONFIRMED Sales Order lines can be delivered.")


def _next_line_number(delivery: SalesDelivery) -> int:
    return (
        delivery.lines.order_by("-line_number").values_list("line_number", flat=True).first() or 0
    ) + 1


def _add_line_locked(
    delivery: SalesDelivery, *, source_sales_order_line, quantity, notes="", line_number=None
):
    _assert_draft(delivery)
    source = SalesOrderLine.objects.select_related("sales_order", "item").get(
        pk=source_sales_order_line.pk
    )
    _validate_source_line(delivery, source)
    qty = _quantity(quantity)
    if qty <= 0:
        raise ValidationError({"quantity": "Delivery quantity must be greater than zero."})
    line = SalesDeliveryLine(
        sales_delivery=delivery,
        source_sales_order_line=source,
        line_number=line_number or _next_line_number(delivery),
        item=source.item,
        source_sales_order_number_snapshot=source.sales_order.document_number,
        item_code_snapshot=source.item_code_snapshot,
        item_name_snapshot=source.item_name_snapshot,
        description_snapshot=source.description_snapshot,
        uom_code_snapshot=source.uom_code_snapshot,
        ordered_quantity_snapshot=source.quantity,
        quantity=qty,
        notes=str(notes or "").strip(),
    )
    line.full_clean()
    line.save()
    return line


@transaction.atomic
def add_draft_delivery_line(
    delivery: SalesDelivery, *, source_sales_order_line, quantity, actor=None, reason="", notes=""
) -> SalesDeliveryLine:
    delivery = SalesDelivery.objects.select_for_update().get(pk=delivery.pk)
    before = model_snapshot(delivery)
    line = _add_line_locked(
        delivery,
        source_sales_order_line=source_sales_order_line,
        quantity=quantity,
        notes=notes,
    )
    _audit(
        delivery,
        action="sales.salesdelivery.line_added",
        actor=actor,
        reason=reason,
        before=before,
        metadata={"line_id": str(line.pk)},
    )
    return line


@transaction.atomic
def update_draft_delivery_line(
    line: SalesDeliveryLine, *, quantity, actor=None, reason="", notes=""
) -> SalesDeliveryLine:
    line = (
        SalesDeliveryLine.objects.select_for_update()
        .select_related("sales_delivery")
        .get(pk=line.pk)
    )
    _assert_draft(line.sales_delivery)
    before = model_snapshot(line)
    qty = _quantity(quantity)
    if qty <= 0:
        raise ValidationError({"quantity": "Delivery quantity must be greater than zero."})
    line.quantity = qty
    line.notes = str(notes or "").strip()
    line.full_clean()
    line.save(update_fields=("quantity", "notes", "updated_at"))
    _audit(
        line, action="sales.salesdeliveryline.updated", actor=actor, reason=reason, before=before
    )
    return line


@transaction.atomic
def remove_draft_delivery_line(line: SalesDeliveryLine, *, actor=None, reason=""):
    line = (
        SalesDeliveryLine.objects.select_for_update()
        .select_related("sales_delivery")
        .get(pk=line.pk)
    )
    _assert_draft(line.sales_delivery)
    before = model_snapshot(line)
    delivery = line.sales_delivery
    line.delete()
    _audit(
        delivery,
        action="sales.salesdelivery.line_removed",
        actor=actor,
        reason=reason,
        before=model_snapshot(delivery),
        metadata={"deleted_line": before},
    )


@transaction.atomic
def update_draft_delivery(
    delivery: SalesDelivery, *, actor=None, reason="", **values
) -> SalesDelivery:
    delivery = (
        SalesDelivery.objects.select_for_update().select_related("customer").get(pk=delivery.pk)
    )
    _assert_draft(delivery)
    before = model_snapshot(delivery)
    if "delivery_date" in values and values["delivery_date"] != delivery.delivery_date:
        raise ValidationError(
            {"delivery_date": "Delivery date is immutable after number allocation."}
        )
    for field in ("destination_snapshot", "expedition_reference", "notes"):
        if field in values:
            setattr(delivery, field, str(values[field] or "").strip())
    delivery.full_clean()
    delivery.save()
    _audit(
        delivery, action="sales.salesdelivery.updated", actor=actor, reason=reason, before=before
    )
    return delivery


def _posted_quantity(source_line_ids):
    rows = (
        SalesDeliveryLine.objects.filter(
            source_sales_order_line_id__in=source_line_ids,
            sales_delivery__state=SalesDeliveryState.POSTED,
        )
        .values("source_sales_order_line_id")
        .annotate(total=Sum("quantity"))
    )
    return {row["source_sales_order_line_id"]: row["total"] for row in rows}


@transaction.atomic
def post_delivery(delivery: SalesDelivery, *, actor=None, idempotency_key="") -> SalesDelivery:
    delivery = (
        SalesDelivery.objects.select_for_update().select_related("customer").get(pk=delivery.pk)
    )
    if delivery.state == SalesDeliveryState.POSTED:
        return delivery
    _assert_draft(delivery)
    lines = list(
        delivery.lines.select_related("source_sales_order_line__sales_order").order_by(
            "line_number"
        )
    )
    if not lines:
        raise ValidationError("A Sales Delivery requires at least one line before posting.")
    source_ids = sorted({line.source_sales_order_line_id for line in lines}, key=str)
    sources = {
        source.pk: source
        for source in SalesOrderLine.objects.select_for_update()
        .select_related("sales_order")
        .filter(pk__in=source_ids)
    }
    posted = _posted_quantity(source_ids)
    requested: dict[object, Decimal] = {}
    for line in lines:
        source = sources[line.source_sales_order_line_id]
        _validate_source_line(delivery, source)
        requested[source.pk] = requested.get(source.pk, Decimal("0")) + line.quantity
    for source_id, quantity in requested.items():
        remaining = sources[source_id].quantity - (posted.get(source_id) or Decimal("0"))
        if quantity > remaining:
            raise ValidationError(
                "Delivery quantity exceeds remaining quantity for Sales Order line "
                f"{sources[source_id].line_number}."
            )
    if idempotency_key:
        claim = claim_idempotency(
            namespace="sales.delivery.post",
            key=idempotency_key,
            payload={"delivery_id": str(delivery.pk)},
            actor=actor,
        )
        if not claim.is_new:
            if claim.record.status == IdempotencyStatus.COMPLETED:
                return delivery
            raise ValidationError("A prior delivery posting request is still in progress.")
    else:
        claim = None
    before = model_snapshot(delivery)
    delivery.state = SalesDeliveryState.POSTED
    delivery.posted_at = timezone.now()
    delivery.posted_by = actor
    delivery.full_clean()
    delivery.save(update_fields=("state", "posted_at", "posted_by", "updated_at"))
    _audit(
        delivery,
        action="sales.salesdelivery.posted",
        actor=actor,
        before=before,
        metadata={"warehouse_candidate_count": len(lines)},
    )
    if claim:
        complete_idempotency(
            claim.record.pk,
            result_reference=str(delivery.pk),
            response={"sales_delivery_id": str(delivery.pk)},
        )
    return delivery


@transaction.atomic
def cancel_delivery(delivery: SalesDelivery, *, actor=None, reason="") -> SalesDelivery:
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Cancellation reason is required."})
    delivery = SalesDelivery.objects.select_for_update().get(pk=delivery.pk)
    if delivery.state not in {SalesDeliveryState.DRAFT, SalesDeliveryState.POSTED}:
        raise ValidationError("Only DRAFT or POSTED Sales Deliveries can be cancelled.")
    before = model_snapshot(delivery)
    delivery.state = SalesDeliveryState.CANCELLED
    delivery.cancelled_at = timezone.now()
    delivery.cancelled_by = actor
    delivery.full_clean()
    delivery.save(update_fields=("state", "cancelled_at", "cancelled_by", "updated_at"))
    _audit(
        delivery,
        action="sales.salesdelivery.cancelled",
        actor=actor,
        reason=reason,
        before=before,
        metadata={
            "warehouse_correction_required": before.get("state") == SalesDeliveryState.POSTED
        },
    )
    return delivery
