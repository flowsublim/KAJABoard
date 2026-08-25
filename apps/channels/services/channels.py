from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.channels.models import ExternalSKUMap, Store
from apps.channels.selectors.channels import normalize_external_key
from apps.core.services.audit import record_audit_event
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.organizations.models import LegalEntity

ChannelMaster = Store | ExternalSKUMap


def _normalize_store(values):
    normalized = values.copy()
    for field in ("code", "channel", "finance_dimension", "revenue_mapping_key"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = value.strip().upper()
    for field in ("name", "external_account_id", "notes"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = value.strip()
    if "external_aliases" in normalized:
        aliases = normalized["external_aliases"]
        if not isinstance(aliases, list):
            raise ValidationError({"external_aliases": "External aliases must be a list."})
        unique = {}
        for alias in aliases:
            cleaned = " ".join(str(alias).split())
            if cleaned:
                unique.setdefault(normalize_external_key(cleaned), cleaned)
        normalized["external_aliases"] = sorted(unique.values(), key=str.casefold)
    return normalized


def _normalize_mapping(values):
    normalized = values.copy()
    for field in ("external_sku", "external_product_name", "external_variation", "notes"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = " ".join(value.split()) if field != "notes" else value.strip()
    if "external_sku" in normalized:
        normalized["external_sku_normalized"] = normalize_external_key(normalized["external_sku"])
    if "external_variation" in normalized:
        normalized["external_variation_normalized"] = normalize_external_key(
            normalized["external_variation"]
        )
    return normalized


def _periods_overlap(left, right) -> bool:
    return (left.effective_to is None or right.effective_from <= left.effective_to) and (
        right.effective_to is None or left.effective_from <= right.effective_to
    )


def _validate_store(store: Store, *, exclude_pk=None):
    if store.business_unit and store.business_unit.legal_entity_id != store.legal_entity_id:
        raise ValidationError(
            {"business_unit": "Business unit must belong to the same legal entity."}
        )
    if not isinstance(store.external_aliases, list):
        raise ValidationError({"external_aliases": "External aliases must be a list."})
    store.full_clean()
    identifiers = {
        normalize_external_key(store.code),
        normalize_external_key(store.name),
        normalize_external_key(store.external_account_id),
        *(normalize_external_key(alias) for alias in store.external_aliases),
    }
    identifiers.discard("")
    candidates = Store.objects.filter(
        legal_entity=store.legal_entity,
        channel=store.channel,
    )
    if exclude_pk:
        candidates = candidates.exclude(pk=exclude_pk)
    for candidate in candidates:
        if not _periods_overlap(store, candidate):
            continue
        candidate_ids = {
            normalize_external_key(candidate.code),
            normalize_external_key(candidate.name),
            normalize_external_key(candidate.external_account_id),
            *(normalize_external_key(alias) for alias in candidate.external_aliases),
        }
        candidate_ids.discard("")
        if identifiers & candidate_ids:
            raise ValidationError(
                {
                    "external_aliases": (
                        "Store identifiers cannot overlap in the same channel and period."
                    )
                }
            )


def _validate_mapping(mapping: ExternalSKUMap, *, exclude_pk=None):
    if mapping.store.legal_entity_id != mapping.item.legal_entity_id:
        raise ValidationError({"item": "Mapped Item must belong to the Store legal entity."})
    if not mapping.external_sku_normalized:
        raise ValidationError({"external_sku": "External SKU is required."})
    for field, dependency in (("store", mapping.store), ("item", mapping.item)):
        if mapping.effective_from < dependency.effective_from:
            raise ValidationError(
                {field: f"{field.title()} must cover the complete mapping effective period."}
            )
        if dependency.effective_to and (
            mapping.effective_to is None or mapping.effective_to > dependency.effective_to
        ):
            raise ValidationError(
                {field: f"{field.title()} must cover the complete mapping effective period."}
            )
    today = timezone.localdate()
    covers_today = mapping.effective_from <= today and (
        mapping.effective_to is None or mapping.effective_to >= today
    )
    if covers_today and not mapping.store.is_active:
        raise ValidationError({"store": "Store must be active for a currently effective mapping."})
    if covers_today and not mapping.item.is_active:
        raise ValidationError({"item": "Item must be active for a currently effective mapping."})
    mapping.full_clean()
    queryset = ExternalSKUMap.objects.filter(
        store=mapping.store,
        external_sku_normalized=mapping.external_sku_normalized,
        external_variation_normalized=mapping.external_variation_normalized,
    )
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    queryset = queryset.filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=mapping.effective_from)
    )
    if mapping.effective_to:
        queryset = queryset.filter(effective_from__lte=mapping.effective_to)
    if queryset.exists():
        raise ValidationError(
            {"effective_from": "External SKU mappings for the same scope cannot overlap."}
        )


def _audit(instance, *, action, actor, reason, idempotency_key, before=None):
    after = model_snapshot(instance)
    record_audit_event(
        action=action,
        target_type=instance._meta.label_lower,
        target_id=instance.pk,
        actor=actor,
        source="channels.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after) if before else sorted(after),
    )


@transaction.atomic
def create_store(*, actor=None, reason="", idempotency_key="", **values):
    values = _normalize_store(values)
    entity = LegalEntity.objects.select_for_update().get(pk=values["legal_entity"].pk)
    values["legal_entity"] = entity
    store = Store(**values)
    _validate_store(store)
    store.save()
    _audit(
        store,
        action="channels.store.created",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    return store


@transaction.atomic
def update_store(store, *, actor=None, reason="", idempotency_key="", **values):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to edit a Store."})
    LegalEntity.objects.select_for_update().get(pk=store.legal_entity_id)
    locked = Store.objects.select_for_update().get(pk=store.pk)
    normalized = _normalize_store(values)
    stable_fields = {"legal_entity", "code", "channel"}
    if any(
        field in normalized
        and getattr(locked, f"{field}_id" if field == "legal_entity" else field)
        != (normalized[field].pk if field == "legal_entity" else normalized[field])
        for field in stable_fields
    ):
        raise ValidationError("Store legal entity, code, and channel are stable identity fields.")
    aliases = list(normalized.get("external_aliases", locked.external_aliases))
    for field in ("name", "external_account_id"):
        if field in normalized and normalized[field] != getattr(locked, field):
            old_identifier = getattr(locked, field).strip()
            if old_identifier:
                aliases.append(old_identifier)
    if "external_aliases" in normalized or aliases != locked.external_aliases:
        normalized["external_aliases"] = _normalize_store({"external_aliases": aliases})[
            "external_aliases"
        ]
    before = model_snapshot(locked)
    for field, value in normalized.items():
        setattr(locked, field, value)
    _validate_store(locked, exclude_pk=locked.pk)
    locked.save()
    _audit(
        locked,
        action="channels.store.updated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked


@transaction.atomic
def create_external_sku_mapping(*, actor=None, reason="", idempotency_key="", **values):
    values = _normalize_mapping(values)
    store = (
        Store.objects.select_for_update().select_related("legal_entity").get(pk=values["store"].pk)
    )
    values["store"] = store
    mapping = ExternalSKUMap(**values)
    _validate_mapping(mapping)
    mapping.save()
    _audit(
        mapping,
        action="channels.externalskumap.created",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    return mapping


@transaction.atomic
def update_external_sku_mapping(mapping, *, actor=None, reason="", idempotency_key="", **values):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to edit an SKU mapping."})
    Store.objects.select_for_update().get(pk=mapping.store_id)
    locked = ExternalSKUMap.objects.select_for_update().get(pk=mapping.pk)
    normalized = _normalize_mapping(values)
    semantic_fields = {
        "item",
        "conversion_quantity",
        "effective_from",
    }
    stable_fields = {"store", "external_sku", "external_variation"}
    if any(
        field in normalized
        and getattr(locked, f"{field}_id" if field == "store" else field)
        != (normalized[field].pk if field == "store" else normalized[field])
        for field in stable_fields
    ):
        raise ValidationError("Store, external SKU, and variation are stable mapping scope fields.")
    if locked.effective_from <= timezone.localdate() and any(
        field in normalized and getattr(locked, field) != normalized[field]
        for field in semantic_fields
    ):
        raise ValidationError(
            "An effective SKU mapping cannot change historical meaning; "
            "end it and create a new version."
        )
    before = model_snapshot(locked)
    for field, value in normalized.items():
        setattr(locked, field, value)
    _validate_mapping(locked, exclude_pk=locked.pk)
    locked.save()
    _audit(
        locked,
        action="channels.externalskumap.updated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked


@transaction.atomic
def deactivate_channel_master(
    instance: ChannelMaster,
    *,
    actor=None,
    reason: str,
    effective_to=None,
    idempotency_key="",
):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to deactivate master data."})
    lock_model = LegalEntity if isinstance(instance, Store) else Store
    lock_pk = instance.legal_entity_id if isinstance(instance, Store) else instance.store_id
    lock_model.objects.select_for_update().get(pk=lock_pk)
    locked = type(instance).objects.select_for_update().get(pk=instance.pk)
    if not locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = False
    end_date = effective_to or timezone.localdate()
    locked.effective_to = max(end_date, locked.effective_from)
    locked.full_clean()
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    _audit(
        locked,
        action=f"{locked._meta.label_lower}.deactivated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked


@transaction.atomic
def reactivate_channel_master(
    instance: ChannelMaster, *, actor=None, reason: str, idempotency_key=""
):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to reactivate master data."})
    lock_model = LegalEntity if isinstance(instance, Store) else Store
    lock_pk = instance.legal_entity_id if isinstance(instance, Store) else instance.store_id
    lock_model.objects.select_for_update().get(pk=lock_pk)
    locked = type(instance).objects.select_for_update().get(pk=instance.pk)
    if locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = True
    locked.effective_to = None
    if isinstance(locked, Store):
        _validate_store(locked, exclude_pk=locked.pk)
    else:
        _validate_mapping(locked, exclude_pk=locked.pk)
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    _audit(
        locked,
        action=f"{locked._meta.label_lower}.reactivated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked
