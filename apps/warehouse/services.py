from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import IdempotencyStatus
from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.production.models import ProductionHandoverState
from apps.purchasing.models import WorkOrderState, WorkOrderType
from apps.warehouse.models import (
    InventoryValuationState,
    MovementDirection,
    MovementType,
    StockMovement,
    ValuationStatus,
    WarehouseDocumentState,
    WarehouseMaterialIssue,
    WarehouseMaterialIssueLine,
    WarehousePostingSequence,
    WarehouseReceipt,
    WarehouseReceiptLine,
)


def _audit(obj, action, actor=None, *, reason="", key=""):
    record_audit_event(
        action=action,
        target_type=obj._meta.label_lower,
        target_id=obj.pk,
        actor=actor,
        source="warehouse.service",
        reason=reason,
        idempotency_key=key,
    )


def _claim(namespace, key, payload, actor):
    if not key:
        raise ValidationError("Idempotency key is required.")
    return claim_idempotency(namespace=namespace, key=key, payload=payload, actor=actor)


def _replay(claim, klass):
    if claim.is_new:
        return None
    if claim.record.status == IdempotencyStatus.COMPLETED:
        return klass.objects.get(pk=claim.record.result_reference)
    raise ValidationError("The same request is already in progress.")


def _positive(value, field="quantity"):
    value = Decimal(str(value))
    if value <= 0:
        raise ValidationError({field: "Quantity must be positive."})
    return value


def _validate_warehouse(warehouse, entity):
    if warehouse.legal_entity_id != entity.pk or not warehouse.is_active:
        raise ValidationError("Warehouse must be active and belong to the legal entity.")


def _next_sequence():
    sequence, _ = WarehousePostingSequence.objects.select_for_update().get_or_create(singleton=True)
    sequence.last_sequence += 1
    sequence.save(update_fields=("last_sequence",))
    return sequence.last_sequence


def _state(warehouse, item, entity):
    state, _ = InventoryValuationState.objects.select_for_update().get_or_create(
        legal_entity=entity,
        warehouse=warehouse,
        item=item,
        defaults={"quantity_on_hand": Decimal("0"), "inventory_value": Decimal("0")},
    )
    return state


def _post_movement(
    *,
    entity,
    warehouse,
    item,
    direction,
    movement_type,
    quantity,
    source_module,
    source_type,
    source_document_id,
    source_line_id,
    source_key,
    transaction_date,
    actor,
    unit_cost=None,
    total_value=None,
    valuation_status=ValuationStatus.READY,
    reversal_of=None,
    notes="",
    bypass_pending_valuation=False,
):
    quantity = _positive(quantity)
    # The singleton sequence row is also the PostgreSQL serialization point
    # for valuation updates and first-use balance creation.
    sequence = _next_sequence()
    state = _state(warehouse, item, entity)
    if direction == MovementDirection.OUT:
        if state.quantity_on_hand < quantity:
            raise ValidationError("Insufficient physical stock.")
        if not bypass_pending_valuation and (
            state.valuation_status == ValuationStatus.PENDING_VALUATION
            or state.average_unit_cost is None
        ):
            raise ValidationError("Stock valuation is pending; OUT is blocked.")
        unit_cost = state.average_unit_cost if not bypass_pending_valuation else unit_cost
        total_value = quantity * unit_cost if unit_cost is not None else None
        state.quantity_on_hand -= quantity
        state.inventory_value = (
            None if total_value is None else (state.inventory_value or Decimal("0")) - total_value
        )
    else:
        state.quantity_on_hand += quantity
        if valuation_status == ValuationStatus.READY and total_value is not None:
            state.inventory_value = (state.inventory_value or Decimal("0")) + total_value
        else:
            state.inventory_value = None
            state.average_unit_cost = None
            state.valuation_status = ValuationStatus.PENDING_VALUATION
    if (
        direction == MovementDirection.IN
        and state.valuation_status != ValuationStatus.PENDING_VALUATION
    ):
        state.average_unit_cost = (
            (state.inventory_value / state.quantity_on_hand) if state.quantity_on_hand else None
        )
    elif direction == MovementDirection.OUT:
        state.average_unit_cost = (
            (state.inventory_value / state.quantity_on_hand) if state.quantity_on_hand else None
        )
    state.last_movement_sequence = sequence
    state.save(
        update_fields=(
            "quantity_on_hand",
            "inventory_value",
            "average_unit_cost",
            "valuation_status",
            "last_movement_sequence",
            "updated_at",
        )
    )
    return StockMovement.objects.create(
        legal_entity=entity,
        warehouse=warehouse,
        item=item,
        direction=direction,
        movement_type=movement_type,
        quantity=quantity,
        uom_code_snapshot=item.uom.code,
        unit_cost=unit_cost,
        total_value=total_value,
        valuation_status=valuation_status,
        source_module=source_module,
        source_type=source_type,
        source_document_id=str(source_document_id),
        source_line_id=str(source_line_id),
        source_key=source_key,
        transaction_date=transaction_date,
        posting_sequence=sequence,
        posted_at=timezone.now(),
        state=WarehouseDocumentState.POSTED,
        created_by=actor,
        posted_by=actor,
        reversal_of=reversal_of,
        notes=notes,
    )


