from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import IdempotencyStatus
from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.core.services.numbering import allocate_document_number
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.organizations.models import LegalEntity
from apps.partners.models import BusinessPartner, PartnerRoleType
from apps.projects.models import (
    Project,
    ProjectBudgetLine,
    ProjectForecastLine,
    ProjectSalesOrder,
    ProjectState,
)
from apps.sales.models import SalesOrder

PROJECT_DOCUMENT_TYPE = "PROJECT"


def _text(value) -> str:
    return " ".join(str(value or "").split())


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _audit(instance, *, action, actor=None, reason="", before=None, metadata=None):
    after = model_snapshot(instance)
    record_audit_event(
        action=action,
        target_type=instance._meta.label_lower,
        target_id=instance.pk,
        actor=actor,
        source="projects.service",
        reason=reason,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after) if before else sorted(after),
        metadata=metadata or {},
    )


def _validate_customer(customer, entity, project_date):
    if customer.legal_entity_id != entity.id:
        raise ValidationError({"customer": "Customer must belong to the Project legal entity."})
    role = customer.roles.filter(
        role_type=PartnerRoleType.CUSTOMER,
        effective_from__lte=project_date,
    ).filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=project_date))
    if project_date >= timezone.localdate():
        role = role.filter(is_active=True)
    if not customer.is_effective_on(project_date) or not role.exists():
        raise ValidationError({"customer": "Project customer requires an effective CUSTOMER role."})


def _refresh_budget_total(project):
    project.budget_total = _money(
        project.budget_lines.filter(is_active=True).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )


def _assert_draft(project):
    if project.state != ProjectState.DRAFT:
        raise ValidationError("Only DRAFT Projects can edit commercial header fields.")


@transaction.atomic
def create_draft_project(*, actor=None, idempotency_key="", **values) -> Project:
    entity = LegalEntity.objects.select_for_update().get(pk=values["legal_entity"].pk)
    customer = BusinessPartner.objects.prefetch_related("roles").get(pk=values["customer"].pk)
    start_date = values["start_date"]
    _validate_customer(customer, entity, start_date)
    payload = {
        "entity": str(entity.pk),
        "customer": str(customer.pk),
        "start_date": start_date.isoformat(),
        "name": _text(values["name"]),
        "contract_reference": _text(values.get("contract_reference")),
    }
    if idempotency_key:
        claim = claim_idempotency(
            namespace="projects.create", key=idempotency_key, payload=payload, actor=actor
        )
        if not claim.is_new:
            if claim.record.status == IdempotencyStatus.COMPLETED and claim.record.result_reference:
                return Project.objects.get(pk=claim.record.result_reference)
            raise ValidationError("A prior Project creation request is still in progress.")
    else:
        claim = None
    allocation = allocate_document_number(
        entity,
        PROJECT_DOCUMENT_TYPE,
        business_date=start_date,
        request_key=f"project:{idempotency_key}" if idempotency_key else "",
        actor=actor,
    )
    project = Project(
        legal_entity=entity,
        document_allocation=allocation,
        code=allocation.number,
        name=_text(values["name"]),
        customer=customer,
        project_type=_text(values.get("project_type")),
        contract_reference=_text(values.get("contract_reference")),
        owner=values.get("owner"),
        start_date=start_date,
        target_date=values.get("target_date"),
        currency=_text(values.get("currency", entity.reporting_currency)).upper(),
        target_margin_percent=values.get("target_margin_percent"),
        notes=str(values.get("notes", "") or "").strip(),
        created_by=actor,
    )
    if len(project.currency) != 3:
        raise ValidationError({"currency": "Currency must be a three-letter code."})
    project.full_clean()
    project.save()
    _audit(project, action="projects.project.created", actor=actor)
    if claim:
        complete_idempotency(
            claim.record.pk,
            result_reference=str(project.pk),
            response={"project_id": str(project.pk), "project_code": project.code},
        )
    return project


@transaction.atomic
def update_draft_project(project, *, actor=None, reason="", **values) -> Project:
    locked = Project.objects.select_for_update().select_related("customer").get(pk=project.pk)
    _assert_draft(locked)
    before = model_snapshot(locked)
    if "start_date" in values and values["start_date"] != locked.start_date:
        raise ValidationError(
            {"start_date": "Project start date is immutable after number allocation."}
        )
    customer = values.get("customer", locked.customer)
    _validate_customer(customer, locked.legal_entity, locked.start_date)
    for field in (
        "name",
        "customer",
        "project_type",
        "contract_reference",
        "owner",
        "target_date",
        "currency",
        "target_margin_percent",
        "notes",
    ):
        if field in values:
            setattr(locked, field, values[field])
    locked.name = _text(locked.name)
    locked.project_type = _text(locked.project_type)
    locked.contract_reference = _text(locked.contract_reference)
    locked.currency = _text(locked.currency).upper()
    locked.notes = str(locked.notes or "").strip()
    locked.full_clean()
    locked.save()
    _audit(locked, action="projects.project.updated", actor=actor, reason=reason, before=before)
    return locked


