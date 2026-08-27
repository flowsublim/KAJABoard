from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.models import IdempotencyStatus
from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.production.models import (
    ProductionCostAllocationLine,
    ProductionCostAllocationRun,
    ProductionCostSnapshot,
    ProductionDirectExtraCost,
    ProductionDirectExtraCostReversal,
    ProductionEntryState,
    ProductionExtraCostCategory,
    ProductionHandoverState,
    ProductionLaborCost,
    ProductionLaborCostReversal,
    ProductionOverheadSnapshot,
    ProductionRejectEntry,
    ProductionRejectLine,
    ProductionRejectLineReversal,
    ProductionStage,
    ProductionTariff,
    ProductionWageMethod,
    ProductionWarehouseHandover,
    ProductionWarehouseHandoverLine,
    ProductionWarehouseHandoverLineReversal,
    ProductionWorkEntry,
    ProductionWorkLine,
    ProductionWorkLineReversal,
)
from apps.production.selectors.wip import (
    active_handover_lines,
    active_reject_lines,
    active_work_lines,
    output_wip,
)
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
    # Callers may hold a WorkOrder instance that predates an approval
    # transition performed by another service.  Always validate against the
    # current persisted state rather than a stale in-memory enum value.
    work_order.refresh_from_db(fields=("legal_entity", "work_order_type", "state"))
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
    list(active_handover_lines(output=output).select_for_update())
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
    if entry.wage_method == ProductionWageMethod.PIECE_RATE and not entry.employee_id:
        raise ValidationError({"employee": "PIC is required for PIECE_RATE."})
    if entry.employee_id and entry.employee.legal_entity_id != entry.legal_entity_id:
        raise ValidationError({"employee": "PIC must belong to the same legal entity."})
    for line in lines:
        if entry.wage_method == ProductionWageMethod.PIECE_RATE and not resolve_tariff(
            legal_entity=entry.legal_entity,
            stage=entry.stage,
            item=line.item,
            business_date=entry.production_date,
        ):
            raise ValidationError(
                f"Tarif produksi belum dikonfigurasi untuk {line.item_code_snapshot}."
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
    for line in entry.lines.select_related("output", "item"):
        tariff = resolve_tariff(
            legal_entity=entry.legal_entity,
            stage=entry.stage,
            item=line.item,
            business_date=entry.production_date,
        )
        rate = tariff.rate_per_unit if tariff else Decimal("0")
        ProductionLaborCost.objects.create(
            source_line=line,
            legal_entity=entry.legal_entity,
            work_order=entry.work_order,
            output=line.output,
            employee=entry.employee,
            employee_code_snapshot=entry.employee.employee_code if entry.employee else "",
            employee_name_snapshot=entry.employee.display_name if entry.employee else "",
            stage_snapshot=entry.stage,
            item_code_snapshot=line.item_code_snapshot,
            quantity_snapshot=line.quantity,
            wage_method=entry.wage_method,
            tariff=tariff,
            tariff_rate_snapshot=rate if tariff else None,
            amount=line.quantity * rate,
            production_date=entry.production_date,
        )
    _audit(entry, "production.work.posted", actor, key=idempotency_key)
    complete_idempotency(
        claim.record.pk, result_reference=str(entry.pk), response={"entry_id": str(entry.pk)}
    )
    return entry


def resolve_tariff(*, legal_entity, stage, item, business_date):
    return (
        ProductionTariff.objects.filter(
            legal_entity=legal_entity,
            stage=stage,
            item=item,
            wage_method=ProductionWageMethod.PIECE_RATE,
            is_active=True,
            effective_from__lte=business_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=business_date))
        .order_by("-effective_from")
        .first()
    )


