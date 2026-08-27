from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import IdempotencyStatus
from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.production.models import (
    ProductionEntryState,
    ProductionRejectEntry,
    ProductionRejectLine,
    ProductionRejectLineReversal,
    ProductionStage,
    ProductionWorkEntry,
    ProductionWorkLine,
    ProductionWorkLineReversal,
)
from apps.production.selectors.wip import active_reject_lines, active_work_lines, output_wip
from apps.purchasing.models import WorkOrder, WorkOrderOutput, WorkOrderState, WorkOrderType


def _audit(obj, action, actor=None, *, reason="", before=None, after=None, key=""):
    record_audit_event(
        action=action,
        target_type=obj._meta.label_lower,
        target_id=obj.pk,
        actor=actor,
        source="production.service",
        reason=reason,
        before_state=before,
        after_state=after,
        idempotency_key=key,
    )


def _positive(value, field="quantity"):
    quantity = Decimal(str(value))
    if quantity <= 0:
        raise ValidationError({field: "Qty must be positive."})
    return quantity


def _eligible_work_order(work_order, entity):
    if work_order.legal_entity_id != entity.id:
        raise ValidationError("SPK must belong to the same legal entity.")
    if (
        work_order.work_order_type != WorkOrderType.INTERNAL
        or work_order.state != WorkOrderState.APPROVED
    ):
        raise ValidationError("Only APPROVED INTERNAL SPK may be used in Production.")


def _draft(entry):
    if entry.state != ProductionEntryState.DRAFT:
        raise ValidationError("Only DRAFT records can be edited.")


def _claim(namespace, key, payload, actor):
    if not key:
        raise ValidationError("Idempotency key is required for posting or correction.")
    return claim_idempotency(namespace=namespace, key=key, payload=payload, actor=actor)


def _line_payload(entry):
    return [
        {"id": str(line.pk), "quantity": str(line.quantity)}
        for line in entry.lines.order_by("sequence")
    ]


def _replay(claim, klass):
    if claim.is_new:
        return None
    if claim.record.status == IdempotencyStatus.COMPLETED and claim.record.result_reference:
        return klass.objects.get(pk=claim.record.result_reference)
    raise ValidationError("The same request is already in progress.")


def _lock_output(output_id):
    output = (
        WorkOrderOutput.objects.select_for_update()
        .select_related("work_order", "item", "work_order__legal_entity")
        .get(pk=output_id)
    )
    list(active_work_lines(output=output).select_for_update())
    list(active_reject_lines(output=output).select_for_update())
    return output


@transaction.atomic
def create_draft_work_entry(
    *, legal_entity, work_order, production_date, stage, notes="", actor=None
):
    entity = legal_entity.__class__.objects.select_for_update().get(pk=legal_entity.pk)
    order = WorkOrder.objects.select_for_update().get(pk=work_order.pk)
    _eligible_work_order(order, entity)
    entry = ProductionWorkEntry.objects.create(
        legal_entity=entity,
        work_order=order,
        production_date=production_date,
        stage=stage,
        notes=str(notes or "").strip(),
        created_by=actor,
    )
    _audit(entry, "production.work_draft.created", actor)
    return entry


@transaction.atomic
def update_draft_work_entry(entry, *, actor=None, production_date=None, stage=None, notes=None):
    entry = (
        ProductionWorkEntry.objects.select_for_update()
        .select_related("work_order", "legal_entity")
        .get(pk=entry.pk)
    )
    _draft(entry)
    _eligible_work_order(entry.work_order, entry.legal_entity)
    before = {
        "production_date": entry.production_date.isoformat(),
        "stage": entry.stage,
        "notes": entry.notes,
    }
    for field, value in (("production_date", production_date), ("stage", stage), ("notes", notes)):
        if value is not None:
            setattr(entry, field, str(value).strip() if field == "notes" else value)
    entry.full_clean()
    entry.save()
    _audit(
        entry,
        "production.work_draft.updated",
        actor,
        before=before,
        after={
            "production_date": entry.production_date.isoformat(),
            "stage": entry.stage,
            "notes": entry.notes,
        },
    )
    return entry


