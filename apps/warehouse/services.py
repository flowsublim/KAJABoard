from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import IdempotencyStatus
from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.production.models import ProductionHandoverState
from apps.purchasing.models import WorkOrderState, WorkOrderType
from apps.warehouse.models import (
    InternalConsumption,
    InternalConsumptionLine,
    InventoryAdjustment,
    InventoryAdjustmentLine,
    InventoryValuationState,
    MovementDirection,
    MovementType,
    OperationalDocumentState,
    StockCount,
    StockCountLine,
    StockMovement,
    SupplierReturn,
    SupplierReturnLine,
    ValuationStatus,
    WarehouseDocumentState,
    WarehouseMaterialIssue,
    WarehouseMaterialIssueLine,
    WarehousePostingSequence,
    WarehousePurchaseReceipt,
    WarehousePurchaseReceiptLine,
    WarehouseReceipt,
    WarehouseReceiptLine,
    WarehouseSalesIssue,
    WarehouseSalesIssueLine,
    WarehouseSubcontractReceipt,
    WarehouseSubcontractReceiptLine,
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
            if state.valuation_status != ValuationStatus.PENDING_VALUATION:
                state.inventory_value = (state.inventory_value or Decimal("0")) + total_value
                state.valuation_status = ValuationStatus.READY
            else:
                # A ready receipt cannot conceal an unresolved earlier receipt.
                state.inventory_value = None
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
    elif (
        direction == MovementDirection.OUT
        and state.valuation_status != ValuationStatus.PENDING_VALUATION
    ):
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
    handover_line = (
        type(handover_line)
        .objects.select_for_update()
        .select_related("handover", "item", "output")
        .get(pk=handover_line.pk)
    )
    quantity = _positive(accepted_quantity, "accepted_quantity")
    drafted = receipt.lines.filter(handover_line=handover_line).aggregate(
        total=Sum("accepted_quantity")
    )["total"] or Decimal("0")
    from apps.quality.selectors import quality_pass_authorization

    authorization = quality_pass_authorization(handover_line)
    if drafted + quantity > authorization["remaining_pass_quantity"]:
        raise ValidationError(
            "Accepted quantity exceeds remaining Quality PASS authorization. "
            "Production finished goods require Quality PASS before Warehouse receipt."
        )
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
    from apps.production.models import ProductionWarehouseHandoverLine
    from apps.quality.selectors import quality_pass_authorization

    posted_by_source = {}
    for line in receipt.lines.select_related("item"):
        handover_line = ProductionWarehouseHandoverLine.objects.select_for_update().get(
            pk=line.handover_line_id
        )
        authorization = quality_pass_authorization(handover_line)
        posted_by_source[handover_line.pk] = (
            posted_by_source.get(handover_line.pk, Decimal("0")) + line.accepted_quantity
        )
        if posted_by_source[handover_line.pk] > authorization["remaining_pass_quantity"]:
            raise ValidationError(
                "Warehouse receipt exceeds active Quality PASS authorization for a handover line."
            )
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
    _rebuild_state(line.receipt.legal_entity, line.receipt.warehouse, line.item)
    _audit(line, "warehouse.receipt.valuation.finalized", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(line.pk))
    return line


# ---------------------------------------------------------------------------
# Phase 6C operational adapters.  These functions are deliberately kept in
# this module so every source document reaches the same _post_movement()
# primitive and therefore the same sequence, valuation, and stock controls.


def _require_reason(reason, field="reason"):
    reason = str(reason or "").strip()
    if not reason:
        raise ValidationError({field: "Reason is required."})
    return reason


def _require_permission(actor, codename):
    if actor is not None and not actor.is_superuser and not actor.has_perm(f"warehouse.{codename}"):
        raise PermissionDenied(f"Warehouse permission required: {codename}")


def _current_sequence():
    sequence, _ = WarehousePostingSequence.objects.get_or_create(singleton=True)
    return sequence.last_sequence


def _active_sum(model, *, field, **filters):
    return model.objects.filter(**filters).aggregate(total=Sum(field))["total"] or Decimal("0")


def _ready_cost(state, *, explicit=None):
    cost = explicit if explicit is not None else state.average_unit_cost
    if cost is None or Decimal(str(cost)) <= 0 or state.valuation_status != ValuationStatus.READY:
        raise ValidationError(
            "Authoritative inventory valuation is unavailable; posting is blocked."
        )
    return Decimal(str(cost))


@transaction.atomic
def create_purchase_receipt(
    *, legal_entity, warehouse, purchase_order, receipt_date, actor=None, notes=""
):
    from apps.purchasing.models import PurchaseOrderState

    purchase_order = purchase_order.__class__.objects.get(pk=purchase_order.pk)
    _validate_warehouse(warehouse, legal_entity)
    if (
        purchase_order.legal_entity_id != legal_entity.pk
        or purchase_order.state != PurchaseOrderState.CONFIRMED
    ):
        raise ValidationError(
            "Only CONFIRMED Purchase Orders in the same legal entity can be received."
        )
    return WarehousePurchaseReceipt.objects.create(
        legal_entity=legal_entity,
        warehouse=warehouse,
        purchase_order=purchase_order,
        vendor=purchase_order.vendor,
        vendor_code_snapshot=purchase_order.vendor_code_snapshot,
        vendor_name_snapshot=purchase_order.vendor_name_snapshot,
        receipt_date=receipt_date,
        notes=str(notes or "").strip(),
        created_by=actor,
    )


@transaction.atomic
def add_purchase_receipt_line(receipt, *, purchase_order_line, quantity, actor=None, notes=""):
    from apps.purchasing.models import AccountingTreatment, PurchaseOrderState

    receipt = WarehousePurchaseReceipt.objects.select_for_update().get(pk=receipt.pk)
    line = (
        purchase_order_line.__class__.objects.select_for_update()
        .select_related("purchase_order", "item", "purchase_category")
        .get(pk=purchase_order_line.pk)
    )
    if receipt.state != WarehouseDocumentState.DRAFT:
        raise ValidationError("Only DRAFT purchase receipts can be edited.")
    if (
        line.purchase_order_id != receipt.purchase_order_id
        or line.purchase_order.state != PurchaseOrderState.CONFIRMED
    ):
        raise ValidationError("Purchase line must belong to the confirmed receipt Purchase Order.")
    if line.accounting_treatment_snapshot != AccountingTreatment.INVENTORY:
        raise ValidationError("Only Purchase Order INVENTORY lines can enter Warehouse stock.")
    if line.item_id is None or not line.item.inventory_eligible:
        raise ValidationError("Purchase inventory receipt requires an active inventory Item.")
    quantity = _positive(quantity)
    received = _active_sum(
        WarehousePurchaseReceiptLine,
        field="quantity",
        purchase_order_line=line,
        receipt__state=WarehouseDocumentState.POSTED,
    )
    drafted = _active_sum(
        WarehousePurchaseReceiptLine, field="quantity", purchase_order_line=line, receipt=receipt
    )
    if received + drafted + quantity > line.quantity:
        raise ValidationError("Receipt exceeds the remaining Purchase Order line quantity.")
    cost = Decimal(str(line.unit_price))
    if cost <= 0:
        raise ValidationError(
            "Purchase line inventory valuation cost snapshot must be greater than zero."
        )
    line_id = uuid4()
    return WarehousePurchaseReceiptLine.objects.create(
        id=line_id,
        receipt=receipt,
        purchase_order_line=line,
        item=line.item,
        item_code_snapshot=line.item_code_snapshot or line.item.code,
        item_name_snapshot=line.item_name_snapshot or line.item.name,
        uom_code_snapshot=line.uom_code_snapshot or line.item.uom.code,
        purchase_category_code_snapshot=line.category_code_snapshot,
        purchase_category_name_snapshot=line.category_name_snapshot,
        accounting_treatment_snapshot=line.accounting_treatment_snapshot,
        vendor_id_snapshot=str(receipt.vendor_id),
        quantity=quantity,
        unit_cost_snapshot=cost,
        total_value_snapshot=quantity * cost,
        source_key=f"PURCHASE_RECEIPT|{line_id}",
        sequence=(
            receipt.lines.order_by("-sequence").values_list("sequence", flat=True).first() or 0
        )
        + 1,
        notes=str(notes or "").strip(),
    )


@transaction.atomic
def post_purchase_receipt(receipt, *, actor=None, idempotency_key):
    receipt = (
        WarehousePurchaseReceipt.objects.select_for_update()
        .select_related("legal_entity", "warehouse", "purchase_order")
        .get(pk=receipt.pk)
    )
    claim = _claim(
        "warehouse.purchase_receipt.post", idempotency_key, {"receipt": str(receipt.pk)}, actor
    )
    replay = _replay(claim, WarehousePurchaseReceipt)
    if replay:
        return replay
    if receipt.state != WarehouseDocumentState.DRAFT or not receipt.lines.exists():
        raise ValidationError("Purchase receipt must be a non-empty DRAFT document.")
    from apps.purchasing.models import AccountingTreatment, PurchaseOrderLine, PurchaseOrderState

    lines = list(receipt.lines.select_related("item", "purchase_order_line").order_by("sequence"))
    source_ids = sorted({line.purchase_order_line_id for line in lines}, key=str)
    locked_sources = {
        row.pk: row
        for row in PurchaseOrderLine.objects.select_for_update().filter(pk__in=source_ids)
    }
    requested = {}
    for row in lines:
        source = locked_sources[row.purchase_order_line_id]
        if (
            source.purchase_order.state != PurchaseOrderState.CONFIRMED
            or source.accounting_treatment_snapshot != AccountingTreatment.INVENTORY
        ):
            raise ValidationError("Only CONFIRMED INVENTORY Purchase Order lines can be posted.")
        received = _active_sum(
            WarehousePurchaseReceiptLine,
            field="quantity",
            purchase_order_line=source,
            receipt__state=WarehouseDocumentState.POSTED,
        )
        requested[source.pk] = requested.get(source.pk, Decimal("0")) + row.quantity
        if received + requested[source.pk] > source.quantity:
            raise ValidationError("Purchase receipt exceeds the remaining quantity for a PO line.")
        if row.unit_cost_snapshot is None or row.unit_cost_snapshot <= 0:
            raise ValidationError("Purchase receipt has no authoritative valuation snapshot.")
    for row in lines:
        movement = _post_movement(
            entity=receipt.legal_entity,
            warehouse=receipt.warehouse,
            item=row.item,
            direction=MovementDirection.IN,
            movement_type=MovementType.PURCHASE_RECEIPT,
            quantity=row.quantity,
            source_module="purchasing",
            source_type="PURCHASE_ORDER_RECEIPT",
            source_document_id=receipt.purchase_order_id,
            source_line_id=row.purchase_order_line_id,
            source_key=row.source_key,
            transaction_date=receipt.receipt_date,
            actor=actor,
            unit_cost=row.unit_cost_snapshot,
            total_value=row.total_value_snapshot,
            valuation_status=ValuationStatus.READY,
        )
        row.posted_movement = movement
        row.save(update_fields=("posted_movement", "updated_at"))
    receipt.state, receipt.posted_by, receipt.posted_at = (
        WarehouseDocumentState.POSTED,
        actor,
        timezone.now(),
    )
    receipt.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    _audit(receipt, "warehouse.purchase_receipt.posted", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(receipt.pk))
    return receipt


@transaction.atomic
def reverse_purchase_receipt(receipt, *, reason, actor=None, idempotency_key):
    reason = _require_reason(reason)
    receipt = (
        WarehousePurchaseReceipt.objects.select_for_update()
        .select_related("legal_entity", "warehouse")
        .get(pk=receipt.pk)
    )
    claim = _claim(
        "warehouse.purchase_receipt.reverse",
        idempotency_key,
        {"receipt": str(receipt.pk), "reason": reason},
        actor,
    )
    replay = _replay(claim, WarehousePurchaseReceipt)
    if replay:
        return replay
    if receipt.state != WarehouseDocumentState.POSTED:
        raise ValidationError("Only POSTED purchase receipts can be reversed.")
    for row in receipt.lines.select_related("item", "posted_movement"):
        original = row.posted_movement or StockMovement.objects.select_for_update().get(
            source_key=row.source_key
        )
        movement = _post_movement(
            entity=receipt.legal_entity,
            warehouse=receipt.warehouse,
            item=row.item,
            direction=MovementDirection.OUT,
            movement_type=MovementType.PURCHASE_RECEIPT,
            quantity=row.quantity,
            source_module="warehouse",
            source_type="PURCHASE_RECEIPT_REVERSAL",
            source_document_id=receipt.pk,
            source_line_id=row.pk,
            source_key=f"REV|{row.source_key}",
            transaction_date=receipt.receipt_date,
            actor=actor,
            unit_cost=original.unit_cost,
            total_value=original.total_value,
            valuation_status=original.valuation_status,
            reversal_of=original,
            bypass_pending_valuation=True,
            notes=reason,
        )
        if movement is None:
            raise ValidationError("Purchase receipt reversal could not be posted.")
    receipt.state = WarehouseDocumentState.REVERSED
    receipt.save(update_fields=("state", "updated_at"))
    _audit(
        receipt, "warehouse.purchase_receipt.reversed", actor, reason=reason, key=idempotency_key
    )
    complete_idempotency(claim.record.pk, result_reference=str(receipt.pk))
    return receipt


def _subcontract_cost(output):
    from apps.production.models import ProductionCostSnapshot

    snapshot = (
        ProductionCostSnapshot.objects.filter(output=output, status="READY", unit_hpp__isnull=False)
        .order_by("-version")
        .first()
    )
    return snapshot.unit_hpp if snapshot else None


@transaction.atomic
def create_subcontract_warehouse_receipt(
    *, legal_entity, warehouse, subcontract_receipt, receipt_date, actor=None, notes=""
):
    from apps.purchasing.models import SubcontractReceiptState

    subcontract_receipt = subcontract_receipt.__class__.objects.get(pk=subcontract_receipt.pk)
    _validate_warehouse(warehouse, legal_entity)
    if (
        subcontract_receipt.legal_entity_id != legal_entity.pk
        or subcontract_receipt.state != SubcontractReceiptState.ACCEPTED
    ):
        raise ValidationError(
            "Only ACCEPTED subcontract receipts in the same legal entity can enter Warehouse."
        )
    return WarehouseSubcontractReceipt.objects.create(
        legal_entity=legal_entity,
        warehouse=warehouse,
        subcontract_receipt=subcontract_receipt,
        vendor=subcontract_receipt.vendor,
        vendor_code_snapshot=subcontract_receipt.vendor_code_snapshot,
        vendor_name_snapshot=subcontract_receipt.vendor_name_snapshot,
        receipt_date=receipt_date,
        notes=str(notes or "").strip(),
        created_by=actor,
    )


@transaction.atomic
def add_subcontract_warehouse_receipt_line(
    receipt, *, subcontract_receipt_line, quantity, actor=None, notes=""
):
    from apps.quality.selectors import subcontract_pass_authorization

    receipt = WarehouseSubcontractReceipt.objects.select_for_update().get(pk=receipt.pk)
    source = (
        subcontract_receipt_line.__class__.objects.select_for_update()
        .select_related("receipt", "item", "output")
        .get(pk=subcontract_receipt_line.pk)
    )
    if (
        receipt.state != WarehouseDocumentState.DRAFT
        or source.receipt_id != receipt.subcontract_receipt_id
    ):
        raise ValidationError(
            "Only DRAFT receipt lines from the selected ACCEPTED subcontract receipt are valid."
        )
    if source.item.item_kind == "SERVICE" or not source.item.inventory_eligible:
        raise ValidationError("Service-only subcontract lines cannot create physical stock.")
    quantity = _positive(quantity)
    auth = subcontract_pass_authorization(source)
    drafted = _active_sum(
        WarehouseSubcontractReceiptLine,
        field="quantity",
        subcontract_receipt_line=source,
        receipt=receipt,
    )
    if drafted + quantity > auth["remaining_pass_quantity"]:
        raise ValidationError("Subcontract Warehouse receipt exceeds active Quality PASS quantity.")
    cost = _subcontract_cost(source.output)
    status = ValuationStatus.READY if cost is not None else ValuationStatus.PENDING_VALUATION
    line_id = uuid4()
    return WarehouseSubcontractReceiptLine.objects.create(
        id=line_id,
        receipt=receipt,
        subcontract_receipt_line=source,
        item=source.item,
        item_code_snapshot=source.item_code_snapshot,
        item_name_snapshot=source.item_name_snapshot,
        uom_code_snapshot=source.uom_code_snapshot,
        quantity=quantity,
        quality_pass_quantity_snapshot=auth["remaining_pass_quantity"],
        unit_cost=cost,
        total_value=quantity * cost if cost is not None else None,
        valuation_status=status,
        source_key=f"SUBCONTRACT_RECEIPT|{line_id}",
        sequence=(
            receipt.lines.order_by("-sequence").values_list("sequence", flat=True).first() or 0
        )
        + 1,
        notes=str(notes or "").strip(),
    )


@transaction.atomic
def post_subcontract_warehouse_receipt(receipt, *, actor=None, idempotency_key):
    from apps.quality.selectors import subcontract_pass_authorization

    receipt = (
        WarehouseSubcontractReceipt.objects.select_for_update()
        .select_related("legal_entity", "warehouse")
        .get(pk=receipt.pk)
    )
    claim = _claim(
        "warehouse.subcontract_receipt.post", idempotency_key, {"receipt": str(receipt.pk)}, actor
    )
    replay = _replay(claim, WarehouseSubcontractReceipt)
    if replay:
        return replay
    if receipt.state != WarehouseDocumentState.DRAFT or not receipt.lines.exists():
        raise ValidationError("Subcontract Warehouse receipt must be a non-empty DRAFT document.")
    for row in receipt.lines.select_related("item", "subcontract_receipt_line__output"):
        auth = subcontract_pass_authorization(row.subcontract_receipt_line_id)
        drafted = _active_sum(
            WarehouseSubcontractReceiptLine,
            field="quantity",
            subcontract_receipt_line=row.subcontract_receipt_line_id,
            receipt=receipt,
        )
        if drafted > auth["remaining_pass_quantity"]:
            raise ValidationError("Only active Quality PASS quantity may enter normal stock.")
        movement = _post_movement(
            entity=receipt.legal_entity,
            warehouse=receipt.warehouse,
            item=row.item,
            direction=MovementDirection.IN,
            movement_type=MovementType.SUBCONTRACT_RECEIPT,
            quantity=row.quantity,
            source_module="purchasing",
            source_type="SUBCONTRACT_RECEIPT",
            source_document_id=receipt.subcontract_receipt_id,
            source_line_id=row.subcontract_receipt_line_id,
            source_key=row.source_key,
            transaction_date=receipt.receipt_date,
            actor=actor,
            unit_cost=row.unit_cost,
            total_value=row.total_value,
            valuation_status=row.valuation_status,
        )
        row.posted_movement = movement
        row.save(update_fields=("posted_movement", "updated_at"))
    receipt.state, receipt.posted_by, receipt.posted_at = (
        WarehouseDocumentState.POSTED,
        actor,
        timezone.now(),
    )
    receipt.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    _audit(receipt, "warehouse.subcontract_receipt.posted", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(receipt.pk))
    return receipt


@transaction.atomic
def finalize_subcontract_receipt_valuation(
    receipt_line, *, production_cost_snapshot, actor=None, idempotency_key
):
    if production_cost_snapshot.status != "READY" or production_cost_snapshot.unit_hpp is None:
        raise ValidationError("Production/Purchasing cost result is not authoritative and READY.")
    row = (
        WarehouseSubcontractReceiptLine.objects.select_for_update()
        .select_related("receipt", "item")
        .get(pk=receipt_line.pk)
    )
    claim = _claim(
        "warehouse.subcontract_receipt.valuation.finalize",
        idempotency_key,
        {"line": str(row.pk), "snapshot": str(production_cost_snapshot.pk)},
        actor,
    )
    replay = _replay(claim, WarehouseSubcontractReceiptLine)
    if replay:
        return replay
    if row.subcontract_receipt_line.output_id != production_cost_snapshot.output_id:
        raise ValidationError("Cost snapshot output does not match subcontract receipt line.")
    movement = row.posted_movement or StockMovement.objects.select_for_update().get(
        source_key=row.source_key
    )
    row.unit_cost = production_cost_snapshot.unit_hpp
    row.total_value = row.quantity * row.unit_cost
    row.valuation_status = ValuationStatus.READY
    row.save(update_fields=("unit_cost", "total_value", "valuation_status", "updated_at"))
    movement.unit_cost, movement.total_value, movement.valuation_status = (
        row.unit_cost,
        row.total_value,
        ValuationStatus.READY,
    )
    movement.save(update_fields=("unit_cost", "total_value", "valuation_status", "updated_at"))
    _rebuild_state(row.receipt.legal_entity, row.receipt.warehouse, row.item)
    _audit(row, "warehouse.subcontract_receipt.valuation.finalized", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(row.pk))
    return row


@transaction.atomic
def create_sales_issue(
    *, legal_entity, warehouse, sales_delivery, issue_date=None, actor=None, notes=""
):
    from apps.sales.models import SalesDeliveryState

    sales_delivery = sales_delivery.__class__.objects.get(pk=sales_delivery.pk)
    _validate_warehouse(warehouse, legal_entity)
    if (
        sales_delivery.legal_entity_id != legal_entity.pk
        or sales_delivery.state != SalesDeliveryState.POSTED
    ):
        raise ValidationError(
            "Only POSTED Sales Deliveries in the same legal entity can be issued."
        )
    return WarehouseSalesIssue.objects.create(
        legal_entity=legal_entity,
        warehouse=warehouse,
        sales_delivery=sales_delivery,
        customer=sales_delivery.customer,
        customer_code_snapshot=sales_delivery.customer_code_snapshot,
        customer_name_snapshot=sales_delivery.customer_name_snapshot,
        issue_date=issue_date or sales_delivery.delivery_date,
        notes=str(notes or "").strip(),
        created_by=actor,
    )


@transaction.atomic
def add_sales_issue_line(issue, *, sales_delivery_line, quantity, actor=None, notes=""):
    from apps.sales.models import SalesDeliveryState

    issue = WarehouseSalesIssue.objects.select_for_update().get(pk=issue.pk)
    source = (
        sales_delivery_line.__class__.objects.select_for_update()
        .select_related("sales_delivery", "source_sales_order_line", "item")
        .get(pk=sales_delivery_line.pk)
    )
    if (
        issue.state != WarehouseDocumentState.DRAFT
        or source.sales_delivery_id != issue.sales_delivery_id
    ):
        raise ValidationError("Only DRAFT issue lines from the selected POSTED delivery are valid.")
    if source.sales_delivery.state != SalesDeliveryState.POSTED:
        raise ValidationError("Sales Delivery must be POSTED before Warehouse issue.")
    quantity = _positive(quantity)
    issued = _active_sum(
        WarehouseSalesIssueLine,
        field="quantity",
        sales_delivery_line=source,
        issue__state=WarehouseDocumentState.POSTED,
    )
    drafted = _active_sum(
        WarehouseSalesIssueLine, field="quantity", sales_delivery_line=source, issue=issue
    )
    if issued + drafted + quantity > source.quantity:
        raise ValidationError("Warehouse issue exceeds the posted Sales Delivery line quantity.")
    line_id = uuid4()
    return WarehouseSalesIssueLine.objects.create(
        id=line_id,
        issue=issue,
        sales_delivery_line=source,
        item=source.item,
        sales_order_id_snapshot=str(source.source_sales_order_line.sales_order_id),
        sales_order_line_id_snapshot=str(source.source_sales_order_line_id),
        delivery_id_snapshot=str(source.sales_delivery_id),
        delivery_line_id_snapshot=str(source.pk),
        quantity=quantity,
        uom_code_snapshot=source.uom_code_snapshot,
        source_key=f"SALES_DELIVERY_ISSUE|{line_id}",
        sequence=(issue.lines.order_by("-sequence").values_list("sequence", flat=True).first() or 0)
        + 1,
        notes=str(notes or "").strip(),
    )


@transaction.atomic
def post_sales_issue(issue, *, actor=None, idempotency_key):
    issue = (
        WarehouseSalesIssue.objects.select_for_update()
        .select_related("legal_entity", "warehouse")
        .get(pk=issue.pk)
    )
    claim = _claim("warehouse.sales_issue.post", idempotency_key, {"issue": str(issue.pk)}, actor)
    replay = _replay(claim, WarehouseSalesIssue)
    if replay:
        return replay
    if issue.state != WarehouseDocumentState.DRAFT or not issue.lines.exists():
        raise ValidationError("Sales issue must be a non-empty DRAFT document.")
    from apps.sales.models import SalesDeliveryLine, SalesDeliveryState

    lines = list(issue.lines.select_related("item").order_by("sequence"))
    source_ids = sorted({line.sales_delivery_line_id for line in lines}, key=str)
    sources = {
        row.pk: row
        for row in SalesDeliveryLine.objects.select_for_update()
        .select_related("sales_delivery")
        .filter(pk__in=source_ids)
    }
    requested = {}
    for row in lines:
        source = sources[row.sales_delivery_line_id]
        if (
            source.sales_delivery.state != SalesDeliveryState.POSTED
            or source.sales_delivery.legal_entity_id != issue.legal_entity_id
        ):
            raise ValidationError(
                "Sales issue source delivery is no longer an active POSTED candidate."
            )
        issued = _active_sum(
            WarehouseSalesIssueLine,
            field="quantity",
            sales_delivery_line=source,
            issue__state=WarehouseDocumentState.POSTED,
        )
        requested[source.pk] = requested.get(source.pk, Decimal("0")) + row.quantity
        if issued + requested[source.pk] > source.quantity:
            raise ValidationError("Warehouse issue exceeds remaining posted Delivery quantity.")
    for row in lines:
        movement = _post_movement(
            entity=issue.legal_entity,
            warehouse=issue.warehouse,
            item=row.item,
            direction=MovementDirection.OUT,
            movement_type=MovementType.SALES_DELIVERY_ISSUE,
            quantity=row.quantity,
            source_module="sales",
            source_type="SALES_DELIVERY",
            source_document_id=row.delivery_id_snapshot,
            source_line_id=row.delivery_line_id_snapshot,
            source_key=row.source_key,
            transaction_date=issue.issue_date,
            actor=actor,
        )
        row.unit_cost, row.total_value, row.posted_movement = (
            movement.unit_cost,
            movement.total_value,
            movement,
        )
        row.save(update_fields=("unit_cost", "total_value", "posted_movement", "updated_at"))
    issue.state, issue.posted_by, issue.posted_at = (
        WarehouseDocumentState.POSTED,
        actor,
        timezone.now(),
    )
    issue.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    _audit(issue, "warehouse.sales_issue.posted", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(issue.pk))
    return issue


@transaction.atomic
def reverse_sales_issue(issue, *, reason, actor=None, idempotency_key):
    reason = _require_reason(reason)
    issue = (
        WarehouseSalesIssue.objects.select_for_update()
        .select_related("legal_entity", "warehouse")
        .get(pk=issue.pk)
    )
    claim = _claim(
        "warehouse.sales_issue.reverse",
        idempotency_key,
        {"issue": str(issue.pk), "reason": reason},
        actor,
    )
    replay = _replay(claim, WarehouseSalesIssue)
    if replay:
        return replay
    if issue.state != WarehouseDocumentState.POSTED:
        raise ValidationError("Only POSTED sales issues can be reversed.")
    for row in issue.lines.select_related("item", "posted_movement"):
        original = row.posted_movement or StockMovement.objects.select_for_update().get(
            source_key=row.source_key
        )
        _post_movement(
            entity=issue.legal_entity,
            warehouse=issue.warehouse,
            item=row.item,
            direction=MovementDirection.IN,
            movement_type=MovementType.SALES_DELIVERY_ISSUE,
            quantity=row.quantity,
            source_module="warehouse",
            source_type="SALES_ISSUE_REVERSAL",
            source_document_id=issue.pk,
            source_line_id=row.pk,
            source_key=f"REV|{row.source_key}",
            transaction_date=issue.issue_date,
            actor=actor,
            unit_cost=original.unit_cost,
            total_value=original.total_value,
            valuation_status=original.valuation_status,
            reversal_of=original,
            bypass_pending_valuation=True,
            notes=reason,
        )
    issue.state = WarehouseDocumentState.REVERSED
    issue.save(update_fields=("state", "updated_at"))
    _audit(issue, "warehouse.sales_issue.reversed", actor, reason=reason, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(issue.pk))
    return issue


@transaction.atomic
def create_stock_count(*, legal_entity, warehouse, count_date, actor=None, notes="", items=None):
    _validate_warehouse(warehouse, legal_entity)
    count = StockCount.objects.create(
        legal_entity=legal_entity,
        warehouse=warehouse,
        count_date=count_date,
        notes=str(notes or "").strip(),
        created_by=actor,
    )
    for item in items or ():
        add_stock_count_line(count, item=item, actor=actor)
    return count


@transaction.atomic
def add_stock_count_line(count, *, item, actor=None):
    count = StockCount.objects.select_for_update().get(pk=count.pk)
    if count.state != OperationalDocumentState.DRAFT:
        raise ValidationError("Only DRAFT stock counts can be edited.")
    if (
        item.legal_entity_id != count.legal_entity_id
        or not item.is_active
        or not item.inventory_eligible
    ):
        raise ValidationError("Count item must be an active inventory Item in the legal entity.")
    sequence = WarehousePostingSequence.objects.select_for_update().get_or_create(singleton=True)[0]
    if not count.snapshot_sequence:
        count.snapshot_sequence = sequence.last_sequence
        count.save(update_fields=("snapshot_sequence", "updated_at"))
    state = _state(count.warehouse, item, count.legal_entity)
    line_id = uuid4()
    line = StockCountLine.objects.create(
        id=line_id,
        count=count,
        item=item,
        system_qty_snapshot=state.quantity_on_hand,
        uom_code_snapshot=item.uom.code,
        sequence=(count.lines.order_by("-sequence").values_list("sequence", flat=True).first() or 0)
        + 1,
    )
    _audit(line, "warehouse.stock_count_line.snapshotted", actor)
    return line


@transaction.atomic
def record_stock_count_line(line, *, counted_quantity, reason="", actor=None):
    row = StockCountLine.objects.select_for_update().select_related("count").get(pk=line.pk)
    if row.count.state != OperationalDocumentState.DRAFT:
        raise ValidationError("Only DRAFT stock counts can record quantities.")
    counted = Decimal(str(counted_quantity))
    if counted < 0:
        raise ValidationError({"counted_quantity": "Counted quantity cannot be negative."})
    row.counted_qty, row.variance_qty, row.reason = (
        counted,
        counted - row.system_qty_snapshot,
        str(reason or "").strip(),
    )
    row.save(update_fields=("counted_qty", "variance_qty", "reason", "updated_at"))
    return row


@transaction.atomic
def approve_stock_count(count, *, actor=None):
    _require_permission(actor, "approve_stockcount")
    count = StockCount.objects.select_for_update().get(pk=count.pk)
    if count.state != OperationalDocumentState.COUNTED:
        raise ValidationError("Stock count must be COUNTED before approval.")
    if count.lines.filter(counted_qty__isnull=True).exists():
        raise ValidationError("Every stock count line must have a counted quantity.")
    count.state, count.approved_by, count.approved_at = (
        OperationalDocumentState.APPROVED,
        actor,
        timezone.now(),
    )
    count.save(update_fields=("state", "approved_by", "approved_at", "updated_at"))
    _audit(count, "warehouse.stock_count.approved", actor)
    return count


@transaction.atomic
def mark_stock_count_counted(count, *, actor=None):
    count = StockCount.objects.select_for_update().get(pk=count.pk)
    if (
        count.state != OperationalDocumentState.DRAFT
        or not count.lines.exists()
        or count.lines.filter(counted_qty__isnull=True).exists()
    ):
        raise ValidationError("Stock count must have counted quantities before submission.")
    count.state, count.submitted_by, count.submitted_at = (
        OperationalDocumentState.COUNTED,
        actor,
        timezone.now(),
    )
    count.save(update_fields=("state", "submitted_by", "submitted_at", "updated_at"))
    return count


@transaction.atomic
def post_stock_count(count, *, actor=None, idempotency_key):
    _require_permission(actor, "post_stockcount")
    count = (
        StockCount.objects.select_for_update()
        .select_related("legal_entity", "warehouse")
        .get(pk=count.pk)
    )
    claim = _claim("warehouse.stock_count.post", idempotency_key, {"count": str(count.pk)}, actor)
    replay = _replay(claim, StockCount)
    if replay:
        return replay
    if count.state != OperationalDocumentState.APPROVED:
        raise ValidationError("Only APPROVED stock counts can be posted.")
    WarehousePostingSequence.objects.select_for_update().get_or_create(singleton=True)
    if StockMovement.objects.filter(
        legal_entity=count.legal_entity,
        warehouse=count.warehouse,
        posting_sequence__gt=count.snapshot_sequence,
    ).exists():
        raise ValidationError("Stock count snapshot is stale; recount or rebase is required.")
    for row in count.lines.select_related("item"):
        if row.counted_qty is None:
            raise ValidationError("Every stock count line must be counted.")
        row.variance_qty = row.counted_qty - row.system_qty_snapshot
        if not row.variance_qty:
            row.save(update_fields=("variance_qty", "updated_at"))
            continue
        state = _state(count.warehouse, row.item, count.legal_entity)
        cost = _ready_cost(state)
        direction = MovementDirection.IN if row.variance_qty > 0 else MovementDirection.OUT
        movement = _post_movement(
            entity=count.legal_entity,
            warehouse=count.warehouse,
            item=row.item,
            direction=direction,
            movement_type=MovementType.OPNAME_GAIN
            if direction == MovementDirection.IN
            else MovementType.OPNAME_LOSS,
            quantity=abs(row.variance_qty),
            source_module="warehouse",
            source_type="STOCK_COUNT",
            source_document_id=count.pk,
            source_line_id=row.pk,
            source_key=f"STOCK_COUNT|{row.pk}",
            transaction_date=count.count_date,
            actor=actor,
            unit_cost=cost,
            total_value=abs(row.variance_qty) * cost,
            valuation_status=ValuationStatus.READY,
        )
        row.save(update_fields=("variance_qty", "updated_at"))
        _audit(movement, "warehouse.stock_count.variance_posted", actor, key=idempotency_key)
    count.state, count.posted_by, count.posted_at = (
        OperationalDocumentState.POSTED,
        actor,
        timezone.now(),
    )
    count.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    _audit(count, "warehouse.stock_count.posted", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(count.pk))
    return count


@transaction.atomic
def create_inventory_adjustment(
    *, legal_entity, warehouse, adjustment_date, reason, reference, actor=None
):
    _validate_warehouse(warehouse, legal_entity)
    reason, reference = _require_reason(reason), str(reference or "").strip()
    if not reference:
        raise ValidationError({"reference": "Reference is required."})
    return InventoryAdjustment.objects.create(
        legal_entity=legal_entity,
        warehouse=warehouse,
        adjustment_date=adjustment_date,
        reason=reason,
        reference=reference,
        created_by=actor,
    )


@transaction.atomic
def add_inventory_adjustment_line(
    adjustment, *, item, quantity, direction, actor=None, cost_treatment="CURRENT_AVERAGE"
):
    adjustment = InventoryAdjustment.objects.select_for_update().get(pk=adjustment.pk)
    if adjustment.state != OperationalDocumentState.DRAFT:
        raise ValidationError("Only DRAFT adjustments can be edited.")
    direction = {"POSITIVE": MovementDirection.IN, "NEGATIVE": MovementDirection.OUT}.get(
        str(direction).upper(), str(direction).upper()
    )
    if direction not in {MovementDirection.IN, MovementDirection.OUT}:
        raise ValidationError(
            "Adjustment direction must be ADJUSTMENT_POSITIVE or ADJUSTMENT_NEGATIVE."
        )
    if item.legal_entity_id != adjustment.legal_entity_id or not item.inventory_eligible:
        raise ValidationError("Adjustment item must be an inventory Item in the legal entity.")
    quantity = _positive(quantity)
    line_id = uuid4()
    return InventoryAdjustmentLine.objects.create(
        id=line_id,
        adjustment=adjustment,
        item=item,
        direction=direction,
        quantity=quantity,
        uom_code_snapshot=item.uom.code,
        cost_treatment=str(cost_treatment or "CURRENT_AVERAGE"),
        source_key=f"INVENTORY_ADJUSTMENT|{line_id}",
        sequence=(
            adjustment.lines.order_by("-sequence").values_list("sequence", flat=True).first() or 0
        )
        + 1,
    )


@transaction.atomic
def approve_inventory_adjustment(adjustment, *, actor=None):
    _require_permission(actor, "approve_inventoryadjustment")
    adjustment = InventoryAdjustment.objects.select_for_update().get(pk=adjustment.pk)
    if adjustment.state != OperationalDocumentState.DRAFT or not adjustment.lines.exists():
        raise ValidationError("A non-empty DRAFT adjustment is required before approval.")
    adjustment.state, adjustment.approved_by = OperationalDocumentState.APPROVED, actor
    adjustment.save(update_fields=("state", "approved_by", "updated_at"))
    _audit(adjustment, "warehouse.inventory_adjustment.approved", actor)
    return adjustment


@transaction.atomic
def post_inventory_adjustment(adjustment, *, actor=None, idempotency_key):
    _require_permission(actor, "post_inventoryadjustment")
    adjustment = (
        InventoryAdjustment.objects.select_for_update()
        .select_related("legal_entity", "warehouse")
        .get(pk=adjustment.pk)
    )
    claim = _claim(
        "warehouse.inventory_adjustment.post",
        idempotency_key,
        {"adjustment": str(adjustment.pk)},
        actor,
    )
    replay = _replay(claim, InventoryAdjustment)
    if replay:
        return replay
    if adjustment.state != OperationalDocumentState.APPROVED:
        raise ValidationError("Only APPROVED adjustments can be posted.")
    for row in adjustment.lines.select_related("item"):
        state = _state(adjustment.warehouse, row.item, adjustment.legal_entity)
        cost = _ready_cost(state)
        movement = _post_movement(
            entity=adjustment.legal_entity,
            warehouse=adjustment.warehouse,
            item=row.item,
            direction=row.direction,
            movement_type=MovementType.INVENTORY_ADJUSTMENT,
            quantity=row.quantity,
            source_module="warehouse",
            source_type="INVENTORY_ADJUSTMENT",
            source_document_id=adjustment.pk,
            source_line_id=row.pk,
            source_key=row.source_key,
            transaction_date=adjustment.adjustment_date,
            actor=actor,
            unit_cost=cost,
            total_value=row.quantity * cost,
            valuation_status=ValuationStatus.READY,
        )
        row.unit_cost, row.total_value, row.posted_movement = (
            movement.unit_cost,
            movement.total_value,
            movement,
        )
        row.save(update_fields=("unit_cost", "total_value", "posted_movement", "updated_at"))
    adjustment.state, adjustment.posted_by, adjustment.posted_at = (
        OperationalDocumentState.POSTED,
        actor,
        timezone.now(),
    )
    adjustment.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    _audit(adjustment, "warehouse.inventory_adjustment.posted", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(adjustment.pk))
    return adjustment


@transaction.atomic
def reverse_inventory_adjustment(adjustment, *, reason, actor=None, idempotency_key):
    reason = _require_reason(reason)
    _require_permission(actor, "reverse_inventoryadjustment")
    adjustment = (
        InventoryAdjustment.objects.select_for_update()
        .select_related("legal_entity", "warehouse")
        .get(pk=adjustment.pk)
    )
    claim = _claim(
        "warehouse.inventory_adjustment.reverse",
        idempotency_key,
        {"adjustment": str(adjustment.pk), "reason": reason},
        actor,
    )
    replay = _replay(claim, InventoryAdjustment)
    if replay:
        return replay
    if adjustment.state != OperationalDocumentState.POSTED:
        raise ValidationError("Only POSTED adjustments can be reversed.")
    for row in adjustment.lines.select_related("item", "posted_movement"):
        original = row.posted_movement or StockMovement.objects.select_for_update().get(
            source_key=row.source_key
        )
        _post_movement(
            entity=adjustment.legal_entity,
            warehouse=adjustment.warehouse,
            item=row.item,
            direction=MovementDirection.OUT
            if original.direction == MovementDirection.IN
            else MovementDirection.IN,
            movement_type=MovementType.INVENTORY_ADJUSTMENT,
            quantity=row.quantity,
            source_module="warehouse",
            source_type="ADJUSTMENT_REVERSAL",
            source_document_id=adjustment.pk,
            source_line_id=row.pk,
            source_key=f"REV|{row.source_key}",
            transaction_date=adjustment.adjustment_date,
            actor=actor,
            unit_cost=original.unit_cost,
            total_value=original.total_value,
            valuation_status=original.valuation_status,
            reversal_of=original,
            bypass_pending_valuation=True,
            notes=reason,
        )
    adjustment.state = OperationalDocumentState.REVERSED
    adjustment.save(update_fields=("state", "updated_at"))
    _audit(
        adjustment,
        "warehouse.inventory_adjustment.reversed",
        actor,
        reason=reason,
        key=idempotency_key,
    )
    complete_idempotency(claim.record.pk, result_reference=str(adjustment.pk))
    return adjustment


@transaction.atomic
def create_internal_consumption(
    *,
    legal_entity,
    warehouse,
    transaction_date,
    purpose,
    reason,
    actor=None,
    reference="",
    cost_center=None,
    project=None,
):
    _validate_warehouse(warehouse, legal_entity)
    purpose, reason = str(purpose or "").strip(), _require_reason(reason)
    if not purpose:
        raise ValidationError({"purpose": "Purpose is required."})
    if cost_center is not None and cost_center.legal_entity_id != legal_entity.pk:
        raise ValidationError("Cost center must belong to the legal entity.")
    if project is not None and project.legal_entity_id != legal_entity.pk:
        raise ValidationError("Project must belong to the legal entity.")
    return InternalConsumption.objects.create(
        legal_entity=legal_entity,
        warehouse=warehouse,
        transaction_date=transaction_date,
        purpose=purpose,
        reason=reason,
        reference=str(reference or "").strip(),
        cost_center=cost_center,
        project=project,
        created_by=actor,
    )


@transaction.atomic
def add_internal_consumption_line(consumption, *, item, quantity, actor=None):
    consumption = InternalConsumption.objects.select_for_update().get(pk=consumption.pk)
    if consumption.state != WarehouseDocumentState.DRAFT:
        raise ValidationError("Only DRAFT internal consumption can be edited.")
    if item.legal_entity_id != consumption.legal_entity_id or not item.inventory_eligible:
        raise ValidationError(
            "Internal consumption requires an inventory Item in the legal entity."
        )
    line_id = uuid4()
    return InternalConsumptionLine.objects.create(
        id=line_id,
        consumption=consumption,
        item=item,
        quantity=_positive(quantity),
        uom_code_snapshot=item.uom.code,
        source_key=f"INTERNAL_CONSUMPTION|{line_id}",
        sequence=(
            consumption.lines.order_by("-sequence").values_list("sequence", flat=True).first() or 0
        )
        + 1,
    )


@transaction.atomic
def post_internal_consumption(consumption, *, actor=None, idempotency_key):
    consumption = (
        InternalConsumption.objects.select_for_update()
        .select_related("legal_entity", "warehouse")
        .get(pk=consumption.pk)
    )
    claim = _claim(
        "warehouse.internal_consumption.post",
        idempotency_key,
        {"consumption": str(consumption.pk)},
        actor,
    )
    replay = _replay(claim, InternalConsumption)
    if replay:
        return replay
    if consumption.state != WarehouseDocumentState.DRAFT or not consumption.lines.exists():
        raise ValidationError("Internal consumption must be a non-empty DRAFT document.")
    for row in consumption.lines.select_related("item"):
        movement = _post_movement(
            entity=consumption.legal_entity,
            warehouse=consumption.warehouse,
            item=row.item,
            direction=MovementDirection.OUT,
            movement_type=MovementType.INTERNAL_CONSUMPTION,
            quantity=row.quantity,
            source_module="warehouse",
            source_type="INTERNAL_CONSUMPTION",
            source_document_id=consumption.pk,
            source_line_id=row.pk,
            source_key=row.source_key,
            transaction_date=consumption.transaction_date,
            actor=actor,
        )
        row.unit_cost, row.total_value, row.posted_movement = (
            movement.unit_cost,
            movement.total_value,
            movement,
        )
        row.save(update_fields=("unit_cost", "total_value", "posted_movement", "updated_at"))
    consumption.state, consumption.posted_by, consumption.posted_at = (
        WarehouseDocumentState.POSTED,
        actor,
        timezone.now(),
    )
    consumption.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    _audit(consumption, "warehouse.internal_consumption.posted", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(consumption.pk))
    return consumption


@transaction.atomic
def create_supplier_return(
    *,
    legal_entity,
    warehouse,
    supplier,
    transaction_date,
    reason,
    actor=None,
    reference="",
    purchase_order=None,
):
    _validate_warehouse(warehouse, legal_entity)
    reason = _require_reason(reason)
    if supplier.legal_entity_id != legal_entity.pk:
        raise ValidationError("Supplier must belong to the legal entity.")
    if purchase_order is not None and (
        purchase_order.legal_entity_id != legal_entity.pk or purchase_order.vendor_id != supplier.pk
    ):
        raise ValidationError("Purchase Order supplier and legal entity must match the return.")
    return SupplierReturn.objects.create(
        legal_entity=legal_entity,
        warehouse=warehouse,
        supplier=supplier,
        purchase_order=purchase_order,
        transaction_date=transaction_date,
        reason=reason,
        reference=str(reference or "").strip(),
        created_by=actor,
    )


@transaction.atomic
def add_supplier_return_line(
    supplier_return,
    *,
    item,
    quantity,
    purchase_order_line=None,
    purchase_receipt_line=None,
    actor=None,
):
    supplier_return = SupplierReturn.objects.select_for_update().get(pk=supplier_return.pk)
    if supplier_return.state != WarehouseDocumentState.DRAFT:
        raise ValidationError("Only DRAFT supplier returns can be edited.")
    if item.legal_entity_id != supplier_return.legal_entity_id or not item.inventory_eligible:
        raise ValidationError("Supplier return requires an inventory Item in the legal entity.")
    if purchase_receipt_line is not None:
        purchase_receipt_line = WarehousePurchaseReceiptLine.objects.select_related(
            "receipt", "purchase_order_line"
        ).get(pk=purchase_receipt_line.pk)
        purchase_order_line = purchase_order_line or purchase_receipt_line.purchase_order_line
        if (
            purchase_receipt_line.receipt.state != WarehouseDocumentState.POSTED
            or purchase_receipt_line.item_id != item.pk
        ):
            raise ValidationError(
                "Supplier return receipt lineage is not an active posted receipt for this Item."
            )
    if purchase_order_line is not None:
        if (
            purchase_order_line.purchase_order.vendor_id != supplier_return.supplier_id
            or purchase_order_line.item_id != item.pk
        ):
            raise ValidationError(
                "Supplier return Purchase Order lineage does not match supplier or Item."
            )
        if (
            supplier_return.purchase_order_id
            and purchase_order_line.purchase_order_id != supplier_return.purchase_order_id
        ):
            raise ValidationError(
                "Supplier return line must belong to the selected Purchase Order."
            )
    line_id = uuid4()
    return SupplierReturnLine.objects.create(
        id=line_id,
        supplier_return=supplier_return,
        item=item,
        purchase_order_line=purchase_order_line,
        purchase_receipt_line=purchase_receipt_line,
        quantity=_positive(quantity),
        uom_code_snapshot=item.uom.code,
        source_key=f"SUPPLIER_RETURN|{line_id}",
        sequence=(
            supplier_return.lines.order_by("-sequence").values_list("sequence", flat=True).first()
            or 0
        )
        + 1,
    )


@transaction.atomic
def post_supplier_return(supplier_return, *, actor=None, idempotency_key):
    supplier_return = (
        SupplierReturn.objects.select_for_update()
        .select_related("legal_entity", "warehouse")
        .get(pk=supplier_return.pk)
    )
    claim = _claim(
        "warehouse.supplier_return.post",
        idempotency_key,
        {"return": str(supplier_return.pk)},
        actor,
    )
    replay = _replay(claim, SupplierReturn)
    if replay:
        return replay
    if supplier_return.state != WarehouseDocumentState.DRAFT or not supplier_return.lines.exists():
        raise ValidationError("Supplier return must be a non-empty DRAFT document.")
    for row in supplier_return.lines.select_related(
        "item", "purchase_receipt_line", "purchase_order_line"
    ):
        if row.purchase_receipt_line_id:
            received = _active_sum(
                WarehousePurchaseReceiptLine,
                field="quantity",
                pk=row.purchase_receipt_line_id,
                receipt__state=WarehouseDocumentState.POSTED,
            )
            returned = _active_sum(
                SupplierReturnLine,
                field="quantity",
                purchase_receipt_line_id=row.purchase_receipt_line_id,
                supplier_return__state=WarehouseDocumentState.POSTED,
            )
            if returned + row.quantity > received:
                raise ValidationError(
                    "Supplier return exceeds the physically received quantity for the "
                    "referenced receipt line."
                )
        movement = _post_movement(
            entity=supplier_return.legal_entity,
            warehouse=supplier_return.warehouse,
            item=row.item,
            direction=MovementDirection.OUT,
            movement_type=MovementType.SUPPLIER_RETURN,
            quantity=row.quantity,
            source_module="warehouse",
            source_type="SUPPLIER_RETURN",
            source_document_id=supplier_return.pk,
            source_line_id=row.pk,
            source_key=row.source_key,
            transaction_date=supplier_return.transaction_date,
            actor=actor,
        )
        row.unit_cost, row.total_value, row.posted_movement = (
            movement.unit_cost,
            movement.total_value,
            movement,
        )
        row.save(update_fields=("unit_cost", "total_value", "posted_movement", "updated_at"))
    supplier_return.state, supplier_return.posted_by, supplier_return.posted_at = (
        WarehouseDocumentState.POSTED,
        actor,
        timezone.now(),
    )
    supplier_return.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    _audit(supplier_return, "warehouse.supplier_return.posted", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(supplier_return.pk))
    return supplier_return


def _rebuild_state(entity, warehouse, item):
    """Rebuild one state only after an explicit valuation finalization."""
    rows = StockMovement.objects.filter(
        legal_entity=entity, warehouse=warehouse, item=item, state=WarehouseDocumentState.POSTED
    ).order_by("posting_sequence")
    pending = rows.filter(valuation_status=ValuationStatus.PENDING_VALUATION).exists()
    incoming = rows.filter(direction=MovementDirection.IN).aggregate(total=Sum("quantity"))[
        "total"
    ] or Decimal("0")
    outgoing = rows.filter(direction=MovementDirection.OUT).aggregate(total=Sum("quantity"))[
        "total"
    ] or Decimal("0")
    state = _state(warehouse, item, entity)
    state.quantity_on_hand = incoming - outgoing
    state.last_movement_sequence = (
        rows.order_by("-posting_sequence").values_list("posting_sequence", flat=True).first() or 0
    )
    if pending:
        state.inventory_value, state.average_unit_cost, state.valuation_status = (
            None,
            None,
            ValuationStatus.PENDING_VALUATION,
        )
    else:
        value = sum(
            (
                row.total_value if row.direction == MovementDirection.IN else -row.total_value
                for row in rows
                if row.total_value is not None
            ),
            Decimal("0"),
        )
        state.inventory_value = value
        state.average_unit_cost = value / state.quantity_on_hand if state.quantity_on_hand else None
        state.valuation_status = ValuationStatus.READY
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
    return state


def reverse_operational_document(document, *, reason, actor=None, idempotency_key):
    """Explicit dispatch for operational reversal buttons and integrations."""
    if isinstance(document, WarehousePurchaseReceipt):
        return reverse_purchase_receipt(
            document, reason=reason, actor=actor, idempotency_key=idempotency_key
        )
    if isinstance(document, WarehouseSubcontractReceipt):
        return reverse_subcontract_warehouse_receipt(
            document, reason=reason, actor=actor, idempotency_key=idempotency_key
        )
    if isinstance(document, WarehouseSalesIssue):
        return reverse_sales_issue(
            document, reason=reason, actor=actor, idempotency_key=idempotency_key
        )
    if isinstance(document, InventoryAdjustment):
        return reverse_inventory_adjustment(
            document, reason=reason, actor=actor, idempotency_key=idempotency_key
        )
    raise ValidationError("This Warehouse document type has no operational reversal adapter.")


@transaction.atomic
def reverse_subcontract_warehouse_receipt(receipt, *, reason, actor=None, idempotency_key):
    reason = _require_reason(reason)
    receipt = (
        WarehouseSubcontractReceipt.objects.select_for_update()
        .select_related("legal_entity", "warehouse")
        .get(pk=receipt.pk)
    )
    claim = _claim(
        "warehouse.subcontract_receipt.reverse",
        idempotency_key,
        {"receipt": str(receipt.pk), "reason": reason},
        actor,
    )
    replay = _replay(claim, WarehouseSubcontractReceipt)
    if replay:
        return replay
    if receipt.state != WarehouseDocumentState.POSTED:
        raise ValidationError("Only POSTED subcontract receipts can be reversed.")
    for row in receipt.lines.select_related("item", "posted_movement"):
        original = row.posted_movement or StockMovement.objects.select_for_update().get(
            source_key=row.source_key
        )
        _post_movement(
            entity=receipt.legal_entity,
            warehouse=receipt.warehouse,
            item=row.item,
            direction=MovementDirection.OUT,
            movement_type=MovementType.SUBCONTRACT_RECEIPT,
            quantity=row.quantity,
            source_module="warehouse",
            source_type="SUBCONTRACT_RECEIPT_REVERSAL",
            source_document_id=receipt.pk,
            source_line_id=row.pk,
            source_key=f"REV|{row.source_key}",
            transaction_date=receipt.receipt_date,
            actor=actor,
            unit_cost=original.unit_cost,
            total_value=original.total_value,
            valuation_status=original.valuation_status,
            reversal_of=original,
            bypass_pending_valuation=True,
            notes=reason,
        )
    receipt.state = WarehouseDocumentState.REVERSED
    receipt.save(update_fields=("state", "updated_at"))
    _audit(
        receipt, "warehouse.subcontract_receipt.reversed", actor, reason=reason, key=idempotency_key
    )
    complete_idempotency(claim.record.pk, result_reference=str(receipt.pk))
    return receipt


# Descriptive aliases make the source-module boundary explicit to adapters
# without creating a second implementation or a second ledger primitive.
create_warehouse_purchase_receipt = create_purchase_receipt
add_warehouse_purchase_receipt_line = add_purchase_receipt_line
post_warehouse_purchase_receipt = post_purchase_receipt
reverse_warehouse_purchase_receipt = reverse_purchase_receipt
create_warehouse_subcontract_receipt = create_subcontract_warehouse_receipt
add_warehouse_subcontract_receipt_line = add_subcontract_warehouse_receipt_line
post_warehouse_subcontract_receipt = post_subcontract_warehouse_receipt
reverse_warehouse_subcontract_receipt = reverse_subcontract_warehouse_receipt
create_warehouse_sales_issue = create_sales_issue
add_warehouse_sales_issue_line = add_sales_issue_line
post_warehouse_sales_issue = post_sales_issue
reverse_warehouse_sales_issue = reverse_sales_issue
create_stock_opname = create_stock_count
add_stock_opname_line = add_stock_count_line
record_stock_opname_line = record_stock_count_line
mark_stock_opname_counted = mark_stock_count_counted
approve_stock_opname = approve_stock_count
post_stock_opname = post_stock_count
create_stock_adjustment = create_inventory_adjustment
add_stock_adjustment_line = add_inventory_adjustment_line
approve_stock_adjustment = approve_inventory_adjustment
post_stock_adjustment = post_inventory_adjustment
reverse_stock_adjustment = reverse_inventory_adjustment
