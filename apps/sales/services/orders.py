from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import Item
from apps.core.models import IdempotencyStatus
from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.core.services.numbering import allocate_document_number
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.organizations.models import BusinessUnit, LegalEntity
from apps.partners.models import BusinessPartner, PartnerRoleType
from apps.sales.models import DiscountType, SalesOrder, SalesOrderLine, SalesOrderState
from apps.sales.services.credit import record_sales_order_credit_control

SALES_ORDER_DOCUMENT_TYPE = "SALES_ORDER"
MONEY_QUANTUM = Decimal("0.01")
HUNDRED = Decimal("100")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _text(value) -> str:
    return " ".join(str(value or "").split())


def _audit(instance, *, action, actor=None, reason="", before=None, after=None, metadata=None):
    after = model_snapshot(instance) if after is None else after
    record_audit_event(
        action=action,
        target_type=instance._meta.label_lower,
        target_id=instance.pk,
        actor=actor,
        source="sales.service",
        reason=reason,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after)
        if before and after
        else sorted(after or {}),
        metadata=metadata or {},
    )


def _is_effective(instance, business_date) -> bool:
    return instance.effective_from <= business_date and (
        instance.effective_to is None or instance.effective_to >= business_date
    )


def _is_currently_active(instance, business_date) -> bool:
    return business_date < timezone.localdate() or instance.is_active


def _validate_customer(customer, *, legal_entity, document_date):
    if customer.legal_entity_id != legal_entity.id:
        raise ValidationError({"customer": "Customer must belong to the Sales Order legal entity."})
    if not _is_effective(customer, document_date) or not _is_currently_active(
        customer, document_date
    ):
        raise ValidationError({"customer": "Customer is not effective for the Sales Order date."})
    role = customer.roles.filter(
        role_type=PartnerRoleType.CUSTOMER,
        effective_from__lte=document_date,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=document_date))
    if document_date >= timezone.localdate():
        role = role.filter(is_active=True)
    if not role.exists():
        raise ValidationError({"customer": "Customer requires an effective CUSTOMER role."})


def _validate_business_unit(business_unit, *, legal_entity, document_date):
    if business_unit is None:
        return
    if business_unit.legal_entity_id != legal_entity.id:
        raise ValidationError(
            {"business_unit": "Business Unit must belong to the Sales Order entity."}
        )
    if not _is_effective(business_unit, document_date) or not _is_currently_active(
        business_unit, document_date
    ):
        raise ValidationError(
            {"business_unit": "Business Unit is not effective for the Sales Order date."}
        )


def _validate_item(item, *, legal_entity, document_date):
    if item.legal_entity_id != legal_entity.id:
        raise ValidationError({"item": "Item must belong to the Sales Order legal entity."})
    if not _is_effective(item, document_date) or not _is_currently_active(item, document_date):
        raise ValidationError({"item": "Item is not effective for the Sales Order date."})
    if not item.sales_eligible:
        raise ValidationError({"item": "Item is not sales eligible."})
    if not _is_effective(item.uom, document_date) or not _is_currently_active(
        item.uom, document_date
    ):
        raise ValidationError({"item": "Item UOM is not effective for the Sales Order date."})


def _normalize_line_values(values):
    normalized = values.copy()
    for field in ("quantity", "unit_price", "discount_value", "tax_rate"):
        if field in normalized:
            normalized[field] = Decimal(str(normalized[field] or 0))
    for field in ("description", "description_snapshot", "notes"):
        if field in normalized:
            normalized[field] = str(normalized[field] or "").strip()
    if "discount_type" in normalized:
        normalized["discount_type"] = str(normalized["discount_type"]).upper()
    return normalized