def _work_line_values(entry, output, quantity, sequence, notes):
    if output.work_order_id != entry.work_order_id:
        raise ValidationError({"output": "Output must belong to the entry SPK."})
    if output.work_order.legal_entity_id != entry.legal_entity_id:
        raise ValidationError({"output": "Output lineage is invalid."})
    return {
        "entry": entry,
        "output": output,
        "item": output.item,
        "item_code_snapshot": output.item_code_snapshot,
        "item_name_snapshot": output.item_name_snapshot,
        "uom_code_snapshot": output.uom_code_snapshot,
        "quantity": _positive(quantity),
        "sequence": sequence,
        "notes": str(notes or "").strip(),
    }


@transaction.atomic
def add_draft_work_line(entry, *, output, quantity, notes="", actor=None):
    entry = (
        ProductionWorkEntry.objects.select_for_update()
        .select_related("work_order__legal_entity")
        .get(pk=entry.pk)
    )
    _draft(entry)
    output = _lock_output(output.pk)
    next_sequence = (
        entry.lines.order_by("-sequence").values_list("sequence", flat=True).first() or 0
    )
    line = ProductionWorkLine.objects.create(
        **_work_line_values(entry, output, quantity, next_sequence + 1, notes)
    )
    _audit(line, "production.work_line.added", actor)
    return line


@transaction.atomic
def update_draft_work_line(line, *, output=None, quantity=None, notes=None, actor=None):
    line = (
        ProductionWorkLine.objects.select_for_update()
        .select_related("entry__work_order__legal_entity")
        .get(pk=line.pk)
    )
    _draft(line.entry)
    target = _lock_output((output or line.output).pk)
    before = {"output": str(line.output_id), "quantity": str(line.quantity), "notes": line.notes}
    values = _work_line_values(
        line.entry,
        target,
        quantity if quantity is not None else line.quantity,
        line.sequence,
        notes if notes is not None else line.notes,
    )
    for key, value in values.items():
        setattr(line, key, value)
    line.full_clean()
    line.save()
    _audit(
        line,
        "production.work_line.updated",
        actor,
        before=before,
        after={"output": str(line.output_id), "quantity": str(line.quantity), "notes": line.notes},
    )
    return line


@transaction.atomic
def remove_draft_work_line(line, *, actor=None):
    line = ProductionWorkLine.objects.select_for_update().select_related("entry").get(pk=line.pk)
    _draft(line.entry)
    _audit(line, "production.work_line.removed", actor)
    line.delete()


def _validate_work_post(entry):
    lines = list(
        entry.lines.select_related("output__work_order", "output__item").order_by("sequence")
    )
    if not lines:
        raise ValidationError("Work entry needs at least one output line.")
    grouped = defaultdict(Decimal)
    for line in lines:
        grouped[line.output_id] += line.quantity
    for output_id, requested in grouped.items():
        output = _lock_output(output_id)
        if output.work_order_id != entry.work_order_id:
            raise ValidationError("Output must belong to the entry SPK.")
        wip = output_wip(output)
        available = (
            wip.available_sewing
            if entry.stage == ProductionStage.SEW
            else wip.available_qc
            if entry.stage == ProductionStage.QC_PACKING
            else None
        )
        if available is not None and requested > available:
            raise ValidationError(
                f"{output.item_code_snapshot}: requested {requested} exceeds "
                f"available WIP {available}."
            )


@transaction.atomic
def post_work_entry(entry, *, actor=None, idempotency_key):
    entry = (
        ProductionWorkEntry.objects.select_for_update()
        .select_related("work_order", "legal_entity")
        .get(pk=entry.pk)
    )
    claim = _claim(
        "production.work.post",
        idempotency_key,
        {"entry": str(entry.pk), "lines": _line_payload(entry)},
        actor,
    )
    replay = _replay(claim, ProductionWorkEntry)
    if replay:
        return replay
    _draft(entry)
    _eligible_work_order(entry.work_order, entry.legal_entity)
    _validate_work_post(entry)
    entry.state = ProductionEntryState.POSTED
    entry.posted_by = actor
    entry.posted_at = timezone.now()
    entry.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    _audit(entry, "production.work.posted", actor, key=idempotency_key)
    complete_idempotency(
        claim.record.pk, result_reference=str(entry.pk), response={"entry_id": str(entry.pk)}
    )
    return entry