@transaction.atomic
def post_stock_movement(
    *,
    legal_entity,
    warehouse,
    item,
    direction,
    movement_type,
    quantity,
    source_module,
    source_type,
    source_document_id,
    source_line_id,
    source_key,
    transaction_date,
    actor=None,
    unit_cost=None,
    total_value=None,
    valuation_status=ValuationStatus.READY,
    idempotency_key,
):
    """Warehouse-only primitive for future source adapters."""
    claim = _claim(
        "warehouse.stock_movement.post",
        idempotency_key,
        {
            "source_key": source_key,
            "direction": direction,
            "movement_type": movement_type,
            "quantity": str(quantity),
        },
        actor,
    )
    replay = _replay(claim, StockMovement)
    if replay:
        return replay
    _validate_warehouse(warehouse, legal_entity)
    movement = _post_movement(
        entity=legal_entity,
        warehouse=warehouse,
        item=item,
        direction=direction,
        movement_type=movement_type,
        quantity=quantity,
        source_module=source_module,
        source_type=source_type,
        source_document_id=source_document_id,
        source_line_id=source_line_id,
        source_key=source_key,
        transaction_date=transaction_date,
        actor=actor,
        unit_cost=unit_cost,
        total_value=total_value,
        valuation_status=valuation_status,
    )
    _audit(movement, "warehouse.stock_movement.posted", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(movement.pk))
    return movement


@transaction.atomic
def create_material_issue(*, legal_entity, warehouse, work_order, issue_date, actor=None, notes=""):
    _validate_warehouse(warehouse, legal_entity)
    work_order.refresh_from_db(fields=("legal_entity", "work_order_type", "state"))
    if (
        work_order.legal_entity_id != legal_entity.pk
        or work_order.work_order_type != WorkOrderType.INTERNAL
        or work_order.state != WorkOrderState.APPROVED
    ):
        raise ValidationError("Only APPROVED INTERNAL SPK may be issued.")
    issue = WarehouseMaterialIssue.objects.create(
        legal_entity=legal_entity,
        warehouse=warehouse,
        work_order=work_order,
        issue_date=issue_date,
        notes=str(notes or "").strip(),
        created_by=actor,
    )
    _audit(issue, "warehouse.issue_draft.created", actor)
    return issue