def _calculate_line(line: SalesOrderLine) -> None:
    if line.quantity <= 0:
        raise ValidationError({"quantity": "Quantity must be greater than zero."})
    if line.unit_price < 0:
        raise ValidationError({"unit_price": "Unit price cannot be negative."})
    if line.discount_value < 0:
        raise ValidationError({"discount_value": "Discount cannot be negative."})
    if line.tax_rate < 0:
        raise ValidationError({"tax_rate": "Tax rate cannot be negative."})
    if line.discount_type not in DiscountType.values:
        raise ValidationError({"discount_type": "Unsupported discount type."})

    line.line_amount = _money(line.quantity * line.unit_price)
    if line.discount_type == DiscountType.PERCENT:
        if line.discount_value > HUNDRED:
            raise ValidationError({"discount_value": "Percentage discount cannot exceed 100."})
        line.line_discount_amount = _money(line.line_amount * line.discount_value / HUNDRED)
    else:
        line.line_discount_amount = _money(line.discount_value)
    if line.line_discount_amount > line.line_amount:
        raise ValidationError({"discount_value": "Discount cannot exceed the line amount."})
    line.line_tax_base = _money(line.line_amount - line.line_discount_amount)
    line.line_tax_amount = _money(line.line_tax_base * line.tax_rate / HUNDRED)
    line.line_total = _money(line.line_tax_base + line.line_tax_amount)


def _apply_line_snapshots(line: SalesOrderLine, *, item: Item, values):
    description = values.get("description", values.get("description_snapshot", ""))
    line.item = item
    line.item_code_snapshot = item.code
    line.item_name_snapshot = item.name
    line.description_snapshot = _text(description) or item.name
    line.uom_code_snapshot = item.uom.code
    line.tax_classification_snapshot = item.tax_classification


def _refresh_order_totals(order: SalesOrder) -> None:
    lines = list(order.lines.all())
    order.subtotal = _money(sum((line.line_amount for line in lines), Decimal("0")))
    order.discount_total = _money(sum((line.line_discount_amount for line in lines), Decimal("0")))
    order.tax_total = _money(sum((line.line_tax_amount for line in lines), Decimal("0")))
    order.freight_amount = _money(order.freight_amount)
    order.grand_total = _money(
        order.subtotal - order.discount_total + order.tax_total + order.freight_amount
    )


def _refresh_customer_snapshots(order: SalesOrder) -> None:
    order.customer_code_snapshot = order.customer.code
    order.customer_name_snapshot = order.customer.display_name
    order.customer_legal_name_snapshot = order.customer.legal_name


def _claim_or_replay(*, namespace, key, payload, actor):
    if not key:
        return None, None
    claim = claim_idempotency(namespace=namespace, key=key, payload=payload, actor=actor)
    if claim.is_new:
        return claim, None
    if claim.record.status != IdempotencyStatus.COMPLETED or not claim.record.result_reference:
        raise ValidationError("A prior request with this idempotency key is still in progress.")
    return claim, SalesOrder.objects.get(pk=claim.record.result_reference)


def _draft_values_payload(values, lines):
    return {
        "legal_entity": str(values["legal_entity"].pk),
        "customer": str(values["customer"].pk),
        "document_date": values["document_date"].isoformat(),
        "customer_po_reference": _text(values.get("customer_po_reference")),
        "business_unit": str(values["business_unit"].pk) if values.get("business_unit") else "",
        "requested_delivery_date": (
            values["requested_delivery_date"].isoformat()
            if values.get("requested_delivery_date")
            else ""
        ),
        "currency": _text(values.get("currency", "IDR")).upper(),
        "freight_amount": str(values.get("freight_amount", 0)),
        "lines": [
            {
                key: str(value.pk) if key == "item" else str(value)
                for key, value in sorted(line.items())
            }
            for line in lines
        ],
    }


def _assert_draft(order: SalesOrder):
    if order.state != SalesOrderState.DRAFT:
        raise ValidationError("Only DRAFT Sales Orders can be edited.")


