from collections import defaultdict
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import IdempotencyStatus
from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.quality.models import (
    InspectionType,
    QualityDocumentState,
    QualityInspection,
    QualityInspectionLine,
    QualityInspectionLineReversal,
    QualityReason,
    QualityResult,
)

ZERO = Decimal("0")


def _audit(obj, action, actor=None, *, reason="", key="", before=None, after=None, changed=None):
    record_audit_event(
        action=action,
        target_type=obj._meta.label_lower,
        target_id=obj.pk,
        actor=actor,
        source="quality.service",
        reason=reason,
        idempotency_key=key,
        before_state=before,
        after_state=after,
        changed_fields=changed or [],
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


def _decimal(value, field):
    try:
        value = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError) as error:
        raise ValidationError({field: "Quantity must be numeric."}) from error
    if value < ZERO:
        raise ValidationError({field: "Quantity cannot be negative."})
    return value


def _line_quantities(
    *, qty_inspected, qty_pass, qty_hold, qty_reject, qty_rework, qty_legacy=0, result=""
):
    values = {
        "qty_inspected": _decimal(qty_inspected, "qty_inspected"),
        "qty_pass": _decimal(qty_pass, "qty_pass"),
        "qty_hold": _decimal(qty_hold, "qty_hold"),
        "qty_reject": _decimal(qty_reject, "qty_reject"),
        "qty_rework": _decimal(qty_rework, "qty_rework"),
        "qty_legacy_unmapped": _decimal(qty_legacy, "qty_legacy_unmapped"),
    }
    canonical_total = sum(
        (values[key] for key in ("qty_pass", "qty_hold", "qty_reject", "qty_rework")), ZERO
    )
    if result == QualityResult.LEGACY_UNMAPPED:
        if canonical_total:
            raise ValidationError("LEGACY_UNMAPPED cannot contain a canonical disposition.")
        if values["qty_legacy_unmapped"] != values["qty_inspected"]:
            raise ValidationError("Legacy-unmapped quantity must equal inspected quantity.")
    else:
        if values["qty_legacy_unmapped"]:
            raise ValidationError("Legacy-unmapped quantity is import-only.")
        if canonical_total != values["qty_inspected"]:
            raise ValidationError("PASS + HOLD + REJECT + REWORK must equal inspected quantity.")
    return values


def _derived_result(values):
    if values["qty_legacy_unmapped"]:
        return QualityResult.LEGACY_UNMAPPED
    active = [
        result
        for result, field in (
            (QualityResult.PASS, "qty_pass"),
            (QualityResult.HOLD, "qty_hold"),
            (QualityResult.REJECT, "qty_reject"),
            (QualityResult.REWORK, "qty_rework"),
        )
        if values[field]
    ]
    return active[0] if len(active) == 1 else ""


def _validate_legacy_result_source(inspection, result, qty_legacy):
    if result == QualityResult.LEGACY_UNMAPPED or qty_legacy:
        if inspection.source_module.strip().lower() not in {"legacy", "migration", "data_exchange"}:
            raise ValidationError(
                "LEGACY_UNMAPPED is restricted to imported or migrated legacy evidence."
            )


def _validate_inspector(inspector, entity):
    if inspector is None:
        raise ValidationError({"inspector": "Inspector is required before posting."})
    if inspector.legal_entity_id != entity.pk or not inspector.is_active:
        raise ValidationError("Inspector must be active and belong to the legal entity.")


def _validate_reason(line):
    needs_reason = bool(line.qty_hold or line.qty_reject or line.qty_rework)
    if needs_reason and not (line.reason_code_snapshot or line.reason_text.strip()):
        raise ValidationError({"reason_text": "HOLD, REJECT, and REWORK require a reason."})
    if line.reason_code_snapshot:
        reason = (
            QualityReason.objects.filter(
                code=line.reason_code_snapshot,
                active=True,
            )
            .filter(Q(legal_entity=line.inspection.legal_entity) | Q(legal_entity__isnull=True))
            .first()
        )
        if reason is None:
            raise ValidationError(
                {"reason_code_snapshot": "Unknown or inactive Quality reason code."}
            )
        if reason.applies_to_result not in {
            line.result,
            QualityResult.HOLD,
            QualityResult.REJECT,
            QualityResult.REWORK,
        }:
            raise ValidationError({"reason_code_snapshot": "Reason code does not apply to result."})


