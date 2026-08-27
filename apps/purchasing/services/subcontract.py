from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import IdempotencyStatus
from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.core.services.numbering import allocate_document_number
from apps.purchasing.models import (
    SubcontractCostType,
    SubcontractDispatchState,
    SubcontractMaterialDispatch,
    SubcontractMaterialDispatchLine,
    SubcontractReceipt,
    SubcontractReceiptCostLine,
    SubcontractReceiptOutputLine,
    SubcontractReceiptState,
    WorkOrder,
    WorkOrderMaterialAllocation,
    WorkOrderOutput,
    WorkOrderState,
    WorkOrderType,
)


def _audit(obj, action, actor=None, reason=""):
    record_audit_event(
        action=action,
        target_type=obj._meta.label_lower,
        target_id=obj.pk,
        actor=actor,
        source="purchasing.subcontract_service",
        reason=reason,
    )


def _subcontract_work_order(work_order):
    if (
        work_order.work_order_type != WorkOrderType.SUBCONTRACT
        or work_order.state != WorkOrderState.APPROVED
    ):
        raise ValidationError("Only APPROVED SUBCONTRACT SPK is eligible.")
    if not work_order.vendor_id:
        raise ValidationError("Subcontract SPK requires a vendor.")


def _draft(record):
    if record.state != "DRAFT":
        raise ValidationError("Only DRAFT records can be edited.")


def _claim(namespace, key, payload, actor):
    if not key:
        return None
    claim = claim_idempotency(namespace=namespace, key=key, payload=payload, actor=actor)
    if not claim.is_new:
        if claim.record.status == IdempotencyStatus.COMPLETED and claim.record.result_reference:
            return claim
        raise ValidationError("A prior request is still in progress.")
    return claim


def _complete(claim, record):
    if claim:
        complete_idempotency(claim.record.pk, result_reference=str(record.pk))


@transaction.atomic
def create_draft_material_dispatch(*, actor=None, idempotency_key="", **values):
    work_order = (
        WorkOrder.objects.select_for_update()
        .select_related("vendor", "legal_entity")
        .get(pk=values["work_order"].pk)
    )
    _subcontract_work_order(work_order)
    dispatch_date = values["dispatch_date"]
    claim = _claim(
        "purchasing.dispatch.create",
        idempotency_key,
        {"work_order": str(work_order.pk), "date": dispatch_date.isoformat()},
        actor,
    )
    if claim and not claim.is_new:
        return SubcontractMaterialDispatch.objects.get(pk=claim.record.result_reference)
    allocation = allocate_document_number(
        work_order.legal_entity,
        "SUBCONTRACT_DISPATCH",
        business_date=dispatch_date,
        request_key=f"subdispatch:{idempotency_key}" if idempotency_key else "",
        actor=actor,
    )
    dispatch = SubcontractMaterialDispatch.objects.create(
        legal_entity=work_order.legal_entity,
        document_allocation=allocation,
        document_number=allocation.number,
        work_order=work_order,
        vendor=work_order.vendor,
        vendor_code_snapshot=work_order.vendor.code,
        vendor_name_snapshot=work_order.vendor.display_name,
        dispatch_date=dispatch_date,
        notes=str(values.get("notes") or "").strip(),
        created_by=actor,
    )
    _audit(dispatch, "purchasing.subdispatch.created", actor)
    _complete(claim, dispatch)
    return dispatch


