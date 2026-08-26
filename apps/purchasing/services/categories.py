from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.services.audit import record_audit_event
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.organizations.models import LegalEntity
from apps.purchasing.models import AccountingTreatment, PurchaseCategory


def _normalize_code(value: str) -> str:
    return " ".join(str(value or "").split()).upper()


def _normalize(values):
    normalized = values.copy()
    for field in (
        "code",
        "name",
        "inventory_classification",
        "asset_class_reference",
        "default_accounting_mapping_key",
        "notes",
    ):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = " ".join(value.split()) if field != "notes" else value.strip()
    if "code" in normalized:
        normalized["code_normalized"] = _normalize_code(normalized["code"])
    if "accounting_treatment" in normalized:
        normalized["accounting_treatment"] = str(normalized["accounting_treatment"]).upper()
    return normalized


def _validate_category(category: PurchaseCategory, *, exclude_pk=None):
    if not category.code_normalized:
        raise ValidationError({"code": "Purchase Category code is required."})
    if category.cost_center and category.cost_center.legal_entity_id != category.legal_entity_id:
        raise ValidationError({"cost_center": "Cost Center must belong to the same legal entity."})
    if (
        category.accounting_treatment
        in {
            AccountingTreatment.EXPENSE,
            AccountingTreatment.SERVICE,
        }
        and not category.cost_center
    ):
        raise ValidationError({"cost_center": "EXPENSE and SERVICE require a Cost Center."})
    if category.snapshot_production:
        if category.accounting_treatment not in {
            AccountingTreatment.EXPENSE,
            AccountingTreatment.SERVICE,
        }:
            raise ValidationError(
                {"snapshot_production": "Production snapshot is allowed only for EXPENSE/SERVICE."}
            )
        if not category.cost_center:
            raise ValidationError(
                {"cost_center": "Production snapshot requires an eligible Cost Center."}
            )
        if not category.cost_center.is_production_overhead_eligible:
            raise ValidationError(
                {"cost_center": "Cost Center is not production-overhead eligible."}
            )
    if category.cost_center:
        if category.effective_from < category.cost_center.effective_from:
            raise ValidationError({"cost_center": "Cost Center must cover the category period."})
        if category.cost_center.effective_to and (
            category.effective_to is None
            or category.effective_to > category.cost_center.effective_to
        ):
            raise ValidationError({"cost_center": "Cost Center must cover the category period."})
    overlaps = PurchaseCategory.objects.filter(
        legal_entity=category.legal_entity,
        code_normalized=category.code_normalized,
    )
    if exclude_pk:
        overlaps = overlaps.exclude(pk=exclude_pk)
    overlaps = overlaps.filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=category.effective_from)
    )
    if category.effective_to:
        overlaps = overlaps.filter(effective_from__lte=category.effective_to)
    if overlaps.exists():
        raise ValidationError(
            {"effective_from": "Purchase Category versions cannot overlap for the same code."}
        )
    category.full_clean()


def _audit(instance, *, action, actor, reason, idempotency_key, before=None):
    after = model_snapshot(instance)
    record_audit_event(
        action=action,
        target_type=instance._meta.label_lower,
        target_id=instance.pk,
        actor=actor,
        source="purchasing.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after) if before else sorted(after),
    )


@transaction.atomic
def create_purchase_category(*, actor=None, reason="", idempotency_key="", **values):
    values = _normalize(values)
    entity = LegalEntity.objects.select_for_update().get(pk=values["legal_entity"].pk)
    values["legal_entity"] = entity
    category = PurchaseCategory(**values)
    _validate_category(category)
    category.save()
    _audit(
        category,
        action="purchasing.purchasecategory.created",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    return category


@transaction.atomic
def update_purchase_category(category, *, actor=None, reason="", idempotency_key="", **values):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to edit a Purchase Category."})
    LegalEntity.objects.select_for_update().get(pk=category.legal_entity_id)
    locked = PurchaseCategory.objects.select_for_update().get(pk=category.pk)
    normalized = _normalize(values)
    stable_fields = {"legal_entity", "code"}
    for field in stable_fields:
        if field in normalized:
            current = getattr(locked, f"{field}_id" if field == "legal_entity" else field)
            incoming = normalized[field].pk if field == "legal_entity" else normalized[field]
            if current != incoming:
                raise ValidationError("Legal entity and code are stable category identity fields.")
    semantic_fields = {
        "accounting_treatment",
        "cost_center",
        "inventory_classification",
        "asset_class_reference",
        "snapshot_production",
        "default_accounting_mapping_key",
        "effective_from",
    }
    if locked.effective_from <= timezone.localdate() and any(
        field in normalized and getattr(locked, field) != normalized[field]
        for field in semantic_fields
    ):
        raise ValidationError(
            "An effective Purchase Category cannot change historical meaning; "
            "end it and create a new version."
        )
    before = model_snapshot(locked)
    for field, value in normalized.items():
        setattr(locked, field, value)
    _validate_category(locked, exclude_pk=locked.pk)
    locked.save()
    _audit(
        locked,
        action="purchasing.purchasecategory.updated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked


@transaction.atomic
def deactivate_purchase_category(category, *, actor=None, reason: str, idempotency_key=""):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to deactivate master data."})
    LegalEntity.objects.select_for_update().get(pk=category.legal_entity_id)
    locked = PurchaseCategory.objects.select_for_update().get(pk=category.pk)
    if not locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = False
    locked.effective_to = max(timezone.localdate(), locked.effective_from)
    locked.full_clean()
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    _audit(
        locked,
        action="purchasing.purchasecategory.deactivated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked


@transaction.atomic
def reactivate_purchase_category(category, *, actor=None, reason: str, idempotency_key=""):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to reactivate master data."})
    LegalEntity.objects.select_for_update().get(pk=category.legal_entity_id)
    locked = PurchaseCategory.objects.select_for_update().get(pk=category.pk)
    if locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = True
    locked.effective_to = None
    _validate_category(locked, exclude_pk=locked.pk)
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    _audit(
        locked,
        action="purchasing.purchasecategory.reactivated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked
