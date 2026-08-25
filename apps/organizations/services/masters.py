from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.services.audit import record_audit_event
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.organizations.models import BusinessUnit, CostCenter, Department, LegalEntity, Warehouse

OrganizationMaster = LegalEntity | BusinessUnit | Department | CostCenter | Warehouse


def _normalize_fields(values: dict[str, object]) -> dict[str, object]:
    normalized = values.copy()
    for field in ("code", "country_code", "reporting_currency", "npwp", "nitku"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = (
                "".join(value.split()).upper()
                if field in {"npwp", "nitku"}
                else value.strip().upper()
            )
    for field in ("name", "display_name", "document_name", "timezone"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = value.strip()
    return normalized


def _validate_organization_links(instance: OrganizationMaster) -> None:
    legal_entity_id = getattr(instance, "legal_entity_id", None)
    business_unit = getattr(instance, "business_unit", None)
    department = getattr(instance, "department", None)
    parent = getattr(instance, "parent", None)

    if business_unit and business_unit.legal_entity_id != legal_entity_id:
        raise ValidationError(
            {"business_unit": "Business unit must belong to the same legal entity."}
        )
    if department and department.legal_entity_id != legal_entity_id:
        raise ValidationError({"department": "Department must belong to the same legal entity."})
    if isinstance(instance, Department) and parent:
        if parent.legal_entity_id != legal_entity_id:
            raise ValidationError(
                {"parent": "Parent department must belong to the same legal entity."}
            )
        cursor = parent
        seen = {instance.pk}
        while cursor:
            if cursor.pk in seen:
                raise ValidationError({"parent": "Department hierarchy cannot contain a cycle."})
            seen.add(cursor.pk)
            cursor = cursor.parent


def _create(model_class, *, actor, reason: str, idempotency_key: str, values: dict):
    instance = model_class(**_normalize_fields(values))
    _validate_organization_links(instance)
    instance.full_clean()
    instance.save()
    after = model_snapshot(instance)
    record_audit_event(
        action=f"{instance._meta.label_lower}.created",
        target_type=instance._meta.label_lower,
        target_id=instance.pk,
        actor=actor,
        source="organizations.service",
        reason=reason,
        idempotency_key=idempotency_key,
        after_state=after,
        changed_fields=sorted(after),
    )
    return instance


def _update(
    instance: OrganizationMaster, *, actor, reason: str, idempotency_key: str, values: dict
):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to edit master data."})
    locked = type(instance).objects.select_for_update().get(pk=instance.pk)
    before = model_snapshot(locked)
    for field, value in _normalize_fields(values).items():
        setattr(locked, field, value)
    _validate_organization_links(locked)
    locked.full_clean()
    locked.save()
    after = model_snapshot(locked)
    record_audit_event(
        action=f"{locked._meta.label_lower}.updated",
        target_type=locked._meta.label_lower,
        target_id=locked.pk,
        actor=actor,
        source="organizations.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    return locked


@transaction.atomic
def create_legal_entity(*, actor=None, reason: str = "", idempotency_key: str = "", **values):
    return _create(
        LegalEntity, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def update_legal_entity(
    instance, *, actor=None, reason: str = "", idempotency_key: str = "", **values
):
    return _update(
        instance, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def create_business_unit(*, actor=None, reason: str = "", idempotency_key: str = "", **values):
    return _create(
        BusinessUnit, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def update_business_unit(
    instance, *, actor=None, reason: str = "", idempotency_key: str = "", **values
):
    return _update(
        instance, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def create_department(*, actor=None, reason: str = "", idempotency_key: str = "", **values):
    return _create(
        Department, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def update_department(
    instance, *, actor=None, reason: str = "", idempotency_key: str = "", **values
):
    return _update(
        instance, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def create_cost_center(*, actor=None, reason: str = "", idempotency_key: str = "", **values):
    return _create(
        CostCenter, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def update_cost_center(
    instance, *, actor=None, reason: str = "", idempotency_key: str = "", **values
):
    return _update(
        instance, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def create_warehouse(*, actor=None, reason: str = "", idempotency_key: str = "", **values):
    return _create(
        Warehouse, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def update_warehouse(
    instance, *, actor=None, reason: str = "", idempotency_key: str = "", **values
):
    return _update(
        instance, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def deactivate_master(
    instance: OrganizationMaster,
    *,
    actor=None,
    reason: str,
    effective_to=None,
    idempotency_key: str = "",
):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to deactivate master data."})
    locked = type(instance).objects.select_for_update().get(pk=instance.pk)
    if not locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = False
    end_date = effective_to or timezone.localdate()
    if end_date < locked.effective_from:
        end_date = locked.effective_from
    locked.effective_to = end_date
    locked.full_clean()
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    after = model_snapshot(locked)
    record_audit_event(
        action=f"{locked._meta.label_lower}.deactivated",
        target_type=locked._meta.label_lower,
        target_id=locked.pk,
        actor=actor,
        source="organizations.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    return locked


@transaction.atomic
def reactivate_master(
    instance: OrganizationMaster,
    *,
    actor=None,
    reason: str,
    idempotency_key: str = "",
):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to reactivate master data."})
    locked = type(instance).objects.select_for_update().get(pk=instance.pk)
    if locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = True
    locked.effective_to = None
    locked.full_clean()
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    after = model_snapshot(locked)
    record_audit_event(
        action=f"{locked._meta.label_lower}.reactivated",
        target_type=locked._meta.label_lower,
        target_id=locked.pk,
        actor=actor,
        source="organizations.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    return locked
