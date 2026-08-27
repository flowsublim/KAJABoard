from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import IdempotencyStatus
from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.core.services.numbering import allocate_document_number
from apps.partners.models import PartnerRoleType
from apps.purchasing.models import (
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
        source="purchasing.work_order_service",
        reason=reason,
    )


def _draft(wo):
    if wo.state != WorkOrderState.DRAFT:
        raise ValidationError("Only DRAFT SPK can be edited.")


def _validate_lineage(sales, project, entity):
    if sales:
        if sales.legal_entity_id != entity.id:
            raise ValidationError({"sales_order": "Sales Order must match entity."})
        if sales.state != "CONFIRMED":
            raise ValidationError({"sales_order": "Sales Order must be CONFIRMED."})
    if project:
        if project.legal_entity_id != entity.id:
            raise ValidationError({"project": "Project must match entity."})
        if project.state != "ACTIVE":
            raise ValidationError({"project": "Project must be ACTIVE."})
    if sales and project and project.customer_id != sales.customer_id:
        raise ValidationError({"project": "Project customer must match Sales Order."})


def _vendor(vendor, entity, day):
    if not vendor or vendor.legal_entity_id != entity.id:
        raise ValidationError({"vendor": "Subcontract SPK requires a same-entity vendor."})
    roles = vendor.roles.filter(
        role_type__in=(PartnerRoleType.VENDOR, PartnerRoleType.SUBCONTRACTOR),
        effective_from__lte=day,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=day))
    if day >= timezone.localdate():
        roles = roles.filter(is_active=True)
    if not roles.exists():
        raise ValidationError({"vendor": "Vendor requires effective VENDOR or SUBCONTRACTOR role."})


@transaction.atomic
def create_draft_work_order(*, actor=None, idempotency_key="", **values):
    entity = (
        values["legal_entity"]
        .__class__.objects.select_for_update()
        .get(pk=values["legal_entity"].pk)
    )
    day = values["document_date"]
    typ = values["work_order_type"]
    vendor = values.get("vendor")
    if typ == WorkOrderType.SUBCONTRACT:
        _vendor(vendor, entity, day)
    if typ == WorkOrderType.INTERNAL and vendor:
        raise ValidationError({"vendor": "INTERNAL SPK must not have a vendor."})
    sales = values.get("sales_order")
    project = values.get("project")
    _validate_lineage(sales, project, entity)
    payload = {
        "entity": str(entity.pk),
        "document_date": day.isoformat(),
        "type": typ,
        "vendor": str(vendor.pk) if vendor else "",
        "sales_order": str(sales.pk) if sales else "",
        "project": str(project.pk) if project else "",
        "due_date": values.get("due_date").isoformat() if values.get("due_date") else "",
    }
    claim = None
    if idempotency_key:
        claim = claim_idempotency(
            namespace="purchasing.work_order.create",
            key=idempotency_key,
            payload=payload,
            actor=actor,
        )
        if not claim.is_new:
            if claim.record.status == IdempotencyStatus.COMPLETED and claim.record.result_reference:
                return WorkOrder.objects.get(pk=claim.record.result_reference)
            raise ValidationError("A prior SPK creation request is still in progress.")
    allocation = allocate_document_number(
        entity,
        "WORK_ORDER",
        business_date=day,
        request_key=f"work-order:{idempotency_key}" if idempotency_key else "",
        actor=actor,
    )
    wo = WorkOrder(
        legal_entity=entity,
        document_allocation=allocation,
        document_number=allocation.number,
        document_date=day,
        work_order_type=typ,
        vendor=vendor,
        sales_order=sales,
        project=project,
        due_date=values.get("due_date"),
        instructions=str(values.get("instructions", "") or "").strip(),
        notes=str(values.get("notes", "") or "").strip(),
        created_by=actor,
    )
    wo.full_clean()
    wo.save()
    _audit(wo, "purchasing.workorder.created", actor)
    if claim:
        complete_idempotency(
            claim.record.pk,
            result_reference=str(wo.pk),
            response={"work_order_id": str(wo.pk), "document_number": wo.document_number},
        )
    return wo