@transaction.atomic
def activate_project(project, *, actor=None) -> Project:
    locked = Project.objects.select_for_update().get(pk=project.pk)
    if locked.state != ProjectState.DRAFT:
        raise ValidationError("Only DRAFT Projects can be activated.")
    before = model_snapshot(locked)
    locked.state = ProjectState.ACTIVE
    locked.activated_by = actor
    locked.activated_at = timezone.now()
    locked.save(update_fields=("state", "activated_by", "activated_at", "updated_at"))
    _audit(locked, action="projects.project.activated", actor=actor, before=before)
    return locked


@transaction.atomic
def hold_project(project, *, actor=None, reason="") -> Project:
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Hold reason is required."})
    locked = Project.objects.select_for_update().get(pk=project.pk)
    if locked.state != ProjectState.ACTIVE:
        raise ValidationError("Only ACTIVE Projects can be placed on hold.")
    before = model_snapshot(locked)
    locked.state = ProjectState.ON_HOLD
    locked.save(update_fields=("state", "updated_at"))
    _audit(locked, action="projects.project.held", actor=actor, reason=reason, before=before)
    return locked


@transaction.atomic
def release_project(project, *, actor=None, reason="") -> Project:
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Release reason is required."})
    locked = Project.objects.select_for_update().get(pk=project.pk)
    if locked.state != ProjectState.ON_HOLD:
        raise ValidationError("Only ON_HOLD Projects can be released.")
    before = model_snapshot(locked)
    locked.state = ProjectState.ACTIVE
    locked.save(update_fields=("state", "updated_at"))
    _audit(locked, action="projects.project.released", actor=actor, reason=reason, before=before)
    return locked


@transaction.atomic
def complete_project(project, *, actor=None, reason="") -> Project:
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Completion reason is required."})
    locked = Project.objects.select_for_update().get(pk=project.pk)
    if locked.state not in {ProjectState.ACTIVE, ProjectState.ON_HOLD}:
        raise ValidationError("Only ACTIVE or ON_HOLD Projects can be completed.")
    before = model_snapshot(locked)
    locked.state = ProjectState.COMPLETED
    locked.save(update_fields=("state", "updated_at"))
    _audit(locked, action="projects.project.completed", actor=actor, reason=reason, before=before)
    return locked


@transaction.atomic
def cancel_project(project, *, actor=None, reason="") -> Project:
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Cancellation reason is required."})
    locked = Project.objects.select_for_update().get(pk=project.pk)
    if locked.state not in {ProjectState.DRAFT, ProjectState.ACTIVE, ProjectState.ON_HOLD}:
        raise ValidationError("This Project cannot be cancelled from its current state.")
    before = model_snapshot(locked)
    locked.state = ProjectState.CANCELLED
    locked.cancelled_by = actor
    locked.cancelled_at = timezone.now()
    locked.save(update_fields=("state", "cancelled_by", "cancelled_at", "updated_at"))
    _audit(locked, action="projects.project.cancelled", actor=actor, reason=reason, before=before)
    return locked


@transaction.atomic
def link_sales_order(project, sales_order, *, actor=None, reason="") -> ProjectSalesOrder:
    locked = Project.objects.select_for_update().get(pk=project.pk)
    if locked.state in {ProjectState.COMPLETED, ProjectState.CANCELLED}:
        raise ValidationError("Completed or cancelled Projects cannot receive Sales Order links.")
    order = SalesOrder.objects.select_for_update().get(pk=sales_order.pk)
    if order.legal_entity_id != locked.legal_entity_id:
        raise ValidationError("Sales Order must belong to the Project legal entity.")
    if order.customer_id != locked.customer_id:
        raise ValidationError("Sales Order must belong to the Project customer.")
    if ProjectSalesOrder.objects.filter(sales_order=order).exists():
        raise ValidationError("Sales Order already has a primary Project link.")
    link = ProjectSalesOrder.objects.create(project=locked, sales_order=order, linked_by=actor)
    _audit(
        link,
        action="projects.projectsalesorder.linked",
        actor=actor,
        reason=reason,
        metadata={"project_id": str(locked.pk), "sales_order_id": str(order.pk)},
    )
    return link