@transaction.atomic
def add_dispatch_line(dispatch, *, allocation, quantity, notes="", actor=None):
    dispatch = SubcontractMaterialDispatch.objects.select_for_update().get(pk=dispatch.pk)
    _draft(dispatch)
    allocation = WorkOrderMaterialAllocation.objects.select_related("material_item__uom").get(
        pk=allocation.pk
    )
    if allocation.work_order_id != dispatch.work_order_id:
        raise ValidationError({"allocation": "Material allocation must belong to this SPK."})
    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise ValidationError({"quantity": "Dispatch quantity must be positive."})
    line_number = (
        dispatch.lines.aggregate(
            maximum=__import__("django.db.models", fromlist=["Max"]).Max("line_number")
        )["maximum"]
        or 0
    )
    line = SubcontractMaterialDispatchLine.objects.create(
        dispatch=dispatch,
        line_number=line_number + 1,
        allocation=allocation,
        material_item=allocation.material_item,
        material_code_snapshot=allocation.material_code_snapshot,
        material_name_snapshot=allocation.material_name_snapshot,
        uom_code_snapshot=allocation.uom_code_snapshot,
        quantity=quantity,
        reference_cost_snapshot=allocation.reference_cost,
        notes=str(notes or "").strip(),
    )
    _audit(line, "purchasing.subdispatchline.added", actor)
    return line


@transaction.atomic
def remove_dispatch_line(line, *, actor=None):
    line = (
        SubcontractMaterialDispatchLine.objects.select_for_update()
        .select_related("dispatch")
        .get(pk=line.pk)
    )
    _draft(line.dispatch)
    _audit(line, "purchasing.subdispatchline.removed", actor)
    line.delete()


@transaction.atomic
def confirm_material_dispatch(dispatch, *, actor=None, idempotency_key=""):
    dispatch = SubcontractMaterialDispatch.objects.select_for_update().get(pk=dispatch.pk)
    claim = _claim(
        "purchasing.dispatch.confirm", idempotency_key, {"dispatch": str(dispatch.pk)}, actor
    )
    if claim and not claim.is_new:
        return dispatch
    _draft(dispatch)
    lines = list(dispatch.lines.select_related("allocation"))
    if not lines:
        raise ValidationError("Kirim Bahan requires at least one line.")
    allocation_ids = [line.allocation_id for line in lines]
    allocations = {
        item.pk: item
        for item in WorkOrderMaterialAllocation.objects.select_for_update().filter(
            pk__in=allocation_ids
        )
    }
    active = (
        SubcontractMaterialDispatchLine.objects.filter(
            allocation_id__in=allocation_ids, dispatch__state=SubcontractDispatchState.CONFIRMED
        )
        .values("allocation_id")
        .annotate(total=Sum("quantity"))
    )
    totals = {item["allocation_id"]: item["total"] for item in active}
    for line in lines:
        if line.allocation_id not in allocations:
            raise ValidationError("Invalid material allocation.")
        if (
            totals.get(line.allocation_id, Decimal("0")) + line.quantity
            > allocations[line.allocation_id].planned_quantity
        ):
            raise ValidationError({"quantity": "Dispatch exceeds the remaining planned allowance."})
        totals[line.allocation_id] = totals.get(line.allocation_id, Decimal("0")) + line.quantity
    dispatch.state = SubcontractDispatchState.CONFIRMED
    dispatch.confirmed_by, dispatch.confirmed_at = actor, timezone.now()
    dispatch.save(update_fields=("state", "confirmed_by", "confirmed_at", "updated_at"))
    _audit(dispatch, "purchasing.subdispatch.confirmed", actor)
    _complete(claim, dispatch)
    return dispatch


@transaction.atomic
def cancel_material_dispatch(dispatch, *, reason, actor=None, idempotency_key=""):
    if not str(reason).strip():
        raise ValidationError({"reason": "Cancellation reason is required."})
    dispatch = SubcontractMaterialDispatch.objects.select_for_update().get(pk=dispatch.pk)
    claim = _claim(
        "purchasing.dispatch.cancel",
        idempotency_key,
        {"dispatch": str(dispatch.pk), "reason": str(reason).strip()},
        actor,
    )
    if claim and not claim.is_new:
        return dispatch
    if dispatch.state == SubcontractDispatchState.CANCELLED:
        raise ValidationError("Dispatch is already cancelled.")
    dispatch.state, dispatch.cancelled_by, dispatch.cancelled_at, dispatch.cancellation_reason = (
        SubcontractDispatchState.CANCELLED,
        actor,
        timezone.now(),
        str(reason).strip(),
    )
    dispatch.save(
        update_fields=("state", "cancelled_by", "cancelled_at", "cancellation_reason", "updated_at")
    )
    _audit(dispatch, "purchasing.subdispatch.cancelled", actor, reason)
    _complete(claim, dispatch)
    return dispatch


@transaction.atomic
def create_draft_subcontract_receipt(*, actor=None, idempotency_key="", **values):
    work_order = (
        WorkOrder.objects.select_for_update()
        .select_related("vendor", "legal_entity")
        .get(pk=values["work_order"].pk)
    )
    _subcontract_work_order(work_order)
    receipt_date = values["receipt_date"]
    claim = _claim(
        "purchasing.receipt.create",
        idempotency_key,
        {"work_order": str(work_order.pk), "date": receipt_date.isoformat()},
        actor,
    )
    if claim and not claim.is_new:
        return SubcontractReceipt.objects.get(pk=claim.record.result_reference)
    allocation = allocate_document_number(
        work_order.legal_entity,
        "SUBCONTRACT_RECEIPT",
        business_date=receipt_date,
        request_key=f"subreceipt:{idempotency_key}" if idempotency_key else "",
        actor=actor,
    )
    receipt = SubcontractReceipt.objects.create(
        legal_entity=work_order.legal_entity,
        document_allocation=allocation,
        document_number=allocation.number,
        work_order=work_order,
        vendor=work_order.vendor,
        vendor_code_snapshot=work_order.vendor.code,
        vendor_name_snapshot=work_order.vendor.display_name,
        receipt_date=receipt_date,
        notes=str(values.get("notes") or "").strip(),
        created_by=actor,
    )
    _audit(receipt, "purchasing.subreceipt.created", actor)
    _complete(claim, receipt)
    return receipt


@transaction.atomic
def add_receipt_output_line(receipt, *, output, accepted_quantity, notes="", actor=None):
    receipt = SubcontractReceipt.objects.select_for_update().get(pk=receipt.pk)
    _draft(receipt)
    if output.work_order_id != receipt.work_order_id:
        raise ValidationError({"output": "Output must belong to this SPK."})
    quantity = Decimal(str(accepted_quantity))
    if quantity <= 0:
        raise ValidationError({"accepted_quantity": "Accepted quantity must be positive."})
    line_number = receipt.output_lines.count() + 1
    line = SubcontractReceiptOutputLine.objects.create(
        receipt=receipt,
        line_number=line_number,
        output=output,
        item=output.item,
        item_code_snapshot=output.item_code_snapshot,
        item_name_snapshot=output.item_name_snapshot,
        uom_code_snapshot=output.uom_code_snapshot,
        accepted_quantity=quantity,
        notes=str(notes or "").strip(),
    )
    _audit(line, "purchasing.subreceiptoutput.added", actor)
    return line


@transaction.atomic
def remove_receipt_output_line(line, *, actor=None):
    line = (
        SubcontractReceiptOutputLine.objects.select_for_update()
        .select_related("receipt")
        .get(pk=line.pk)
    )
    _draft(line.receipt)
    _audit(line, "purchasing.subreceiptoutput.removed", actor)
    line.delete()