@transaction.atomic
def reverse_work_line(line, *, reason, actor=None, idempotency_key):
    if not str(reason).strip():
        raise ValidationError({"reason": "Correction reason is required."})
    line = (
        ProductionWorkLine.objects.select_for_update()
        .select_related("entry", "output__work_order")
        .get(pk=line.pk)
    )
    claim = _claim(
        "production.work_line.reverse",
        idempotency_key,
        {"line": str(line.pk), "reason": str(reason).strip()},
        actor,
    )
    replay = _replay(claim, ProductionWorkLineReversal)
    if replay:
        return replay
    if line.entry.state != ProductionEntryState.POSTED or hasattr(line, "reversal"):
        raise ValidationError("Only active POSTED work lines can be reversed.")
    output = _lock_output(line.output_id)
    wip = output_wip(output)
    remaining = {
        ProductionStage.CUT: wip.cut_quantity
        - line.quantity
        - wip.sew_quantity
        - wip.reject_cut_quantity,
        ProductionStage.SEW: wip.sew_quantity
        - line.quantity
        - wip.qc_quantity
        - wip.reject_sew_quantity,
        ProductionStage.QC_PACKING: wip.qc_quantity - line.quantity - wip.reject_qc_quantity,
    }[line.entry.stage]
    if remaining < 0:
        raise ValidationError("Reversal would make downstream WIP overconsumed.")
    reversal = ProductionWorkLineReversal.objects.create(
        original_line=line, reason=str(reason).strip(), reversed_by=actor
    )
    _audit(reversal, "production.work_line.reversed", actor, reason=reason, key=idempotency_key)
    complete_idempotency(
        claim.record.pk,
        result_reference=str(reversal.pk),
        response={"reversal_id": str(reversal.pk)},
    )
    return reversal


@transaction.atomic
def create_draft_reject_entry(*, legal_entity, work_order, production_date, notes="", actor=None):
    entity = legal_entity.__class__.objects.select_for_update().get(pk=legal_entity.pk)
    order = WorkOrder.objects.select_for_update().get(pk=work_order.pk)
    _eligible_work_order(order, entity)
    entry = ProductionRejectEntry.objects.create(
        legal_entity=entity,
        work_order=order,
        production_date=production_date,
        notes=str(notes or "").strip(),
        created_by=actor,
    )
    _audit(entry, "production.reject_draft.created", actor)
    return entry


@transaction.atomic
def update_draft_reject_entry(entry, *, actor=None, production_date=None, notes=None):
    entry = (
        ProductionRejectEntry.objects.select_for_update()
        .select_related("work_order", "legal_entity")
        .get(pk=entry.pk)
    )
    _draft(entry)
    _eligible_work_order(entry.work_order, entry.legal_entity)
    before = {"production_date": entry.production_date.isoformat(), "notes": entry.notes}
    if production_date is not None:
        entry.production_date = production_date
    if notes is not None:
        entry.notes = str(notes).strip()
    entry.full_clean()
    entry.save()
    _audit(
        entry,
        "production.reject_draft.updated",
        actor,
        before=before,
        after={"production_date": entry.production_date.isoformat(), "notes": entry.notes},
    )
    return entry


@transaction.atomic
def add_draft_reject_line(entry, *, output, stage, quantity, reason, notes="", actor=None):
    entry = (
        ProductionRejectEntry.objects.select_for_update()
        .select_related("work_order__legal_entity")
        .get(pk=entry.pk)
    )
    _draft(entry)
    if not str(reason).strip():
        raise ValidationError({"reason": "Reject reason is required."})
    output = _lock_output(output.pk)
    if output.work_order_id != entry.work_order_id:
        raise ValidationError({"output": "Output must belong to the entry SPK."})
    seq = entry.lines.order_by("-sequence").values_list("sequence", flat=True).first() or 0
    line = ProductionRejectLine.objects.create(
        entry=entry,
        output=output,
        stage=stage,
        quantity=_positive(quantity),
        reason=str(reason).strip(),
        notes=str(notes or "").strip(),
        sequence=seq + 1,
    )
    _audit(line, "production.reject_line.added", actor)
    return line