@transaction.atomic
def create_tariff(*, actor=None, **values):
    if values["item"].legal_entity_id != values["legal_entity"].pk:
        raise ValidationError({"item": "Item must belong to the same legal entity."})
    start = values["effective_from"]
    end = values.get("effective_to")
    if end is not None and end < start:
        raise ValidationError({"effective_to": "Effective end must be on or after start."})
    if values["wage_method"] == ProductionWageMethod.NO_WAGE and values.get("rate_per_unit") != 0:
        raise ValidationError({"rate_per_unit": "NO_WAGE tariff rate must be zero."})
    qs = ProductionTariff.objects.filter(
        legal_entity=values["legal_entity"],
        stage=values["stage"],
        item=values["item"],
        wage_method=values["wage_method"],
        is_active=True,
        effective_from__lte=end or start,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=start))
    if qs.exists():
        raise ValidationError("Tarif aktif bertumpang tindih pada periode yang sama.")
    tariff = ProductionTariff.objects.create(**values)
    _audit(tariff, "production.tariff.created", actor)
    return tariff


@transaction.atomic
def update_tariff(tariff, *, actor=None, **changes):
    tariff = (
        ProductionTariff.objects.select_for_update()
        .select_related("legal_entity", "item")
        .get(pk=tariff.pk)
    )
    values = {
        "legal_entity": tariff.legal_entity,
        "stage": changes.get("stage", tariff.stage),
        "item": changes.get("item", tariff.item),
        "wage_method": changes.get("wage_method", tariff.wage_method),
        "effective_from": changes.get("effective_from", tariff.effective_from),
        "effective_to": changes.get("effective_to", tariff.effective_to),
    }
    # Reuse overlap rules while excluding the row being edited.
    if values["item"].legal_entity_id != tariff.legal_entity_id:
        raise ValidationError({"item": "Item must belong to the same legal entity."})
    if values["effective_to"] and values["effective_to"] < values["effective_from"]:
        raise ValidationError({"effective_to": "Effective end must be on or after start."})
    overlap = (
        ProductionTariff.objects.filter(
            legal_entity=tariff.legal_entity,
            stage=values["stage"],
            item=values["item"],
            wage_method=values["wage_method"],
            is_active=True,
            effective_from__lte=values["effective_to"] or values["effective_from"],
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=values["effective_from"]))
        .exclude(pk=tariff.pk)
    )
    if overlap.exists():
        raise ValidationError("Tarif aktif bertumpang tindih pada periode yang sama.")
    before = {field: str(getattr(tariff, field)) for field in changes}
    for field, value in changes.items():
        setattr(tariff, field, value)
    tariff.full_clean()
    tariff.save()
    _audit(tariff, "production.tariff.updated", actor, before=before)
    return tariff


@transaction.atomic
def create_direct_extra_cost(*, actor=None, **values):
    _eligible_work_order(values["work_order"], values["legal_entity"])
    if values["output"].work_order_id != values["work_order"].pk:
        raise ValidationError({"output": "Output must belong to the same SPK."})
    if values["output"].item.legal_entity_id != values["legal_entity"].pk:
        raise ValidationError({"output": "Output must belong to the same legal entity."})
    _positive(values["amount"], "amount")
    employee = values.get("employee")
    if employee and employee.legal_entity_id != values["legal_entity"].pk:
        raise ValidationError({"employee": "Payee must belong to the same legal entity."})
    if values["category"] == "OTHER_DIRECT" and not str(values.get("description", "")).strip():
        raise ValidationError({"description": "Explanation is required."})
    obj = ProductionDirectExtraCost.objects.create(created_by=actor, **values)
    _audit(obj, "production.extra_cost.created", actor)
    return obj


@transaction.atomic
def update_direct_extra_cost_draft(obj, *, actor=None, **changes):
    obj = (
        ProductionDirectExtraCost.objects.select_for_update()
        .select_related("work_order", "legal_entity", "output__item")
        .get(pk=obj.pk)
    )
    if obj.state != ProductionEntryState.DRAFT:
        raise ValidationError("Only DRAFT direct costs can be edited.")
    allowed = {"cost_date", "category", "employee", "description", "amount", "notes"}
    before = {field: str(getattr(obj, field)) for field in allowed if field in changes}
    for field, value in changes.items():
        if field in allowed:
            setattr(obj, field, value)
    if (
        obj.category == ProductionExtraCostCategory.OTHER_DIRECT
        and not str(obj.description).strip()
    ):
        raise ValidationError({"description": "Explanation is required."})
    _positive(obj.amount, "amount")
    if obj.employee and obj.employee.legal_entity_id != obj.legal_entity_id:
        raise ValidationError({"employee": "Payee must belong to the same legal entity."})
    obj.full_clean()
    obj.save()
    _audit(obj, "production.extra_cost.updated", actor, before=before)
    return obj


@transaction.atomic
def post_direct_extra_cost(obj, *, actor=None, idempotency_key):
    obj = ProductionDirectExtraCost.objects.select_for_update().get(pk=obj.pk)
    claim = _claim(
        "production.extra_cost.post",
        idempotency_key,
        {"id": str(obj.pk), "amount": str(obj.amount)},
        actor,
    )
    replay = _replay(claim, ProductionDirectExtraCost)
    if replay:
        return replay
    if obj.state != ProductionEntryState.DRAFT:
        raise ValidationError("Only DRAFT direct costs can be posted.")
    obj.state = ProductionEntryState.POSTED
    obj.posted_by = actor
    obj.posted_at = timezone.now()
    obj.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    _audit(obj, "production.extra_cost.posted", actor, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(obj.pk))
    return obj


@transaction.atomic
def reverse_direct_extra_cost(obj, *, reason, actor=None, idempotency_key):
    if not str(reason).strip():
        raise ValidationError({"reason": "Correction reason is required."})
    obj = ProductionDirectExtraCost.objects.select_for_update().get(pk=obj.pk)
    claim = _claim(
        "production.extra_cost.reverse",
        idempotency_key,
        {"id": str(obj.pk), "reason": str(reason).strip()},
        actor,
    )
    replay = _replay(claim, ProductionDirectExtraCostReversal)
    if replay:
        return replay
    if obj.state != ProductionEntryState.POSTED or obj.reversed_at:
        raise ValidationError("Only active POSTED direct cost can be reversed.")
    reversal = ProductionDirectExtraCostReversal.objects.create(
        original=obj, reason=str(reason).strip(), reversed_by=actor
    )
    obj.reversed_at = timezone.now()
    obj.save(update_fields=("reversed_at", "updated_at"))
    _audit(reversal, "production.extra_cost.reversed", actor, reason=reason, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(reversal.pk))
    return reversal


@transaction.atomic
def correct_direct_extra_cost(obj, *, reason, actor=None, idempotency_key, replacement_values=None):
    """Append-only reversal plus an explicit replacement source."""
    if not str(reason).strip():
        raise ValidationError({"reason": "Correction reason is required."})
    replacement_values = dict(replacement_values or {})
    payload = {
        "id": str(obj.pk),
        "reason": str(reason).strip(),
        "replacement": {key: str(value) for key, value in sorted(replacement_values.items())},
    }
    claim = _claim("production.extra_cost.correct", idempotency_key, payload, actor)
    replay = _replay(claim, ProductionDirectExtraCostReversal)
    if replay:
        return replay
    original = (
        ProductionDirectExtraCost.objects.select_for_update()
        .select_related("work_order", "legal_entity", "output", "employee")
        .get(pk=obj.pk)
    )
    if original.state != ProductionEntryState.POSTED or original.reversed_at:
        raise ValidationError("Only active POSTED direct cost can be corrected.")
    values = {
        "legal_entity": original.legal_entity,
        "work_order": original.work_order,
        "output": original.output,
        "cost_date": original.cost_date,
        "category": original.category,
        "employee": original.employee,
        "description": original.description,
        "amount": original.amount,
        "notes": original.notes,
    }
    values.update(replacement_values)
    replacement = create_direct_extra_cost(actor=actor, **values)
    replacement.state = ProductionEntryState.POSTED
    replacement.posted_by = actor
    replacement.posted_at = timezone.now()
    replacement.save(update_fields=("state", "posted_by", "posted_at", "updated_at"))
    original.reversed_at = timezone.now()
    original.save(update_fields=("reversed_at", "updated_at"))
    reversal = ProductionDirectExtraCostReversal.objects.create(
        original=original, replacement=replacement, reason=str(reason).strip(), reversed_by=actor
    )
    _audit(reversal, "production.extra_cost.corrected", actor, reason=reason, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(reversal.pk))
    return reversal


@transaction.atomic
def reverse_labor_cost(obj, *, reason, actor=None, idempotency_key):
    if not str(reason).strip():
        raise ValidationError({"reason": "Correction reason is required."})
    obj = ProductionLaborCost.objects.select_for_update().get(pk=obj.pk)
    claim = _claim(
        "production.labor.reverse",
        idempotency_key,
        {"id": str(obj.pk), "reason": str(reason).strip()},
        actor,
    )
    replay = _replay(claim, ProductionLaborCostReversal)
    if replay:
        return replay
    if obj.reversed_at:
        raise ValidationError("Only active labor cost can be reversed.")
    reversal = ProductionLaborCostReversal.objects.create(
        original=obj, reason=str(reason).strip(), reversed_by=actor
    )
    obj.reversed_at = timezone.now()
    obj.save(update_fields=("reversed_at", "updated_at"))
    _audit(reversal, "production.labor.reversed", actor, reason=reason, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(reversal.pk))
    return reversal


@transaction.atomic
def correct_labor_cost(obj, *, reason, actor=None, idempotency_key, replacement_values=None):
    if not str(reason).strip():
        raise ValidationError({"reason": "Correction reason is required."})
    replacement_values = dict(replacement_values or {})
    payload = {
        "id": str(obj.pk),
        "reason": str(reason).strip(),
        "replacement": {key: str(value) for key, value in sorted(replacement_values.items())},
    }
    claim = _claim("production.labor.correct", idempotency_key, payload, actor)
    replay = _replay(claim, ProductionLaborCostReversal)
    if replay:
        return replay
    original = (
        ProductionLaborCost.objects.select_for_update()
        .select_related("source_line", "legal_entity", "work_order", "output", "employee", "tariff")
        .get(pk=obj.pk)
    )
    if original.reversed_at:
        raise ValidationError("Only active labor cost can be corrected.")
    values = {
        "source_line": original.source_line,
        "legal_entity": original.legal_entity,
        "work_order": original.work_order,
        "output": original.output,
        "employee": original.employee,
        "employee_code_snapshot": original.employee_code_snapshot,
        "employee_name_snapshot": original.employee_name_snapshot,
        "stage_snapshot": original.stage_snapshot,
        "item_code_snapshot": original.item_code_snapshot,
        "quantity_snapshot": original.quantity_snapshot,
        "wage_method": original.wage_method,
        "tariff": original.tariff,
        "tariff_rate_snapshot": original.tariff_rate_snapshot,
        "amount": original.amount,
        "production_date": original.production_date,
    }
    values.update(replacement_values)
    replacement = ProductionLaborCost.objects.create(**values)
    original.reversed_at = timezone.now()
    original.save(update_fields=("reversed_at", "updated_at"))
    reversal = ProductionLaborCostReversal.objects.create(
        original=original, replacement=replacement, reason=str(reason).strip(), reversed_by=actor
    )
    _audit(reversal, "production.labor.corrected", actor, reason=reason, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(reversal.pk))
    return reversal