@transaction.atomic
def add_receipt_cost_line(receipt, *, cost_type, amount, output=None, notes="", actor=None):
    receipt = SubcontractReceipt.objects.select_for_update().get(pk=receipt.pk)
    _draft(receipt)
    if cost_type not in SubcontractCostType.values:
        raise ValidationError({"cost_type": "Unsupported subcontract cost type."})
    if cost_type == SubcontractCostType.SPECIFIC_SERVICE and (
        not output or output.work_order_id != receipt.work_order_id
    ):
        raise ValidationError({"output": "Specific service requires an output from this SPK."})
    if cost_type == SubcontractCostType.SHARED_SERVICE:
        output = None
    amount = Decimal(str(amount))
    if amount < 0:
        raise ValidationError({"amount": "Cost amount cannot be negative."})
    line = SubcontractReceiptCostLine.objects.create(
        receipt=receipt,
        line_number=receipt.cost_lines.count() + 1,
        cost_type=cost_type,
        output=output,
        amount=amount,
        notes=str(notes or "").strip(),
    )
    _audit(line, "purchasing.subreceiptcost.added", actor)
    return line


@transaction.atomic
def remove_receipt_cost_line(line, *, actor=None):
    line = (
        SubcontractReceiptCostLine.objects.select_for_update()
        .select_related("receipt")
        .get(pk=line.pk)
    )
    _draft(line.receipt)
    _audit(line, "purchasing.subreceiptcost.removed", actor)
    line.delete()


@transaction.atomic
def accept_subcontract_receipt(receipt, *, actor=None, idempotency_key=""):
    receipt = SubcontractReceipt.objects.select_for_update().get(pk=receipt.pk)
    claim = _claim(
        "purchasing.receipt.accept", idempotency_key, {"receipt": str(receipt.pk)}, actor
    )
    if claim and not claim.is_new:
        return receipt
    _draft(receipt)
    lines = list(receipt.output_lines.select_related("output"))
    if not lines:
        raise ValidationError("Terima Maklun requires at least one output line.")
    output_ids = [line.output_id for line in lines]
    outputs = {
        item.pk: item
        for item in WorkOrderOutput.objects.select_for_update().filter(pk__in=output_ids)
    }
    active = (
        SubcontractReceiptOutputLine.objects.filter(
            output_id__in=output_ids, receipt__state=SubcontractReceiptState.ACCEPTED
        )
        .values("output_id")
        .annotate(total=Sum("accepted_quantity"))
    )
    totals = {item["output_id"]: item["total"] for item in active}
    for line in lines:
        if (
            totals.get(line.output_id, Decimal("0")) + line.accepted_quantity
            > outputs[line.output_id].target_quantity
        ):
            raise ValidationError({"accepted_quantity": "Receipt exceeds remaining output target."})
        totals[line.output_id] = totals.get(line.output_id, Decimal("0")) + line.accepted_quantity
    receipt.state, receipt.accepted_by, receipt.accepted_at = (
        SubcontractReceiptState.ACCEPTED,
        actor,
        timezone.now(),
    )
    receipt.save(update_fields=("state", "accepted_by", "accepted_at", "updated_at"))
    _audit(receipt, "purchasing.subreceipt.accepted", actor)
    _complete(claim, receipt)
    return receipt


@transaction.atomic
def cancel_subcontract_receipt(receipt, *, reason, actor=None, idempotency_key=""):
    if not str(reason).strip():
        raise ValidationError({"reason": "Cancellation reason is required."})
    receipt = SubcontractReceipt.objects.select_for_update().get(pk=receipt.pk)
    claim = _claim(
        "purchasing.receipt.cancel",
        idempotency_key,
        {"receipt": str(receipt.pk), "reason": str(reason).strip()},
        actor,
    )
    if claim and not claim.is_new:
        return receipt
    if receipt.state == SubcontractReceiptState.CANCELLED:
        raise ValidationError("Receipt is already cancelled.")
    receipt.state, receipt.cancelled_by, receipt.cancelled_at, receipt.cancellation_reason = (
        SubcontractReceiptState.CANCELLED,
        actor,
        timezone.now(),
        str(reason).strip(),
    )
    receipt.save(
        update_fields=("state", "cancelled_by", "cancelled_at", "cancellation_reason", "updated_at")
    )
    _audit(receipt, "purchasing.subreceipt.cancelled", actor, reason)
    _complete(claim, receipt)
    return receipt