def _validate_source_line(line, inspection):
    if not line.source_line_id:
        raise ValidationError({"source_line_id": "Stable source line identity is required."})
    if inspection.inspection_type == InspectionType.PRODUCTION_FINISHED_GOODS:
        if line.production_handover_line_id is None:
            raise ValidationError("Production finished-goods inspection requires a handover line.")
        source = line.production_handover_line
        if source.pk.__str__() != line.source_line_id:
            raise ValidationError(
                "Source line identity does not match the Production handover line."
            )
        if source.handover.legal_entity_id != inspection.legal_entity_id:
            raise ValidationError("Source and inspection legal entities must match.")
        if source.item_id != line.item_id or source.output_id != line.work_order_output_id:
            raise ValidationError("Item/output linkage does not match the Production source line.")
        from apps.production.models import ProductionWarehouseHandoverLineReversal

        if ProductionWarehouseHandoverLineReversal.objects.filter(original_line=source).exists():
            raise ValidationError("Reversed Production handover lines cannot be inspected.")
    elif inspection.inspection_type == InspectionType.SUBCONTRACT_RECEIPT:
        if line.subcontract_receipt_line_id is None:
            raise ValidationError("Subcontract inspection requires an exact receipt line.")
        source = line.subcontract_receipt_line
        source.receipt.refresh_from_db(fields=("state", "legal_entity_id"))
        if source.receipt.state != "ACCEPTED":
            raise ValidationError("Only ACCEPTED subcontract receipt lines can be inspected.")
        if (
            str(source.pk) != line.source_line_id
            or source.receipt.legal_entity_id != inspection.legal_entity_id
        ):
            raise ValidationError("Source line identity or legal entity is invalid.")
        if source.item_id != line.item_id or source.output_id != line.work_order_output_id:
            raise ValidationError("Item/output linkage does not match the subcontract source line.")


@transaction.atomic
def create_inspection(
    *,
    legal_entity,
    inspection_type,
    source_module,
    source_type,
    source_document_id,
    source_key,
    inspection_date,
    inspector=None,
    warehouse=None,
    notes="",
    evidence_reference="",
    evidence_metadata=None,
    actor=None,
):
    if inspector is None and actor is not None:
        inspector = getattr(actor, "employee_profile", None)
    if not source_key:
        raise ValidationError({"source_key": "Stable source key is required."})
    if inspector is not None and inspector.legal_entity_id != legal_entity.pk:
        raise ValidationError("Inspector and inspection legal entities must match.")
    if warehouse is not None and warehouse.legal_entity_id != legal_entity.pk:
        raise ValidationError("Warehouse and inspection legal entities must match.")
    inspection = QualityInspection.objects.create(
        legal_entity=legal_entity,
        inspection_type=inspection_type,
        source_module=source_module,
        source_type=source_type,
        source_document_id=str(source_document_id),
        source_key=source_key,
        inspection_date=inspection_date,
        inspector=inspector,
        warehouse=warehouse,
        notes=str(notes or "").strip(),
        evidence_reference=str(evidence_reference or "").strip(),
        evidence_metadata=evidence_metadata or {},
        created_by=actor,
    )
    _audit(inspection, "quality.inspection_draft.created", actor)
    return inspection


@transaction.atomic
def create_from_production_handover(
    handover_line,
    *,
    inspector=None,
    actor=None,
    inspection_date=None,
    notes="",
    source_key=None,
):
    from apps.production.models import ProductionHandoverState, ProductionWarehouseHandoverLine
    from apps.quality.selectors import quality_pass_authorization

    source = (
        ProductionWarehouseHandoverLine.objects.select_for_update()
        .select_related("handover", "handover__legal_entity", "output", "item")
        .get(pk=handover_line.pk)
    )
    if source.handover.state != ProductionHandoverState.READY_FOR_GUDANG:
        raise ValidationError("Only READY_FOR_GUDANG handover lines can enter Quality.")
    auth = quality_pass_authorization(source)
    pending = auth["pending_inspection_quantity"]
    if pending <= ZERO:
        raise ValidationError("This handover line has no pending inspection quantity.")
    inspection = create_inspection(
        legal_entity=source.handover.legal_entity,
        inspection_type=InspectionType.PRODUCTION_FINISHED_GOODS,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
        source_document_id=source.handover_id,
        source_key=source_key or f"QUALITY|PROD_HANDOVER|{source.pk}|{uuid4()}",
        inspection_date=inspection_date or timezone.localdate(),
        inspector=inspector,
        notes=notes,
        actor=actor,
    )
    return add_inspection_line(
        inspection,
        source_line_id=str(source.pk),
        production_handover_line=source,
        work_order_output=source.output,
        item=source.item,
        qty_presented=pending,
        qty_inspected=ZERO,
        qty_pass=ZERO,
        qty_hold=ZERO,
        qty_reject=ZERO,
        qty_rework=ZERO,
        actor=actor,
    ).inspection


@transaction.atomic
def add_inspection_line(
    inspection,
    *,
    source_line_id,
    item,
    qty_presented,
    qty_inspected=0,
    qty_pass=0,
    qty_hold=0,
    qty_reject=0,
    qty_rework=0,
    qty_legacy_unmapped=0,
    result="",
    production_handover_line=None,
    subcontract_receipt_line=None,
    work_order_output=None,
    uom_code_snapshot=None,
    reason_code_snapshot="",
    reason_text="",
    reason=None,
    notes="",
    actor=None,
):
    inspection = QualityInspection.objects.select_for_update().get(pk=inspection.pk)
    if inspection.state != QualityDocumentState.DRAFT:
        raise ValidationError("Only DRAFT inspections can be edited.")
    presented = _decimal(qty_presented, "qty_presented")
    if (
        inspection.inspection_type == InspectionType.PRODUCTION_FINISHED_GOODS
        and production_handover_line is None
    ):
        from apps.production.models import ProductionWarehouseHandoverLine

        try:
            production_handover_line = ProductionWarehouseHandoverLine.objects.select_related(
                "output", "item", "handover"
            ).get(pk=source_line_id)
        except (ProductionWarehouseHandoverLine.DoesNotExist, ValueError):
            raise ValidationError("Production handover line is required for this source.") from None
        work_order_output = work_order_output or production_handover_line.output
    if (
        inspection.inspection_type == InspectionType.SUBCONTRACT_RECEIPT
        and subcontract_receipt_line is None
    ):
        from apps.purchasing.models import SubcontractReceiptOutputLine

        try:
            subcontract_receipt_line = SubcontractReceiptOutputLine.objects.select_related(
                "output", "item", "receipt"
            ).get(pk=source_line_id)
        except (SubcontractReceiptOutputLine.DoesNotExist, ValueError):
            raise ValidationError("Subcontract receipt line is required for this source.") from None
        work_order_output = work_order_output or subcontract_receipt_line.output
    values = _line_quantities(
        qty_inspected=qty_inspected,
        qty_pass=qty_pass,
        qty_hold=qty_hold,
        qty_reject=qty_reject,
        qty_rework=qty_rework,
        qty_legacy=qty_legacy_unmapped,
        result=result,
    )
    _validate_legacy_result_source(inspection, result, values["qty_legacy_unmapped"])
    if values["qty_inspected"] > presented:
        raise ValidationError(
            {"qty_inspected": "Inspected quantity cannot exceed presented quantity."}
        )
    line = QualityInspectionLine.objects.create(
        inspection=inspection,
        source_line_id=str(source_line_id),
        production_handover_line=production_handover_line,
        subcontract_receipt_line=subcontract_receipt_line,
        work_order_output=work_order_output,
        item=item,
        qty_presented=presented,
        **values,
        uom_code_snapshot=uom_code_snapshot or item.uom.code,
        result=result,
        reason_code_snapshot=str(reason_code_snapshot or "").strip(),
        reason_text=str(reason if reason is not None else reason_text or "").strip(),
        notes=str(notes or "").strip(),
        sequence=(
            inspection.lines.order_by("-sequence").values_list("sequence", flat=True).first() or 0
        )
        + 1,
    )
    _validate_source_line(line, inspection)
    _audit(line, "quality.inspection_line.added", actor)
    return line