@transaction.atomic
def unlink_sales_order(link, *, actor=None, reason=""):
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Unlink reason is required."})
    locked = ProjectSalesOrder.objects.select_for_update().select_related("project").get(pk=link.pk)
    if locked.project.state not in {ProjectState.DRAFT, ProjectState.ACTIVE, ProjectState.ON_HOLD}:
        raise ValidationError("This Project link cannot be removed from the current Project state.")
    before = model_snapshot(locked)
    target_id = locked.pk
    locked.delete()
    record_audit_event(
        action="projects.projectsalesorder.unlinked",
        target_type="projects.projectsalesorder",
        target_id=target_id,
        actor=actor,
        source="projects.service",
        reason=reason,
        before_state=before,
        changed_fields=sorted(before),
    )


def _validate_budget_dimensions(project, *, cost_center=None, purchase_category=None, item=None):
    for name, value in (
        ("cost_center", cost_center),
        ("purchase_category", purchase_category),
        ("item", item),
    ):
        if value is not None and value.legal_entity_id != project.legal_entity_id:
            raise ValidationError(
                {name: f"{name.replace('_', ' ').title()} must match the Project entity."}
            )


def _assert_budget_editable(project):
    if project.state not in {ProjectState.DRAFT, ProjectState.ACTIVE}:
        raise ValidationError("Project budgets can be changed only while DRAFT or ACTIVE.")


@transaction.atomic
def add_project_budget_line(project, *, actor=None, reason="", **values) -> ProjectBudgetLine:
    locked = Project.objects.select_for_update().get(pk=project.pk)
    _assert_budget_editable(locked)
    if locked.state == ProjectState.ACTIVE and not str(reason or "").strip():
        raise ValidationError(
            {"reason": "Budget revision reason is required for an ACTIVE Project."}
        )
    cost_center = values.get("cost_center")
    purchase_category = values.get("purchase_category")
    item = values.get("item")
    _validate_budget_dimensions(
        locked,
        cost_center=cost_center,
        purchase_category=purchase_category,
        item=item,
    )
    project_before = model_snapshot(locked)
    line = ProjectBudgetLine(
        project=locked,
        category=values["category"],
        description=_text(values["description"]),
        amount=_money(values["amount"]),
        cost_center=cost_center,
        purchase_category=purchase_category,
        item=item,
        notes=str(values.get("notes", "") or "").strip(),
    )
    line.full_clean()
    line.save()
    _refresh_budget_total(locked)
    locked.save(update_fields=("budget_total", "updated_at"))
    _audit(
        line,
        action="projects.projectbudgetline.created",
        actor=actor,
        reason=reason,
        metadata={"project_budget_total": str(locked.budget_total)},
    )
    _audit(
        locked,
        action="projects.project.budget_revised",
        actor=actor,
        reason=reason,
        before=project_before,
    )
    return line


@transaction.atomic
def update_project_budget_line(line, *, actor=None, reason="", **values) -> ProjectBudgetLine:
    locked_line = (
        ProjectBudgetLine.objects.select_for_update().select_related("project").get(pk=line.pk)
    )
    project = Project.objects.select_for_update().get(pk=locked_line.project_id)
    _assert_budget_editable(project)
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Budget revision reason is required."})
    before = model_snapshot(locked_line)
    for field in (
        "category",
        "description",
        "amount",
        "cost_center",
        "purchase_category",
        "item",
        "notes",
        "is_active",
    ):
        if field in values:
            setattr(locked_line, field, values[field])
    locked_line.description = _text(locked_line.description)
    locked_line.amount = _money(locked_line.amount)
    locked_line.notes = str(locked_line.notes or "").strip()
    _validate_budget_dimensions(
        project,
        cost_center=locked_line.cost_center,
        purchase_category=locked_line.purchase_category,
        item=locked_line.item,
    )
    locked_line.full_clean()
    locked_line.save()
    project_before = model_snapshot(project)
    _refresh_budget_total(project)
    project.save(update_fields=("budget_total", "updated_at"))
    _audit(
        locked_line,
        action="projects.projectbudgetline.updated",
        actor=actor,
        reason=reason,
        before=before,
    )
    _audit(
        project,
        action="projects.project.budget_revised",
        actor=actor,
        reason=reason,
        before=project_before,
    )
    return locked_line


@transaction.atomic
def remove_project_budget_line(line, *, actor=None, reason=""):
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Budget revision reason is required."})
    locked_line = (
        ProjectBudgetLine.objects.select_for_update().select_related("project").get(pk=line.pk)
    )
    project = Project.objects.select_for_update().get(pk=locked_line.project_id)
    _assert_budget_editable(project)
    before = model_snapshot(locked_line)
    project_before = model_snapshot(project)
    line_id = locked_line.pk
    locked_line.delete()
    _refresh_budget_total(project)
    project.save(update_fields=("budget_total", "updated_at"))
    record_audit_event(
        action="projects.projectbudgetline.removed",
        target_type="projects.projectbudgetline",
        target_id=line_id,
        actor=actor,
        source="projects.service",
        reason=reason,
        before_state=before,
        changed_fields=sorted(before),
    )
    _audit(
        project,
        action="projects.project.budget_revised",
        actor=actor,
        reason=reason,
        before=project_before,
    )


def _assert_forecast_editable(project: Project):
    if project.state not in {ProjectState.DRAFT, ProjectState.ACTIVE, ProjectState.ON_HOLD}:
        raise ValidationError(
            "Project forecast can be modified only while DRAFT, ACTIVE, or ON_HOLD."
        )


def _validate_forecast_dimensions(
    project: Project, *, cost_center=None, purchase_category=None, item=None
):
    for name, value in (
        ("cost_center", cost_center),
        ("purchase_category", purchase_category),
        ("item", item),
    ):
        if value is not None and value.legal_entity_id != project.legal_entity_id:
            raise ValidationError(
                {name: f"{name.replace('_', ' ').title()} must match the Project entity."}
            )


@transaction.atomic
def add_project_forecast_line(project, *, actor=None, reason="", **values) -> ProjectForecastLine:
    locked = Project.objects.select_for_update().get(pk=project.pk)
    _assert_forecast_editable(locked)
    if (
        locked.state in {ProjectState.ACTIVE, ProjectState.ON_HOLD}
        and not str(reason or "").strip()
    ):
        raise ValidationError(
            {"reason": "Forecast revision reason is required for an ACTIVE or ON_HOLD Project."}
        )
    cost_center = values.get("cost_center")
    purchase_category = values.get("purchase_category")
    item = values.get("item")
    _validate_forecast_dimensions(
        locked,
        cost_center=cost_center,
        purchase_category=purchase_category,
        item=item,
    )
    line = ProjectForecastLine(
        project=locked,
        category=values["category"],
        description=_text(values["description"]),
        amount=_money(values["amount"]),
        cost_center=cost_center,
        purchase_category=purchase_category,
        item=item,
        notes=str(values.get("notes", "") or "").strip(),
        is_active=values.get("is_active", True),
    )
    line.full_clean()
    line.save()
    _audit(
        line,
        action="projects.projectforecastline.created",
        actor=actor,
        reason=reason,
        metadata={"category": line.category, "amount": str(line.amount)},
    )
    return line


@transaction.atomic
def update_project_forecast_line(line, *, actor=None, reason="", **values) -> ProjectForecastLine:
    locked_line = (
        ProjectForecastLine.objects.select_for_update().select_related("project").get(pk=line.pk)
    )
    project = Project.objects.select_for_update().get(pk=locked_line.project_id)
    _assert_forecast_editable(project)
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Forecast revision reason is required."})
    before = model_snapshot(locked_line)
    for field in (
        "category",
        "description",
        "amount",
        "cost_center",
        "purchase_category",
        "item",
        "notes",
        "is_active",
    ):
        if field in values:
            setattr(locked_line, field, values[field])
    locked_line.description = _text(locked_line.description)
    locked_line.amount = _money(locked_line.amount)
    locked_line.notes = str(locked_line.notes or "").strip()
    _validate_forecast_dimensions(
        project,
        cost_center=locked_line.cost_center,
        purchase_category=locked_line.purchase_category,
        item=locked_line.item,
    )
    locked_line.full_clean()
    locked_line.save()
    _audit(
        locked_line,
        action="projects.projectforecastline.updated",
        actor=actor,
        reason=reason,
        before=before,
    )
    return locked_line


@transaction.atomic
def remove_project_forecast_line(line, *, actor=None, reason=""):
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Forecast revision reason is required."})
    locked_line = (
        ProjectForecastLine.objects.select_for_update().select_related("project").get(pk=line.pk)
    )
    project = Project.objects.select_for_update().get(pk=locked_line.project_id)
    _assert_forecast_editable(project)
    before = model_snapshot(locked_line)
    line_id = locked_line.pk
    locked_line.delete()
    record_audit_event(
        action="projects.projectforecastline.removed",
        target_type="projects.projectforecastline",
        target_id=line_id,
        actor=actor,
        source="projects.service",
        reason=reason,
        before_state=before,
        changed_fields=sorted(before),
    )