@transaction.atomic
def add_material_issue_line(issue, *, allocation, quantity, actor=None):
    issue = WarehouseMaterialIssue.objects.select_for_update().get(pk=issue.pk)
    if issue.state != WarehouseDocumentState.DRAFT:
        raise ValidationError("Only DRAFT issue can be edited.")
    if allocation.work_order_id != issue.work_order_id:
        raise ValidationError("Allocation must belong to the issue SPK.")
    quantity = _positive(quantity)
    issued = WarehouseMaterialIssueLine.objects.filter(
        allocation=allocation, issue__state=WarehouseDocumentState.POSTED
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    drafted = issue.lines.filter(allocation=allocation).aggregate(total=Sum("quantity"))[
        "total"
    ] or Decimal("0")
    if issued + drafted + quantity > allocation.planned_quantity:
        raise ValidationError("Issue exceeds remaining Production authorization.")
    sequence = issue.lines.order_by("-sequence").values_list("sequence", flat=True).first() or 0
    line = WarehouseMaterialIssueLine.objects.create(
        issue=issue,
        allocation=allocation,
        output=allocation.output,
        item=allocation.material_item,
        source_key=f"PROD_MATERIAL_REQ|{allocation.pk}|{issue.pk}",
        quantity=quantity,
        uom_code_snapshot=allocation.uom_code_snapshot,
        sequence=sequence + 1,
    )
    _audit(line, "warehouse.issue_line.added", actor)
    return line


@transaction.atomic
def post_material_issue(issue, *, actor=None, idempotency_key):
    issue = (
        WarehouseMaterialIssue.objects.select_for_update()
        .select_related("legal_entity", "warehouse", "work_order")
        .get(pk=issue.pk)
    )
    claim = _claim("warehouse.issue.post", idempotency_key, {"issue": str(issue.pk)}, actor)
    replay = _replay(claim, WarehouseMaterialIssue)
    if replay:
        return replay
    if issue.state != WarehouseDocumentState.DRAFT or not issue.lines.exists():
        raise ValidationError("Issue must be a non-empty DRAFT.")
    for line in issue.lines.select_related("allocation", "item"):
        movement = _post_movement(
            entity=issue.legal_entity,
            warehouse=issue.warehouse,
            item=line.item,
            direction=MovementDirection.OUT,
            movement_type=MovementType.PRODUCTION_MATERIAL_ISSUE,
            quantity=line.quantity,
            source_module="production",
            source_type="MATERIAL_REQUEST",
            source_document_id=issue.work_order_id,
            source_line_id=line.output_id,
            source_key=line.source_key,
            transaction_date=issue.issue_date,
            actor=actor,
        )
        line.unit_cost, line.total_value = movement.unit_cost, movement.total_value
        line.save(update_fields=("unit_cost", "total_value", "updated_at"))
    issue.state = WarehouseDocumentState.POSTED
    issue.posted_by, issue.posted_at = actor, timezone.now()
    issue.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    _audit(issue, "warehouse.issue.posted", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(issue.pk))
    return issue


@transaction.atomic
def reverse_material_issue(issue, *, reason, actor=None, idempotency_key):
    if not str(reason).strip():
        raise ValidationError({"reason": "Reason is required."})
    issue = (
        WarehouseMaterialIssue.objects.select_for_update()
        .select_related("legal_entity", "warehouse")
        .get(pk=issue.pk)
    )
    claim = _claim(
        "warehouse.issue.reverse",
        idempotency_key,
        {"issue": str(issue.pk), "reason": str(reason).strip()},
        actor,
    )
    replay = _replay(claim, WarehouseMaterialIssue)
    if replay:
        return replay
    if issue.state != WarehouseDocumentState.POSTED:
        raise ValidationError("Only POSTED issue can be reversed.")
    for line in issue.lines.select_related("item"):
        original_movement = StockMovement.objects.select_for_update().get(
            source_key=line.source_key
        )
        _post_movement(
            entity=issue.legal_entity,
            warehouse=issue.warehouse,
            item=line.item,
            direction=MovementDirection.IN,
            movement_type=MovementType.PRODUCTION_MATERIAL_ISSUE,
            quantity=line.quantity,
            source_module="warehouse",
            source_type="ISSUE_REVERSAL",
            source_document_id=issue.pk,
            source_line_id=line.pk,
            source_key=f"REV|{line.source_key}",
            transaction_date=issue.issue_date,
            actor=actor,
            unit_cost=line.unit_cost,
            total_value=line.total_value,
            reversal_of=original_movement,
        )
    issue.state = WarehouseDocumentState.REVERSED
    issue.save(update_fields=("state", "updated_at"))
    _audit(issue, "warehouse.issue.reversed", actor, reason=reason, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(issue.pk))
    return issue


@transaction.atomic
def create_production_receipt(
    *, legal_entity, warehouse, handover, receipt_date, actor=None, notes=""
):
    _validate_warehouse(warehouse, legal_entity)
    if (
        handover.legal_entity_id != legal_entity.pk
        or handover.state != ProductionHandoverState.READY_FOR_GUDANG
    ):
        raise ValidationError("Handover must be READY_FOR_GUDANG in the same entity.")
    receipt = WarehouseReceipt.objects.create(
        legal_entity=legal_entity,
        warehouse=warehouse,
        work_order=handover.work_order,
        handover=handover,
        receipt_date=receipt_date,
        notes=str(notes or "").strip(),
        created_by=actor,
    )
    _audit(receipt, "warehouse.receipt_draft.created", actor)
    return receipt


@transaction.atomic
def add_production_receipt_line(receipt, *, handover_line, accepted_quantity, actor=None):
    receipt = WarehouseReceipt.objects.select_for_update().get(pk=receipt.pk)
    if receipt.state != WarehouseDocumentState.DRAFT:
        raise ValidationError("Only DRAFT receipt can be edited.")
    if handover_line.handover_id != receipt.handover_id:
        raise ValidationError("Handover line must belong to the receipt handover.")
    quantity = _positive(accepted_quantity, "accepted_quantity")
    accepted = WarehouseReceiptLine.objects.filter(
        handover_line=handover_line, receipt__state=WarehouseDocumentState.POSTED
    ).aggregate(total=Sum("accepted_quantity"))["total"] or Decimal("0")
    drafted = receipt.lines.filter(handover_line=handover_line).aggregate(
        total=Sum("accepted_quantity")
    )["total"] or Decimal("0")
    if accepted + drafted + quantity > handover_line.quantity:
        raise ValidationError("Accepted quantity exceeds remaining Production handover.")
    sequence = receipt.lines.order_by("-sequence").values_list("sequence", flat=True).first() or 0
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=handover_line,
        output=handover_line.output,
        item=handover_line.item,
        source_key=f"PROD_HANDOVER|{handover_line.pk}|{receipt.pk}",
        accepted_quantity=quantity,
        uom_code_snapshot=handover_line.uom_code_snapshot,
        valuation_status=ValuationStatus.PENDING_VALUATION,
        sequence=sequence + 1,
    )
    _audit(line, "warehouse.receipt_line.added", actor)
    return line