@transaction.atomic
def update_draft_reject_line(
    line, *, output=None, stage=None, quantity=None, reason=None, notes=None, actor=None
):
    line = ProductionRejectLine.objects.select_for_update().select_related("entry").get(pk=line.pk)
    _draft(line.entry)
    target = _lock_output((output or line.output).pk)
    if target.work_order_id != line.entry.work_order_id:
        raise ValidationError({"output": "Output must belong to the entry SPK."})
    if reason is not None and not str(reason).strip():
        raise ValidationError({"reason": "Reject reason is required."})
    before = {"quantity": str(line.quantity), "stage": line.stage, "reason": line.reason}
    line.output, line.stage, line.quantity, line.reason, line.notes = (
        target,
        stage or line.stage,
        _positive(quantity if quantity is not None else line.quantity),
        str(reason if reason is not None else line.reason).strip(),
        str(notes if notes is not None else line.notes).strip(),
    )
    line.full_clean()
    line.save()
    _audit(
        line,
        "production.reject_line.updated",
        actor,
        before=before,
        after={"quantity": str(line.quantity), "stage": line.stage, "reason": line.reason},
    )
    return line


@transaction.atomic
def remove_draft_reject_line(line, *, actor=None):
    line = ProductionRejectLine.objects.select_for_update().select_related("entry").get(pk=line.pk)
    _draft(line.entry)
    _audit(line, "production.reject_line.removed", actor)
    line.delete()


@transaction.atomic
def post_reject_entry(entry, *, actor=None, idempotency_key):
    entry = (
        ProductionRejectEntry.objects.select_for_update()
        .select_related("work_order", "legal_entity")
        .get(pk=entry.pk)
    )
    claim = _claim(
        "production.reject.post",
        idempotency_key,
        {"entry": str(entry.pk), "lines": _line_payload(entry)},
        actor,
    )
    replay = _replay(claim, ProductionRejectEntry)
    if replay:
        return replay
    _draft(entry)
    _eligible_work_order(entry.work_order, entry.legal_entity)
    lines = list(entry.lines.all())
    if not lines:
        raise ValidationError("Reject entry needs at least one line.")
    grouped = defaultdict(Decimal)
    for line in lines:
        grouped[(line.output_id, line.stage)] += line.quantity
    for (output_id, stage), requested in grouped.items():
        output = _lock_output(output_id)
        if output.work_order_id != entry.work_order_id:
            raise ValidationError("Output must belong to the entry SPK.")
        wip = output_wip(output)
        available = {
            ProductionStage.CUT: wip.cut_quantity - wip.sew_quantity - wip.reject_cut_quantity,
            ProductionStage.SEW: wip.sew_quantity - wip.qc_quantity - wip.reject_sew_quantity,
            ProductionStage.QC_PACKING: wip.qc_quantity - wip.reject_qc_quantity,
        }[stage]
        if requested > available:
            raise ValidationError(
                f"Reject requested {requested} exceeds available WIP {available}."
            )
    entry.state = ProductionEntryState.POSTED
    entry.posted_by = actor
    entry.posted_at = timezone.now()
    entry.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    _audit(entry, "production.reject.posted", actor, key=idempotency_key)
    complete_idempotency(
        claim.record.pk, result_reference=str(entry.pk), response={"entry_id": str(entry.pk)}
    )
    return entry


@transaction.atomic
def reverse_reject_line(line, *, reason, actor=None, idempotency_key):
    if not str(reason).strip():
        raise ValidationError({"reason": "Correction reason is required."})
    line = ProductionRejectLine.objects.select_for_update().select_related("entry").get(pk=line.pk)
    claim = _claim(
        "production.reject_line.reverse",
        idempotency_key,
        {"line": str(line.pk), "reason": str(reason).strip()},
        actor,
    )
    replay = _replay(claim, ProductionRejectLineReversal)
    if replay:
        return replay
    if line.entry.state != ProductionEntryState.POSTED or hasattr(line, "reversal"):
        raise ValidationError("Only active POSTED reject lines can be reversed.")
    _lock_output(line.output_id)
    reversal = ProductionRejectLineReversal.objects.create(
        original_line=line, reason=str(reason).strip(), reversed_by=actor
    )
    _audit(reversal, "production.reject_line.reversed", actor, reason=reason, key=idempotency_key)
    complete_idempotency(
        claim.record.pk,
        result_reference=str(reversal.pk),
        response={"reversal_id": str(reversal.pk)},
    )
    return reversal