@transaction.atomic
def update_draft_work_order(wo, *, actor=None, **values):
    wo = WorkOrder.objects.select_for_update().get(pk=wo.pk)
    _draft(wo)
    work_order_type = values.get("work_order_type", wo.work_order_type)
    vendor = values.get("vendor", wo.vendor)
    sales = values.get("sales_order", wo.sales_order)
    project = values.get("project", wo.project)
    if work_order_type == WorkOrderType.SUBCONTRACT:
        _vendor(vendor, wo.legal_entity, wo.document_date)
    elif vendor:
        raise ValidationError({"vendor": "INTERNAL SPK must not have a vendor."})
    _validate_lineage(sales, project, wo.legal_entity)
    for field in (
        "work_order_type",
        "vendor",
        "sales_order",
        "project",
        "due_date",
        "instructions",
        "notes",
    ):
        if field in values:
            setattr(
                wo,
                field,
                str(values[field] or "").strip()
                if field in {"instructions", "notes"}
                else values[field],
            )
    wo.full_clean()
    wo.save()
    _audit(wo, "purchasing.workorder.updated", actor)
    return wo


@transaction.atomic
def add_work_order_output(wo, *, item, target_quantity, due_date=None, notes="", actor=None):
    wo = WorkOrder.objects.select_for_update().get(pk=wo.pk)
    _draft(wo)
    if item.legal_entity_id != wo.legal_entity_id or not item.is_effective_on(wo.document_date):
        raise ValidationError({"item": "Output Item is not effective for this SPK."})
    qty = Decimal(str(target_quantity))
    if qty <= 0:
        raise ValidationError({"target_quantity": "Target quantity must be positive."})
    line_number = (
        wo.outputs.order_by("-line_number").values_list("line_number", flat=True).first() or 0
    )
    out = WorkOrderOutput(
        work_order=wo,
        line_number=line_number + 1,
        item=item,
        item_code_snapshot=item.code,
        item_name_snapshot=item.name,
        uom_code_snapshot=item.uom.code,
        target_quantity=qty,
        due_date=due_date,
        notes=str(notes or "").strip(),
    )
    out.full_clean()
    out.save()
    _audit(out, "purchasing.workorderoutput.added", actor)
    return out


@transaction.atomic
def update_work_order_output(
    output, *, actor=None, target_quantity=None, due_date=None, notes=None
):
    output = (
        WorkOrderOutput.objects.select_for_update().select_related("work_order").get(pk=output.pk)
    )
    _draft(output.work_order)
    if target_quantity is not None:
        quantity = Decimal(str(target_quantity))
        if quantity <= 0:
            raise ValidationError({"target_quantity": "Target quantity must be positive."})
        output.target_quantity = quantity
    if due_date is not None:
        output.due_date = due_date
    if notes is not None:
        output.notes = str(notes or "").strip()
    output.full_clean()
    output.save()
    _audit(output, "purchasing.workorderoutput.updated", actor)
    return output


@transaction.atomic
def remove_work_order_output(output, *, actor=None):
    output = (
        WorkOrderOutput.objects.select_for_update().select_related("work_order").get(pk=output.pk)
    )
    _draft(output.work_order)
    if output.material_allocations.exists():
        raise ValidationError("Remove the output material allocations before removing this output.")
    _audit(output, "purchasing.workorderoutput.removed", actor)
    output.delete()


@transaction.atomic
def add_material_allocation(
    wo, *, output, material_item, planned_quantity, reference_cost=None, notes="", actor=None
):
    wo = WorkOrder.objects.select_for_update().get(pk=wo.pk)
    _draft(wo)
    if output.work_order_id != wo.id:
        raise ValidationError({"output": "Output must belong to the same SPK."})
    if material_item.legal_entity_id != wo.legal_entity_id or not material_item.is_effective_on(
        wo.document_date
    ):
        raise ValidationError({"material_item": "Material Item is not effective."})
    qty = Decimal(str(planned_quantity))
    if qty <= 0:
        raise ValidationError({"planned_quantity": "Material quantity must be positive."})
    cost = Decimal(str(reference_cost)) if reference_cost not in (None, "") else None
    if cost is not None and cost < 0:
        raise ValidationError({"reference_cost": "Reference cost cannot be negative."})
    line = WorkOrderMaterialAllocation(
        work_order=wo,
        output=output,
        material_item=material_item,
        material_code_snapshot=material_item.code,
        material_name_snapshot=material_item.name,
        uom_code_snapshot=material_item.uom.code,
        planned_quantity=qty,
        reference_cost=cost,
        notes=str(notes or "").strip(),
    )
    line.full_clean()
    line.save()
    _audit(line, "purchasing.workordermaterial.added", actor)
    return line