@transaction.atomic
def update_draft_line(line, *, actor=None, **changes):
    line = (
        QualityInspectionLine.objects.select_for_update()
        .select_related(
            "inspection",
            "item",
            "production_handover_line__handover",
            "subcontract_receipt_line__receipt",
        )
        .get(pk=line.pk)
    )
    if line.inspection.state != QualityDocumentState.DRAFT:
        raise ValidationError("Only DRAFT inspection lines can be edited.")
    if "reason" in changes:
        changes["reason_text"] = changes.pop("reason")
    allowed = {
        "qty_presented",
        "qty_inspected",
        "qty_pass",
        "qty_hold",
        "qty_reject",
        "qty_rework",
        "qty_legacy_unmapped",
        "result",
        "reason_code_snapshot",
        "reason_text",
        "notes",
    }
    unknown = set(changes) - allowed
    if unknown:
        raise ValidationError(f"Unsupported draft line fields: {', '.join(sorted(unknown))}.")
    before = {field: str(getattr(line, field)) for field in allowed if hasattr(line, field)}
    for field, value in changes.items():
        setattr(line, field, value)
    line.qty_presented = _decimal(line.qty_presented, "qty_presented")
    values = _line_quantities(
        qty_inspected=line.qty_inspected,
        qty_pass=line.qty_pass,
        qty_hold=line.qty_hold,
        qty_reject=line.qty_reject,
        qty_rework=line.qty_rework,
        qty_legacy=line.qty_legacy_unmapped,
        result=line.result,
    )
    _validate_legacy_result_source(line.inspection, line.result, values["qty_legacy_unmapped"])
    if values["qty_inspected"] > line.qty_presented:
        raise ValidationError(
            {"qty_inspected": "Inspected quantity cannot exceed presented quantity."}
        )
    for field, value in values.items():
        setattr(line, field, value)
    line.reason_code_snapshot = str(line.reason_code_snapshot or "").strip()
    line.reason_text = str(line.reason_text or "").strip()
    line.result = _derived_result(values) if line.qty_inspected else ""
    line.full_clean()
    _validate_source_line(line, line.inspection)
    line.save()
    _audit(
        line, "quality.inspection_line.draft_updated", actor, before=before, changed=list(changes)
    )
    return line


@transaction.atomic
def remove_draft_line(line, *, actor=None):
    line = (
        QualityInspectionLine.objects.select_for_update()
        .select_related("inspection")
        .get(pk=line.pk)
    )
    if line.inspection.state != QualityDocumentState.DRAFT:
        raise ValidationError("Only DRAFT inspection lines can be removed.")
    _audit(line, "quality.inspection_line.draft_removed", actor)
    line.delete()


def _lock_production_sources(lines):
    from apps.production.models import ProductionWarehouseHandoverLine

    source_ids = {
        line.production_handover_line_id for line in lines if line.production_handover_line_id
    }
    return {
        source.pk: source
        for source in ProductionWarehouseHandoverLine.objects.select_for_update()
        .select_related("handover")
        .filter(pk__in=source_ids)
    }