@transaction.atomic
def post_production_receipt(receipt, *, actor=None, idempotency_key):
    receipt = (
        WarehouseReceipt.objects.select_for_update()
        .select_related("legal_entity", "warehouse", "handover")
        .get(pk=receipt.pk)
    )
    claim = _claim("warehouse.receipt.post", idempotency_key, {"receipt": str(receipt.pk)}, actor)
    replay = _replay(claim, WarehouseReceipt)
    if replay:
        return replay
    if receipt.state != WarehouseDocumentState.DRAFT or not receipt.lines.exists():
        raise ValidationError("Receipt must be a non-empty DRAFT.")
    for line in receipt.lines.select_related("item"):
        _post_movement(
            entity=receipt.legal_entity,
            warehouse=receipt.warehouse,
            item=line.item,
            direction=MovementDirection.IN,
            movement_type=MovementType.PRODUCTION_FINISHED_GOODS_RECEIPT,
            quantity=line.accepted_quantity,
            source_module="production",
            source_type="PRODUCTION_HANDOVER",
            source_document_id=receipt.handover_id,
            source_line_id=line.handover_line_id,
            source_key=line.source_key,
            transaction_date=receipt.receipt_date,
            actor=actor,
            valuation_status=ValuationStatus.PENDING_VALUATION,
        )
    receipt.state = WarehouseDocumentState.POSTED
    receipt.posted_by, receipt.posted_at = actor, timezone.now()
    receipt.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    _audit(receipt, "warehouse.receipt.posted", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(receipt.pk))
    return receipt