@transaction.atomic
def update_material_allocation(
    allocation, *, actor=None, planned_quantity=None, reference_cost=None, notes=None
):
    allocation = (
        WorkOrderMaterialAllocation.objects.select_for_update()
        .select_related("work_order")
        .get(pk=allocation.pk)
    )
    _draft(allocation.work_order)
    if planned_quantity is not None:
        quantity = Decimal(str(planned_quantity))
        if quantity <= 0:
            raise ValidationError({"planned_quantity": "Material quantity must be positive."})
        allocation.planned_quantity = quantity
    if reference_cost is not None:
        cost = Decimal(str(reference_cost)) if reference_cost != "" else None
        if cost is not None and cost < 0:
            raise ValidationError({"reference_cost": "Reference cost cannot be negative."})
        allocation.reference_cost = cost
    if notes is not None:
        allocation.notes = str(notes or "").strip()
    allocation.full_clean()
    allocation.save()
    _audit(allocation, "purchasing.workordermaterial.updated", actor)
    return allocation


@transaction.atomic
def remove_material_allocation(allocation, *, actor=None):
    allocation = (
        WorkOrderMaterialAllocation.objects.select_for_update()
        .select_related("work_order")
        .get(pk=allocation.pk)
    )
    _draft(allocation.work_order)
    _audit(allocation, "purchasing.workordermaterial.removed", actor)
    allocation.delete()


@transaction.atomic
def submit_work_order(wo, *, actor=None, idempotency_key=""):
    wo = WorkOrder.objects.select_for_update().get(pk=wo.pk)
    claim = _claim_action("submit", wo, idempotency_key, actor)
    if claim and not claim.is_new:
        return wo
    _draft(wo)
    if not wo.outputs.exists():
        raise ValidationError("SPK needs at least one output.")
    _validate_lineage(wo.sales_order, wo.project, wo.legal_entity)
    wo.state = WorkOrderState.SUBMITTED
    wo.submitted_by = actor
    wo.submitted_at = timezone.now()
    wo.save()
    _audit(wo, "purchasing.workorder.submitted", actor)
    _complete_action(claim, wo)
    return wo


@transaction.atomic
def approve_work_order(wo, *, actor=None, idempotency_key=""):
    wo = WorkOrder.objects.select_for_update().get(pk=wo.pk)
    claim = _claim_action("approve", wo, idempotency_key, actor)
    if claim and not claim.is_new:
        return wo
    if wo.state != WorkOrderState.SUBMITTED:
        raise ValidationError("Only SUBMITTED SPK can be approved.")
    if wo.work_order_type == WorkOrderType.SUBCONTRACT:
        _vendor(wo.vendor, wo.legal_entity, wo.document_date)
    _validate_lineage(wo.sales_order, wo.project, wo.legal_entity)
    wo.state = WorkOrderState.APPROVED
    wo.approved_by = actor
    wo.approved_at = timezone.now()
    wo.save()
    _audit(wo, "purchasing.workorder.approved", actor)
    _complete_action(claim, wo)
    return wo


@transaction.atomic
def void_work_order(wo, *, actor=None, reason="", idempotency_key=""):
    if not str(reason).strip():
        raise ValidationError({"reason": "Void reason is required."})
    wo = WorkOrder.objects.select_for_update().get(pk=wo.pk)
    claim = _claim_action("void", wo, idempotency_key, actor, {"reason": str(reason).strip()})
    if claim and not claim.is_new:
        return wo
    if wo.state == WorkOrderState.VOID:
        raise ValidationError("SPK is already void.")
    wo.state = WorkOrderState.VOID
    wo.voided_by = actor
    wo.voided_at = timezone.now()
    wo.save()
    _audit(wo, "purchasing.workorder.voided", actor, reason)
    _complete_action(claim, wo)
    return wo


def _claim_action(action, work_order, idempotency_key, actor, extra=None):
    if not idempotency_key:
        return None
    claim = claim_idempotency(
        namespace=f"purchasing.work_order.{action}",
        key=idempotency_key,
        payload={"work_order": str(work_order.pk), **(extra or {})},
        actor=actor,
    )
    if not claim.is_new:
        if claim.record.status != IdempotencyStatus.COMPLETED:
            raise ValidationError("A prior SPK action request is still in progress.")
        if claim.record.result_reference != str(work_order.pk):
            raise ValidationError("Idempotency key belongs to a different SPK.")
    return claim


def _complete_action(claim, work_order):
    if claim:
        complete_idempotency(claim.record.pk, result_reference=str(work_order.pk))