def _validate_posted_source_capacity(inspection, lines):
    from apps.quality.selectors import quality_disposition_totals

    sources = _lock_production_sources(lines)
    requested = defaultdict(Decimal)
    presented = defaultdict(Decimal)
    subcontract_sources = {}
    for line in lines:
        _validate_source_line(line, inspection)
        values = _line_quantities(
            qty_inspected=line.qty_inspected,
            qty_pass=line.qty_pass,
            qty_hold=line.qty_hold,
            qty_reject=line.qty_reject,
            qty_rework=line.qty_rework,
            qty_legacy=line.qty_legacy_unmapped,
            result=line.result,
        )
        _validate_legacy_result_source(inspection, line.result, values["qty_legacy_unmapped"])
        if line.qty_inspected <= ZERO:
            raise ValidationError("Every posted Quality line must inspect a positive quantity.")
        if line.qty_inspected > line.qty_presented:
            raise ValidationError("Inspected quantity cannot exceed presented quantity.")
        line.result = _derived_result(values)
        _validate_reason(line)
        if line.production_handover_line_id:
            requested[line.production_handover_line_id] += line.qty_inspected
            presented[line.production_handover_line_id] += line.qty_presented
        if line.subcontract_receipt_line_id:
            subcontract_sources[line.subcontract_receipt_line_id] = line.subcontract_receipt_line
    for source_id, source in sources.items():
        if source.handover.state != "READY_FOR_GUDANG" or hasattr(source, "reversal"):
            raise ValidationError("Only active READY_FOR_GUDANG handover lines can be inspected.")
        existing = quality_disposition_totals(handover_line=source)["inspected_quantity"]
        if existing + requested[source_id] > source.quantity:
            raise ValidationError(
                "Quality inspection exceeds remaining handover quantity "
                f"for source line {source.pk}."
            )
        if existing + presented[source_id] > source.quantity:
            raise ValidationError(
                "Presented Quality quantity exceeds remaining handover quantity "
                f"for source line {source.pk}."
            )
        if presented[source_id] > source.quantity - existing:
            raise ValidationError(
                "Presented quantity exceeds remaining handover quantity "
                f"for source line {source.pk}."
            )
    for source_id, source in subcontract_sources.items():
        existing = quality_disposition_totals(subcontract_receipt_line=source)["inspected_quantity"]
        requested_qty = sum(
            (line.qty_inspected for line in lines if line.subcontract_receipt_line_id == source_id),
            ZERO,
        )
        presented_qty = sum(
            (line.qty_presented for line in lines if line.subcontract_receipt_line_id == source_id),
            ZERO,
        )
        if existing + requested_qty > source.accepted_quantity:
            raise ValidationError(
                "Quality inspection exceeds remaining subcontract receipt quantity."
            )
        if presented_qty > source.accepted_quantity - existing:
            raise ValidationError(
                "Presented quantity exceeds remaining subcontract receipt quantity."
            )


@transaction.atomic
def post_inspection(inspection, *, actor=None, idempotency_key):
    inspection = (
        QualityInspection.objects.select_for_update()
        .select_related("legal_entity", "inspector")
        .get(pk=inspection.pk)
    )
    claim = _claim(
        "quality.inspection.post", idempotency_key, {"inspection": str(inspection.pk)}, actor
    )
    replay = _replay(claim, QualityInspection)
    if replay:
        return replay
    if inspection.state != QualityDocumentState.DRAFT:
        raise ValidationError("Only DRAFT inspections can be posted.")
    lines = list(
        inspection.lines.select_for_update()
        .select_related("item", "item__uom", "production_handover_line", "subcontract_receipt_line")
        .order_by("sequence")
    )
    if not lines:
        raise ValidationError("Inspection needs at least one line.")
    _validate_inspector(inspection.inspector, inspection.legal_entity)
    _validate_posted_source_capacity(inspection, lines)
    for line in lines:
        line.result = _derived_result(
            {
                "qty_pass": line.qty_pass,
                "qty_hold": line.qty_hold,
                "qty_reject": line.qty_reject,
                "qty_rework": line.qty_rework,
                "qty_legacy_unmapped": line.qty_legacy_unmapped,
            }
        )
        line.save(update_fields=("result", "updated_at"))
    inspection.inspector_code_snapshot = inspection.inspector.employee_code
    inspection.inspector_name_snapshot = inspection.inspector.display_name
    inspection.state = QualityDocumentState.POSTED
    inspection.posted_by = actor
    inspection.posted_at = timezone.now()
    inspection.save(
        update_fields=(
            "state",
            "posted_by",
            "posted_at",
            "inspector_code_snapshot",
            "inspector_name_snapshot",
            "updated_at",
        )
    )
    _audit(inspection, "quality.inspection.posted", actor, key=idempotency_key)
    complete_idempotency(
        claim.record.pk,
        result_reference=str(inspection.pk),
        response={"inspection_id": str(inspection.pk)},
    )
    return inspection