@transaction.atomic
def run_monthly_overhead_allocation(*, legal_entity, allocation_month, actor=None):
    sources = [
        source
        for source in ProductionOverheadSnapshot.objects.filter(
            legal_entity=legal_entity,
            posting_date__year=allocation_month.year,
            posting_date__month=allocation_month.month,
            source_status="POSTED",
            source_reversal_status="ACTIVE",
        )
        if (source.metadata_snapshot or {}).get("accounting_treatment") in {"EXPENSE", "SERVICE"}
        and (source.metadata_snapshot or {}).get("production_eligible") is True
        and (source.metadata_snapshot or {}).get("snapshot_production") is True
        and not (source.metadata_snapshot or {}).get("reversed")
    ]
    previous = (
        ProductionCostAllocationRun.objects.filter(
            legal_entity=legal_entity,
            allocation_month=allocation_month,
            status="READY",
        )
        .order_by("-created_at")
        .first()
    )
    run = ProductionCostAllocationRun.objects.create(
        legal_entity=legal_entity, allocation_month=allocation_month, supersedes=previous
    )
    cuts = (
        active_work_lines(stage=ProductionStage.CUT)
        .filter(
            entry__legal_entity=legal_entity,
            entry__production_date__year=allocation_month.year,
            entry__production_date__month=allocation_month.month,
        )
        .values("output")
        .annotate(quantity=Sum("quantity"))
    )
    total = sum((row["quantity"] for row in cuts), Decimal("0"))
    if not total:
        run.status = "BLOCKED_NO_DRIVER"
        run.save(update_fields=("status",))
        return run
    rows = list(cuts)
    for source in sources:
        remaining = source.amount
        for index, row in enumerate(rows):
            amount = (
                remaining
                if index == len(rows) - 1
                else (source.amount * row["quantity"] / total).quantize(Decimal("0.01"))
            )
            remaining -= amount
            ProductionCostAllocationLine.objects.create(
                run=run,
                source=source,
                output_id=row["output"],
                driver_quantity=row["quantity"],
                driver_total=total,
                ratio=row["quantity"] / total,
                source_amount=source.amount,
                allocated_amount=amount,
            )
    _audit(run, "production.overhead_allocation.run", actor)
    return run


@transaction.atomic
def capture_overhead_snapshot(*, actor=None, **values):
    """Capture only a trusted, already-posted production overhead source."""
    values = dict(values)
    metadata = dict(values.pop("metadata_snapshot", None) or {})
    values.pop("captured_by", None)
    treatment = metadata.get("accounting_treatment") or metadata.get("treatment")
    values.setdefault("category_snapshot", metadata.get("category", ""))
    values.setdefault("accounting_treatment_snapshot", treatment)
    values.setdefault("cost_center_snapshot", metadata.get("cost_center", ""))
    if treatment not in {"EXPENSE", "SERVICE"}:
        raise ValidationError("Only EXPENSE/SERVICE sources may become production overhead.")
    if not metadata.get("production_eligible") or not metadata.get("snapshot_production"):
        raise ValidationError("Source is not production-overhead eligible.")
    if (
        values.get("source_status") != "POSTED"
        or metadata.get("active") is False
        or metadata.get("reversed")
    ):
        raise ValidationError("Overhead source must be active and POSTED.")
    values = dict(values)
    values["metadata_snapshot"] = metadata
    snapshot = ProductionOverheadSnapshot.objects.create(**values, captured_by=actor)
    _audit(snapshot, "production.overhead_snapshot.captured", actor)
    return snapshot