@transaction.atomic
def create_draft_sales_order(*, actor=None, idempotency_key="", lines=None, **values) -> SalesOrder:
    """Allocate a configured Sales Order number and persist a draft without side effects."""

    lines = lines or []
    entity = LegalEntity.objects.select_for_update().get(pk=values["legal_entity"].pk)
    customer = BusinessPartner.objects.prefetch_related("roles").get(pk=values["customer"].pk)
    document_date = values["document_date"]
    business_unit = values.get("business_unit")
    if business_unit:
        business_unit = BusinessUnit.objects.get(pk=business_unit.pk)
    _validate_customer(customer, legal_entity=entity, document_date=document_date)
    _validate_business_unit(business_unit, legal_entity=entity, document_date=document_date)
    payload = _draft_values_payload({**values, "legal_entity": entity, "customer": customer}, lines)
    claim, replay = _claim_or_replay(
        namespace="sales.create_draft",
        key=idempotency_key,
        payload=payload,
        actor=actor,
    )
    if replay:
        return replay

    allocation = allocate_document_number(
        entity,
        SALES_ORDER_DOCUMENT_TYPE,
        business_date=document_date,
        request_key=f"sales-order:{idempotency_key}" if idempotency_key else "",
        actor=actor,
    )
    order = SalesOrder(
        legal_entity=entity,
        document_allocation=allocation,
        document_number=allocation.number,
        document_date=document_date,
        customer=customer,
        customer_po_reference=_text(values.get("customer_po_reference")),
        business_unit=business_unit,
        requested_delivery_date=values.get("requested_delivery_date"),
        currency=_text(values.get("currency", entity.reporting_currency)).upper(),
        notes=str(values.get("notes", "") or "").strip(),
        freight_amount=_money(values.get("freight_amount", 0)),
        created_by=actor,
    )
    if len(order.currency) != 3:
        raise ValidationError({"currency": "Currency must be a three-letter code."})
    _refresh_customer_snapshots(order)
    order.full_clean()
    order.save()
    for position, line_values in enumerate(lines, start=1):
        _add_line_locked(order, line_number=position, **line_values)
    _refresh_order_totals(order)
    order.full_clean()
    order.save()
    _audit(order, action="sales.salesorder.created", actor=actor)
    if claim:
        complete_idempotency(
            claim.record.pk,
            result_reference=str(order.pk),
            response={"sales_order_id": str(order.pk), "document_number": order.document_number},
        )
    return order


def _add_line_locked(order: SalesOrder, *, line_number=None, actor=None, reason="", **values):
    _assert_draft(order)
    values = _normalize_line_values(values)
    item = Item.objects.select_related("uom").get(pk=values["item"].pk)
    _validate_item(item, legal_entity=order.legal_entity, document_date=order.document_date)
    if line_number is None:
        last = (
            order.lines.order_by("-line_number").values_list("line_number", flat=True).first() or 0
        )
        line_number = last + 1
    line = SalesOrderLine(
        sales_order=order,
        line_number=line_number,
        quantity=values["quantity"],
        unit_price=values["unit_price"],
        discount_type=values.get("discount_type", DiscountType.AMOUNT),
        discount_value=values.get("discount_value", Decimal("0")),
        tax_rate=values.get("tax_rate", Decimal("0")),
        notes=values.get("notes", ""),
    )
    _apply_line_snapshots(line, item=item, values=values)
    _calculate_line(line)
    line.full_clean()
    line.save()
    _audit(line, action="sales.salesorderline.added", actor=actor, reason=reason)
    return line


@transaction.atomic
def add_draft_line(order, *, actor=None, reason="", **values) -> SalesOrderLine:
    locked = SalesOrder.objects.select_for_update().get(pk=order.pk)
    before_order = model_snapshot(locked)
    line = _add_line_locked(locked, actor=actor, reason=reason, **values)
    _refresh_order_totals(locked)
    locked.save()
    _audit(
        locked,
        action="sales.salesorder.totals_recalculated",
        actor=actor,
        reason=reason,
        before=before_order,
    )
    return line


