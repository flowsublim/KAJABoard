from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import UOM, Item, ItemCategory
from apps.core.services.audit import record_audit_event
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.partners.models import PartnerRoleType
from apps.partners.selectors import effective_partner_roles

CatalogMaster = UOM | ItemCategory | Item


def _normalize(values: dict[str, object]) -> dict[str, object]:
    normalized = values.copy()
    for field in ("code", "dimension", "tax_classification", "valuation_policy"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = value.strip().upper()
    if isinstance(normalized.get("name"), str):
        normalized["name"] = normalized["name"].strip()
    return normalized


def _validate_category(category: ItemCategory) -> None:
    if not category.parent:
        return
    if category.parent_id == category.pk:
        raise ValidationError({"parent": "A category cannot be its own parent."})
    cursor = category.parent
    seen = {category.pk}
    while cursor:
        if cursor.pk in seen:
            raise ValidationError({"parent": "Category hierarchy cannot contain a cycle."})
        seen.add(cursor.pk)
        cursor = cursor.parent


def _validate_item(item: Item) -> None:
    if item.subcategory:
        if not item.category:
            raise ValidationError({"category": "A category is required when subcategory is set."})
        if item.subcategory.parent_id != item.category_id:
            raise ValidationError(
                {"subcategory": "Subcategory must be a child of the selected category."}
            )
    if item.parent_item:
        if item.parent_item.legal_entity_id != item.legal_entity_id:
            raise ValidationError(
                {"parent_item": "Parent item must belong to the same legal entity."}
            )
        cursor = item.parent_item
        seen = {item.pk}
        while cursor:
            if cursor.pk in seen:
                raise ValidationError({"parent_item": "Item hierarchy cannot contain a cycle."})
            seen.add(cursor.pk)
            cursor = cursor.parent_item
    if not isinstance(item.variant_attributes, dict):
        raise ValidationError(
            {"variant_attributes": "Variant attributes must be a key/value object."}
        )
    if item.preferred_vendor:
        if item.preferred_vendor.legal_entity_id != item.legal_entity_id:
            raise ValidationError(
                {"preferred_vendor": "Preferred vendor must belong to the same legal entity."}
            )
        vendor_roles = effective_partner_roles(item.preferred_vendor).filter(
            role_type=PartnerRoleType.VENDOR
        )
        if not item.preferred_vendor.is_active or not vendor_roles.exists():
            raise ValidationError(
                {"preferred_vendor": "Preferred vendor must have an effective active VENDOR role."}
            )


def _create(model_class, *, actor, reason: str, idempotency_key: str, values: dict):
    instance = model_class(**_normalize(values))
    if isinstance(instance, ItemCategory):
        _validate_category(instance)
    if isinstance(instance, Item):
        _validate_item(instance)
    instance.full_clean()
    instance.save()
    after = model_snapshot(instance)
    record_audit_event(
        action=f"{instance._meta.label_lower}.created",
        target_type=instance._meta.label_lower,
        target_id=instance.pk,
        actor=actor,
        source="catalog.service",
        reason=reason,
        idempotency_key=idempotency_key,
        after_state=after,
        changed_fields=sorted(after),
    )
    return instance


def _update(instance: CatalogMaster, *, actor, reason: str, idempotency_key: str, values: dict):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to edit catalog master data."})
    locked = type(instance).objects.select_for_update().get(pk=instance.pk)
    before = model_snapshot(locked)
    for field, value in _normalize(values).items():
        setattr(locked, field, value)
    if isinstance(locked, ItemCategory):
        _validate_category(locked)
    if isinstance(locked, Item):
        _validate_item(locked)
    locked.full_clean()
    locked.save()
    after = model_snapshot(locked)
    record_audit_event(
        action=f"{locked._meta.label_lower}.updated",
        target_type=locked._meta.label_lower,
        target_id=locked.pk,
        actor=actor,
        source="catalog.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    return locked


@transaction.atomic
def create_uom(*, actor=None, reason: str = "", idempotency_key: str = "", **values):
    return _create(UOM, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values)


@transaction.atomic
def update_uom(instance, *, actor=None, reason: str = "", idempotency_key: str = "", **values):
    return _update(
        instance, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def create_item_category(*, actor=None, reason: str = "", idempotency_key: str = "", **values):
    return _create(
        ItemCategory, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def update_item_category(
    instance, *, actor=None, reason: str = "", idempotency_key: str = "", **values
):
    return _update(
        instance, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def create_item(*, actor=None, reason: str = "", idempotency_key: str = "", **values):
    return _create(Item, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values)


@transaction.atomic
def update_item(instance, *, actor=None, reason: str = "", idempotency_key: str = "", **values):
    return _update(
        instance, actor=actor, reason=reason, idempotency_key=idempotency_key, values=values
    )


@transaction.atomic
def deactivate_catalog_master(
    instance: CatalogMaster,
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
    locked.effective_to = max(end_date, locked.effective_from)
    locked.full_clean()
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    after = model_snapshot(locked)
    record_audit_event(
        action=f"{locked._meta.label_lower}.deactivated",
        target_type=locked._meta.label_lower,
        target_id=locked.pk,
        actor=actor,
        source="catalog.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    return locked


@transaction.atomic
def reactivate_catalog_master(
    instance: CatalogMaster,
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
        source="catalog.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    return locked