@transaction.atomic
def build_cost_snapshot(*, output, as_of_date, actor=None, idempotency_key=None):
    claim = None
    if idempotency_key:
        claim = _claim(
            "production.cost_snapshot.build",
            idempotency_key,
            {"output": str(output.pk), "as_of_date": as_of_date.isoformat()},
            actor,
        )
        replay = _replay(claim, ProductionCostSnapshot)
        if replay:
            return replay
    version = (
        ProductionCostSnapshot.objects.filter(output=output)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    ) + 1
    labor = ProductionLaborCost.objects.filter(output=output, reversed_at__isnull=True).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")
    extra = ProductionDirectExtraCost.objects.filter(
        output=output, state=ProductionEntryState.POSTED, reversed_at__isnull=True
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    latest_run = (
        ProductionCostAllocationRun.objects.filter(
            legal_entity=output.work_order.legal_entity,
            status="READY",
            allocation_month__year=as_of_date.year,
            allocation_month__month=as_of_date.month,
        )
        .order_by("-created_at")
        .first()
    )
    overhead = (
        ProductionCostAllocationLine.objects.filter(output=output, run=latest_run).aggregate(
            total=Sum("allocated_amount")
        )["total"]
        if latest_run
        else None
    )
    overhead_status = "READY" if overhead is not None else "BLOCKED_OVERHEAD_SOURCE"
    snapshot = ProductionCostSnapshot.objects.create(
        work_order=output.work_order,
        output=output,
        version=version,
        as_of_date=as_of_date,
        material_amount=None,
        labor_amount=labor,
        direct_extra_amount=extra,
        overhead_amount=overhead,
        total_cogm=None,
        unit_hpp=None,
        status="INCOMPLETE",
        component_status={
            "material": "UNAVAILABLE_WAREHOUSE_ACTUAL",
            "labor": "READY",
            "direct_extra": "READY",
            "overhead": overhead_status,
        },
    )
    _audit(snapshot, "production.cost_snapshot.built", actor)
    if claim:
        complete_idempotency(claim.record.pk, result_reference=str(snapshot.pk))
    return snapshot


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
        ProductionStage.QC_PACKING: wip.qc_quantity
        - line.quantity
        - wip.reject_qc_quantity
        - wip.handover_quantity,
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
            ProductionStage.QC_PACKING: wip.qc_quantity
            - wip.reject_qc_quantity
            - wip.handover_quantity,
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


@transaction.atomic
def create_handover_draft(*, legal_entity, work_order, handover_date, notes="", actor=None):
    entity = legal_entity.__class__.objects.select_for_update().get(pk=legal_entity.pk)
    order = WorkOrder.objects.select_for_update().get(pk=work_order.pk)
    _eligible_work_order(order, entity)
    handover = ProductionWarehouseHandover.objects.create(
        legal_entity=entity,
        work_order=order,
        handover_date=handover_date,
        notes=str(notes or "").strip(),
        created_by=actor,
    )
    _audit(handover, "production.handover_draft.created", actor)
    return handover


@transaction.atomic
def update_handover_draft(handover, *, actor=None, handover_date=None, notes=None):
    handover = (
        ProductionWarehouseHandover.objects.select_for_update()
        .select_related("work_order", "legal_entity")
        .get(pk=handover.pk)
    )
    if handover.state != ProductionHandoverState.DRAFT:
        raise ValidationError("Only DRAFT handovers can be edited.")
    _eligible_work_order(handover.work_order, handover.legal_entity)
    before = {"handover_date": handover.handover_date.isoformat(), "notes": handover.notes}
    if handover_date is not None:
        handover.handover_date = handover_date
    if notes is not None:
        handover.notes = str(notes).strip()
    handover.full_clean()
    handover.save()
    _audit(
        handover,
        "production.handover_draft.updated",
        actor,
        before=before,
        after={"handover_date": handover.handover_date.isoformat(), "notes": handover.notes},
    )
    return handover


def _handover_line_values(handover, output, quantity, sequence, notes):
    if output.work_order_id != handover.work_order_id:
        raise ValidationError({"output": "Output must belong to the handover SPK."})
    if output.work_order.legal_entity_id != handover.legal_entity_id:
        raise ValidationError({"output": "Output legal entity is invalid."})
    return {
        "handover": handover,
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
def add_handover_line(handover, *, output, quantity, notes="", actor=None):
    handover = (
        ProductionWarehouseHandover.objects.select_for_update()
        .select_related("work_order", "legal_entity")
        .get(pk=handover.pk)
    )
    if handover.state != ProductionHandoverState.DRAFT:
        raise ValidationError("Only DRAFT handovers can be edited.")
    output = _lock_output(output.pk)
    sequence = handover.lines.order_by("-sequence").values_list("sequence", flat=True).first() or 0
    line = ProductionWarehouseHandoverLine.objects.create(
        **_handover_line_values(handover, output, quantity, sequence + 1, notes)
    )
    _audit(line, "production.handover_line.added", actor)
    return line


@transaction.atomic
def update_handover_line(line, *, output=None, quantity=None, notes=None, actor=None):
    line = (
        ProductionWarehouseHandoverLine.objects.select_for_update()
        .select_related("handover__work_order", "handover__legal_entity")
        .get(pk=line.pk)
    )
    if line.handover.state != ProductionHandoverState.DRAFT:
        raise ValidationError("Only DRAFT handover lines can be edited.")
    target = _lock_output((output or line.output).pk)
    before = {"output": str(line.output_id), "quantity": str(line.quantity), "notes": line.notes}
    values = _handover_line_values(
        line.handover,
        target,
        quantity if quantity is not None else line.quantity,
        line.sequence,
        notes if notes is not None else line.notes,
    )
    for field, value in values.items():
        setattr(line, field, value)
    line.full_clean()
    line.save()
    _audit(
        line,
        "production.handover_line.updated",
        actor,
        before=before,
        after={"output": str(line.output_id), "quantity": str(line.quantity), "notes": line.notes},
    )
    return line


@transaction.atomic
def remove_handover_line(line, *, actor=None):
    line = (
        ProductionWarehouseHandoverLine.objects.select_for_update()
        .select_related("handover")
        .get(pk=line.pk)
    )
    if line.handover.state != ProductionHandoverState.DRAFT:
        raise ValidationError("Only DRAFT handover lines can be removed.")
    _audit(line, "production.handover_line.removed", actor)
    line.delete()


@transaction.atomic
def mark_handover_ready(handover, *, actor=None, idempotency_key):
    handover = (
        ProductionWarehouseHandover.objects.select_for_update()
        .select_related("work_order", "legal_entity")
        .get(pk=handover.pk)
    )
    claim = _claim(
        "production.handover.ready",
        idempotency_key,
        {"handover": str(handover.pk), "lines": _line_payload(handover)},
        actor,
    )
    replay = _replay(claim, ProductionWarehouseHandover)
    if replay:
        return replay
    if handover.state != ProductionHandoverState.DRAFT:
        raise ValidationError("Only DRAFT handovers can be marked Siap Gudang.")
    _eligible_work_order(handover.work_order, handover.legal_entity)
    lines = list(handover.lines.select_related("output").order_by("sequence"))
    if not lines:
        raise ValidationError("Handover needs at least one output line.")
    requested_by_output = defaultdict(Decimal)
    for line in lines:
        requested_by_output[line.output_id] += line.quantity
    for output_id, requested in requested_by_output.items():
        output = _lock_output(output_id)
        if output.work_order_id != handover.work_order_id:
            raise ValidationError("Output must belong to the handover SPK.")
        available = output_wip(output).available_handover
        if requested > available:
            raise ValidationError(
                f"{output.item_code_snapshot}: requested {requested} exceeds "
                f"available handover WIP {available}."
            )
    handover.state = ProductionHandoverState.READY_FOR_GUDANG
    handover.ready_by = actor
    handover.ready_at = timezone.now()
    handover.save(update_fields=("state", "ready_by", "ready_at", "updated_at"))
    _audit(handover, "production.handover.ready", actor, key=idempotency_key)
    complete_idempotency(
        claim.record.pk,
        result_reference=str(handover.pk),
        response={"handover_id": str(handover.pk)},
    )
    return handover


@transaction.atomic
def reverse_handover_line(line, *, reason, actor=None, idempotency_key):
    if not str(reason).strip():
        raise ValidationError({"reason": "Correction reason is required."})
    line = (
        ProductionWarehouseHandoverLine.objects.select_for_update()
        .select_related("handover", "output")
        .get(pk=line.pk)
    )
    claim = _claim(
        "production.handover_line.reverse",
        idempotency_key,
        {"line": str(line.pk), "reason": str(reason).strip()},
        actor,
    )
    replay = _replay(claim, ProductionWarehouseHandoverLineReversal)
    if replay:
        return replay
    if line.handover.state != ProductionHandoverState.READY_FOR_GUDANG or hasattr(line, "reversal"):
        raise ValidationError("Only active Siap Gudang lines can be reversed.")
    _lock_output(line.output_id)
    # Phase 6 may inject a durable Warehouse-result guard here before reversal.
    reversal = ProductionWarehouseHandoverLineReversal.objects.create(
        original_line=line,
        reason=str(reason).strip(),
        reversed_by=actor,
    )
    _audit(
        reversal,
        "production.handover_line.reversed",
        actor,
        reason=reason,
        key=idempotency_key,
    )
    complete_idempotency(
        claim.record.pk,
        result_reference=str(reversal.pk),
        response={"reversal_id": str(reversal.pk)},
    )
    return reversal