@transaction.atomic
def reverse_production_receipt(receipt, *, reason, actor=None, idempotency_key):
    if not str(reason).strip():
        raise ValidationError({"reason": "Reason is required."})
    receipt = (
        WarehouseReceipt.objects.select_for_update()
        .select_related("legal_entity", "warehouse")
        .get(pk=receipt.pk)
    )
    claim = _claim(
        "warehouse.receipt.reverse",
        idempotency_key,
        {"receipt": str(receipt.pk), "reason": str(reason).strip()},
        actor,
    )
    replay = _replay(claim, WarehouseReceipt)
    if replay:
        return replay
    if receipt.state != WarehouseDocumentState.POSTED:
        raise ValidationError("Only POSTED receipt can be reversed.")
    for line in receipt.lines.select_related("item"):
        original_movement = StockMovement.objects.select_for_update().get(
            source_key=line.source_key
        )
        _post_movement(
            entity=receipt.legal_entity,
            warehouse=receipt.warehouse,
            item=line.item,
            direction=MovementDirection.OUT,
            movement_type=MovementType.PRODUCTION_FINISHED_GOODS_RECEIPT,
            quantity=line.accepted_quantity,
            source_module="warehouse",
            source_type="RECEIPT_REVERSAL",
            source_document_id=receipt.pk,
            source_line_id=line.pk,
            source_key=f"REV|{line.source_key}",
            transaction_date=receipt.receipt_date,
            actor=actor,
            unit_cost=line.unit_cost,
            total_value=line.total_value,
            bypass_pending_valuation=True,
            reversal_of=original_movement,
        )
    receipt.state = WarehouseDocumentState.REVERSED
    receipt.save(update_fields=("state", "updated_at"))
    _audit(receipt, "warehouse.receipt.reversed", actor, reason=reason, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(receipt.pk))
    return receipt


@transaction.atomic
def finalize_production_receipt_valuation(
    receipt_line, *, production_cost_snapshot, actor=None, idempotency_key
):
    if production_cost_snapshot.status != "READY" or production_cost_snapshot.unit_hpp is None:
        raise ValidationError("Production cost snapshot is not authoritative and READY.")
    line = (
        WarehouseReceiptLine.objects.select_for_update()
        .select_related("receipt", "item", "receipt__warehouse", "receipt__legal_entity")
        .get(pk=receipt_line.pk)
    )
    claim = _claim(
        "warehouse.receipt.valuation.finalize",
        idempotency_key,
        {"line": str(line.pk), "snapshot": str(production_cost_snapshot.pk)},
        actor,
    )
    replay = _replay(claim, WarehouseReceiptLine)
    if replay:
        return replay
    if line.output_id != production_cost_snapshot.output_id:
        raise ValidationError("Cost snapshot output does not match receipt line.")
    if line.valuation_status == ValuationStatus.READY:
        raise ValidationError("Receipt line valuation is already finalized.")
    movement = StockMovement.objects.select_for_update().get(source_key=line.source_key)
    cost = production_cost_snapshot.unit_hpp
    value = line.accepted_quantity * cost
    movement.unit_cost, movement.total_value = cost, value
    movement.valuation_status = ValuationStatus.READY
    movement.save(update_fields=("unit_cost", "total_value", "valuation_status", "updated_at"))
    line.unit_cost, line.total_value = cost, value
    line.valuation_status = ValuationStatus.READY
    line.save(update_fields=("unit_cost", "total_value", "valuation_status", "updated_at"))
    state = _state(line.receipt.warehouse, line.item, line.receipt.legal_entity)
    pending = StockMovement.objects.filter(
        warehouse=line.receipt.warehouse,
        item=line.item,
        state=WarehouseDocumentState.POSTED,
        valuation_status=ValuationStatus.PENDING_VALUATION,
    ).exists()
    if not pending:
        rows = StockMovement.objects.filter(
            warehouse=line.receipt.warehouse,
            item=line.item,
            state=WarehouseDocumentState.POSTED,
        )
        incoming = rows.filter(direction=MovementDirection.IN).aggregate(total=Sum("quantity"))[
            "total"
        ] or Decimal("0")
        outgoing = rows.filter(direction=MovementDirection.OUT).aggregate(total=Sum("quantity"))[
            "total"
        ] or Decimal("0")
        value_total = rows.filter(valuation_status=ValuationStatus.READY).aggregate(
            total=Sum("total_value")
        )["total"] or Decimal("0")
        state.quantity_on_hand = incoming - outgoing
        state.inventory_value = value_total
        state.average_unit_cost = (
            value_total / state.quantity_on_hand if state.quantity_on_hand else None
        )
        state.valuation_status = ValuationStatus.READY
        state.save(
            update_fields=(
                "quantity_on_hand",
                "inventory_value",
                "average_unit_cost",
                "valuation_status",
                "updated_at",
            )
        )
    _audit(line, "warehouse.receipt.valuation.finalized", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(line.pk))
    return line