@transaction.atomic
def update_draft_line(line, *, actor=None, reason="", **values) -> SalesOrderLine:
    locked = (
        SalesOrderLine.objects.select_related("sales_order").select_for_update().get(pk=line.pk)
    )
    order = SalesOrder.objects.select_for_update().get(pk=locked.sales_order_id)
    _assert_draft(order)
    before_line = model_snapshot(locked)
    before_order = model_snapshot(order)
    values = _normalize_line_values(values)
    item = Item.objects.select_related("uom").get(pk=values.get("item", locked.item).pk)
    _validate_item(item, legal_entity=order.legal_entity, document_date=order.document_date)
    for field in ("quantity", "unit_price", "discount_type", "discount_value", "tax_rate", "notes"):
        if field in values:
            setattr(locked, field, values[field])
    _apply_line_snapshots(locked, item=item, values=values)
    _calculate_line(locked)
    locked.full_clean()
    locked.save()
    _audit(
        locked,
        action="sales.salesorderline.updated",
        actor=actor,
        reason=reason,
        before=before_line,
    )
    _refresh_order_totals(order)
    order.save()
    _audit(
        order,
        action="sales.salesorder.totals_recalculated",
        actor=actor,
        reason=reason,
        before=before_order,
    )
    return locked


@transaction.atomic
def remove_draft_line(line, *, actor=None, reason="") -> None:
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to remove a Sales Order line."})
    locked = (
        SalesOrderLine.objects.select_related("sales_order").select_for_update().get(pk=line.pk)
    )
    order = SalesOrder.objects.select_for_update().get(pk=locked.sales_order_id)
    _assert_draft(order)
    before_line = model_snapshot(locked)
    before_order = model_snapshot(order)
    line_id = locked.pk
    locked.delete()
    record_audit_event(
        action="sales.salesorderline.removed",
        target_type="sales.salesorderline",
        target_id=line_id,
        actor=actor,
        source="sales.service",
        reason=reason,
        before_state=before_line,
        after_state=None,
        changed_fields=sorted(before_line),
    )
    _refresh_order_totals(order)
    order.save()
    _audit(
        order,
        action="sales.salesorder.totals_recalculated",
        actor=actor,
        reason=reason,
        before=before_order,
    )


@transaction.atomic
def update_draft_sales_order(order, *, actor=None, reason="", **values) -> SalesOrder:
    locked = SalesOrder.objects.select_for_update().get(pk=order.pk)
    _assert_draft(locked)
    before = model_snapshot(locked)
    if "document_date" in values and values["document_date"] != locked.document_date:
        raise ValidationError(
            {"document_date": "Document date is immutable after Sales Order number allocation."}
        )
    document_date = values.get("document_date", locked.document_date)
    customer = BusinessPartner.objects.prefetch_related("roles").get(
        pk=values.get("customer", locked.customer).pk
    )
    business_unit_value = values.get("business_unit", locked.business_unit)
    business_unit = (
        BusinessUnit.objects.get(pk=business_unit_value.pk)
        if business_unit_value is not None
        else None
    )
    _validate_customer(customer, legal_entity=locked.legal_entity, document_date=document_date)
    _validate_business_unit(
        business_unit, legal_entity=locked.legal_entity, document_date=document_date
    )
    for field in (
        "document_date",
        "customer_po_reference",
        "requested_delivery_date",
        "currency",
        "notes",
        "freight_amount",
    ):
        if field in values:
            setattr(locked, field, values[field])
    locked.customer = customer
    locked.business_unit = business_unit
    locked.customer_po_reference = _text(locked.customer_po_reference)
    locked.currency = _text(locked.currency).upper()
    locked.notes = str(locked.notes or "").strip()
    locked.freight_amount = _money(locked.freight_amount)
    if len(locked.currency) != 3:
        raise ValidationError({"currency": "Currency must be a three-letter code."})
    for line in locked.lines.select_related("item", "item__uom"):
        _validate_item(
            line.item, legal_entity=locked.legal_entity, document_date=locked.document_date
        )
    _refresh_customer_snapshots(locked)
    _refresh_order_totals(locked)
    locked.full_clean()
    locked.save()
    _audit(locked, action="sales.salesorder.updated", actor=actor, reason=reason, before=before)
    return locked


@transaction.atomic
def confirm_sales_order(order, *, actor=None, idempotency_key="") -> SalesOrder:
    locked = SalesOrder.objects.select_for_update().select_related("customer").get(pk=order.pk)
    claim, replay = _claim_or_replay(
        namespace="sales.confirm",
        key=idempotency_key,
        payload={"sales_order_id": str(locked.pk), "action": "confirm"},
        actor=actor,
    )
    if replay:
        return replay
    if locked.state != SalesOrderState.DRAFT:
        raise ValidationError("Only DRAFT Sales Orders can be confirmed.")
    lines = list(locked.lines.select_for_update().select_related("item", "item__uom"))
    if not lines:
        raise ValidationError("A Sales Order requires at least one line before confirmation.")
    _validate_customer(
        locked.customer, legal_entity=locked.legal_entity, document_date=locked.document_date
    )
    _validate_business_unit(
        locked.business_unit,
        legal_entity=locked.legal_entity,
        document_date=locked.document_date,
    )
    before = model_snapshot(locked)
    _refresh_customer_snapshots(locked)
    for line in lines:
        _validate_item(
            line.item, legal_entity=locked.legal_entity, document_date=locked.document_date
        )
        line.item_code_snapshot = line.item.code
        line.item_name_snapshot = line.item.name
        line.uom_code_snapshot = line.item.uom.code
        line.tax_classification_snapshot = line.item.tax_classification
        _calculate_line(line)
        line.full_clean()
        line.save()
    _refresh_order_totals(locked)
    locked.state = SalesOrderState.CONFIRMED
    locked.confirmed_by = actor
    locked.confirmed_at = timezone.now()
    locked.full_clean()
    locked.save()
    _audit(locked, action="sales.salesorder.confirmed", actor=actor, before=before)
    credit_control = record_sales_order_credit_control(locked, actor=actor)
    if credit_control.status == "HELD":
        credit_before = model_snapshot(locked)
        locked.state = SalesOrderState.ON_HOLD
        locked.save(update_fields=("state", "updated_at"))
        _audit(
            locked,
            action="sales.salesorder.credit_held",
            actor=actor,
            reason="Authoritative Finance exposure exceeds the configured credit limit.",
            before=credit_before,
        )
    if claim:
        complete_idempotency(
            claim.record.pk,
            result_reference=str(locked.pk),
            response={"sales_order_id": str(locked.pk), "state": locked.state},
        )
    return locked


@transaction.atomic
def hold_sales_order(order, *, actor=None, reason="") -> SalesOrder:
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to place a Sales Order on hold."})
    locked = SalesOrder.objects.select_for_update().get(pk=order.pk)
    if locked.state != SalesOrderState.CONFIRMED:
        raise ValidationError("Only CONFIRMED Sales Orders can be placed on hold.")
    before = model_snapshot(locked)
    locked.state = SalesOrderState.ON_HOLD
    locked.save(update_fields=("state", "updated_at"))
    _audit(locked, action="sales.salesorder.held", actor=actor, reason=reason, before=before)
    return locked


@transaction.atomic
def release_sales_order(order, *, actor=None, reason="") -> SalesOrder:
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to release a Sales Order hold."})
    locked = SalesOrder.objects.select_for_update().get(pk=order.pk)
    if locked.state != SalesOrderState.ON_HOLD:
        raise ValidationError("Only ON_HOLD Sales Orders can be released.")
    before = model_snapshot(locked)
    locked.state = SalesOrderState.CONFIRMED
    locked.save(update_fields=("state", "updated_at"))
    _audit(locked, action="sales.salesorder.released", actor=actor, reason=reason, before=before)
    return locked


@transaction.atomic
def cancel_sales_order(order, *, actor=None, reason="") -> SalesOrder:
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to cancel a Sales Order."})
    locked = SalesOrder.objects.select_for_update().get(pk=order.pk)
    if locked.state not in {
        SalesOrderState.DRAFT,
        SalesOrderState.CONFIRMED,
        SalesOrderState.ON_HOLD,
    }:
        raise ValidationError("This Sales Order cannot be cancelled from its current state.")
    before = model_snapshot(locked)
    locked.state = SalesOrderState.CANCELLED
    locked.cancelled_by = actor
    locked.cancelled_at = timezone.now()
    locked.save(update_fields=("state", "cancelled_by", "cancelled_at", "updated_at"))
    _audit(locked, action="sales.salesorder.cancelled", actor=actor, reason=reason, before=before)
    return locked
