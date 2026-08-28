from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.omnichannel.models import (
    OmniException,
    OmniExceptionState,
    OmniMappingStatus,
    OmniOperationalStatus,
    OmniOrderLine,
    OmniPacking,
    OmniPackingLine,
    OmniPackingState,
)
from apps.warehouse.models import MovementDirection, MovementType
from apps.warehouse.services import post_stock_movement


def _positive(value):
    try:
        value = Decimal(str(value))
    except Exception as error:
        raise ValidationError("Packing quantity is invalid.") from error
    if value <= 0:
        raise ValidationError("Packing quantity must be positive.")
    return value


def _require_permission(actor, codename):
    if (
        actor is not None
        and not actor.is_superuser
        and not actor.has_perm(f"omnichannel.{codename}")
    ):
        raise PermissionDenied(f"Omnichannel permission required: {codename}")


def _packed_quantity(line):
    return OmniPackingLine.objects.filter(
        order_line=line, warehouse_movement__isnull=False, packing__state=OmniPackingState.POSTED
    ).aggregate(total=Sum("packed_quantity"))["total"] or Decimal("0")


@transaction.atomic
def create_packing(*, legal_entity, store, warehouse, packing_date, lines, actor=None, notes=""):
    if store.legal_entity_id != legal_entity.pk or not store.is_active:
        raise ValidationError("Store must be active and belong to the legal entity.")
    if warehouse.legal_entity_id != legal_entity.pk or not warehouse.is_active:
        raise ValidationError("Warehouse must be active and belong to the legal entity.")
    normalized_lines = []
    for entry in lines:
        order_line = (
            OmniOrderLine.objects.select_for_update()
            .select_related("order", "item")
            .get(
                pk=entry["order_line"].pk
                if hasattr(entry["order_line"], "pk")
                else entry["order_line"]
            )
        )
        quantity = _positive(entry["quantity"])
        if (
            order_line.order.legal_entity_id != legal_entity.pk
            or order_line.order.store_id != store.pk
        ):
            raise ValidationError("Packing line is outside the selected legal entity or Store.")
        if order_line.item_id is None or order_line.mapping_status != OmniMappingStatus.READY:
            raise ValidationError("Only mapped canonical Items can be packed.")
        if order_line.order.normalized_status in {
            OmniOperationalStatus.CANCELLED,
            OmniOperationalStatus.RETURNED,
            OmniOperationalStatus.REFUNDED,
        }:
            raise ValidationError("Cancelled or returned orders cannot be packed.")
        remaining = order_line.internal_quantity - _packed_quantity(order_line)
        if quantity > remaining:
            raise ValidationError("Packing exceeds the remaining mapped demand.")
        normalized_lines.append((order_line, quantity))
    if not normalized_lines:
        raise ValidationError("Packing must contain at least one line.")
    packing = OmniPacking.objects.create(
        legal_entity=legal_entity,
        store=store,
        marketplace=store.channel,
        warehouse=warehouse,
        packing_date=packing_date,
        created_by=actor,
        notes=str(notes or "").strip(),
    )
    for sequence, (order_line, quantity) in enumerate(normalized_lines, start=1):
        line_id = uuid4()
        OmniPackingLine.objects.create(
            id=line_id,
            packing=packing,
            order=order_line.order,
            order_line=order_line,
            item=order_line.item,
            item_code_snapshot=order_line.item.code,
            item_name_snapshot=order_line.item.name,
            requested_quantity=quantity,
            packed_quantity=quantity,
            source_key=f"OMNI_PACK|{line_id}",
            sequence=sequence,
        )
    record_audit_event(
        action="omnichannel.packing.created",
        target_type=packing._meta.label_lower,
        target_id=packing.pk,
        actor=actor,
        source="omnichannel.service",
    )
    return packing


@transaction.atomic
def post_packing(packing, *, actor=None, idempotency_key=""):
    _require_permission(actor, "post_omnipacking")
    packing = (
        OmniPacking.objects.select_for_update()
        .select_related("legal_entity", "warehouse", "store")
        .get(pk=packing.pk)
    )
    if packing.state == OmniPackingState.POSTED:
        return packing
    if packing.state != OmniPackingState.DRAFT:
        raise ValidationError("Only DRAFT packing documents can be posted.")
    key = idempotency_key or f"OMNI_PACKING|{packing.pk}"
    claim = claim_idempotency(
        namespace="omnichannel.packing.post",
        key=key,
        payload={"packing": str(packing.pk)},
        actor=actor,
    )
    if not claim.is_new:
        if claim.record.result_reference:
            return OmniPacking.objects.get(pk=claim.record.result_reference)
        raise ValidationError("The same packing request is already in progress.")
    lines = list(
        packing.lines.select_for_update().select_related("order_line", "item").order_by("sequence")
    )
    if not lines:
        raise ValidationError("Packing must contain at least one line.")
    for line in lines:
        order_line = OmniOrderLine.objects.select_for_update().get(pk=line.order_line_id)
        remaining = order_line.internal_quantity - _packed_quantity(order_line)
        if line.packed_quantity > remaining:
            raise ValidationError("Packing exceeds the remaining mapped demand.")
        if line.warehouse_movement_id:
            continue
        movement = post_stock_movement(
            legal_entity=packing.legal_entity,
            warehouse=packing.warehouse,
            item=line.item,
            direction=MovementDirection.OUT,
            movement_type=MovementType.OMNI_PACKING,
            quantity=line.packed_quantity,
            source_module="omnichannel",
            source_type="OMNI_PACKING",
            source_document_id=packing.pk,
            source_line_id=line.pk,
            source_key=line.source_key,
            transaction_date=packing.packing_date,
            actor=actor,
            idempotency_key=f"{line.source_key}|POST",
        )
        line.warehouse_movement = movement
        line.save(update_fields=("warehouse_movement", "updated_at"))
    packing.state = OmniPackingState.POSTED
    packing.posted_by = actor
    packing.posted_at = timezone.now()
    packing.idempotency_key = key
    packing.save(update_fields=("state", "posted_by", "posted_at", "idempotency_key", "updated_at"))
    record_audit_event(
        action="omnichannel.packing.posted",
        target_type=packing._meta.label_lower,
        target_id=packing.pk,
        actor=actor,
        source="omnichannel.service",
        idempotency_key=key,
        metadata={"movement_ids": [str(line.warehouse_movement_id) for line in lines]},
    )
    complete_idempotency(claim.record.pk, result_reference=str(packing.pk))
    return packing


def mark_cancelled_after_packing(order, *, actor=None):
    """Record the required review signal without reversing Warehouse history."""
    if not order.packing_lines.filter(warehouse_movement__isnull=False).exists():
        return None
    return OmniException.objects.create(
        legal_entity=order.legal_entity,
        order=order,
        code="CANCELLED_AFTER_PACKING",
        state=OmniExceptionState.OPEN,
        message="Source order was cancelled after physical Warehouse OUT; review required.",
        metadata={"order": str(order.pk)},
    )