def _warehouse_consumed(handover_line):
    from apps.warehouse.selectors import posted_production_receipt_quantity

    return posted_production_receipt_quantity(handover_line)


@transaction.atomic
def reverse_inspection(inspection, *, reason, actor=None, idempotency_key):
    reason = str(reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Correction/reversal reason is required."})
    inspection = QualityInspection.objects.select_for_update().get(pk=inspection.pk)
    claim = _claim(
        "quality.inspection.reverse",
        idempotency_key,
        {"inspection": str(inspection.pk), "reason": reason},
        actor,
    )
    replay = _replay(claim, QualityInspection)
    if replay:
        return replay
    if inspection.state != QualityDocumentState.POSTED:
        raise ValidationError("Only POSTED inspections can be reversed.")
    lines = list(
        inspection.lines.filter(reversal__isnull=True).select_related("production_handover_line")
    )
    for line in lines:
        if line.production_handover_line_id and line.qty_pass:
            consumed = _warehouse_consumed(line.production_handover_line)
            if consumed:
                record_audit_event(
                    action="quality.inspection.reversal_blocked_downstream",
                    target_type=inspection._meta.label_lower,
                    target_id=inspection.pk,
                    actor=actor,
                    source="quality.service",
                    reason=reason,
                    idempotency_key=idempotency_key,
                    metadata={
                        "line_id": str(line.pk),
                        "warehouse_accepted_quantity": str(consumed),
                    },
                )
                raise ValidationError(
                    "Quality reversal is blocked: Warehouse has already consumed PASS quantity. "
                    "Reverse or adjust the Warehouse receipt first."
                )
        QualityInspectionLineReversal.objects.create(
            original_line=line, reason=reason, reversed_by=actor
        )
    inspection.state = QualityDocumentState.REVERSED
    inspection.reversed_by = actor
    inspection.reversed_at = timezone.now()
    inspection.reversal_reason = reason
    inspection.save(
        update_fields=("state", "reversed_by", "reversed_at", "reversal_reason", "updated_at")
    )
    _audit(inspection, "quality.inspection.reversed", actor, reason=reason, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(inspection.pk))
    return inspection


@transaction.atomic
def reverse_inspection_line(line, *, reason, actor=None, idempotency_key):
    reason = str(reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Correction reason is required."})
    line = (
        QualityInspectionLine.objects.select_for_update()
        .select_related("inspection", "production_handover_line")
        .get(pk=line.pk)
    )
    claim = _claim(
        "quality.inspection_line.reverse",
        idempotency_key,
        {"line": str(line.pk), "reason": reason},
        actor,
    )
    replay = _replay(claim, QualityInspectionLineReversal)
    if replay:
        return replay
    if line.inspection.state != QualityDocumentState.POSTED or hasattr(line, "reversal"):
        raise ValidationError("Only active lines on a POSTED inspection can be reversed.")
    if (
        line.production_handover_line_id
        and line.qty_pass
        and _warehouse_consumed(line.production_handover_line)
    ):
        raise ValidationError(
            "Quality line reversal is blocked: Warehouse has already consumed PASS quantity."
        )
    reversal = QualityInspectionLineReversal.objects.create(
        original_line=line, reason=reason, reversed_by=actor
    )
    _audit(reversal, "quality.inspection_line.reversed", actor, reason=reason, key=idempotency_key)
    complete_idempotency(claim.record.pk, result_reference=str(reversal.pk))
    return reversal


@transaction.atomic
def replace_inspection_line(
    line, *, replacement_inspection, replacement_values, reason, actor=None, idempotency_key
):
    """Append a replacement inspection line after reversing the original line."""
    reverse_inspection_line(line, reason=reason, actor=actor, idempotency_key=idempotency_key)
    replacement = add_inspection_line(replacement_inspection, actor=actor, **replacement_values)
    QualityInspectionLineReversal.objects.filter(original_line=line).update(
        replacement_line=replacement
    )
    return replacement
