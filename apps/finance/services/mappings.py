from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.services.audit import record_audit_event
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.finance.models import COAAccount, COAMapping, DCDirection, MappingDimensionType
from apps.organizations.models import LegalEntity


class FinanceMappingError(ValidationError):
    """Raised when accounting mapping cannot be resolved deterministically."""


@dataclass(frozen=True)
class ResolvedAccountMapping:
    mapping_id: str
    account_id: str
    account_code: str
    account_name: str
    module_code: str
    event_code: str
    line_role: str
    dc: str
    selected_dimension_type: str
    selected_dimension_value: str
    priority: int
    business_date: object


def normalize_mapping_key(value: str) -> str:
    return " ".join(str(value or "").split()).upper()


def _normalize(values):
    normalized = values.copy()
    for field in (
        "module_code",
        "event_code",
        "dimension_type",
        "dimension_value",
        "line_role",
        "dc",
        "notes",
    ):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = " ".join(value.split()) if field != "notes" else value.strip()
    for field in ("module_code", "event_code", "dimension_type", "line_role", "dc"):
        if field in normalized:
            normalized[field] = str(normalized[field]).upper()
    if "dimension_type" in normalized and "dimension_value" in normalized:
        if normalized["dimension_type"] == MappingDimensionType.DEFAULT:
            normalized["dimension_value"] = "DEFAULT"
        normalized["dimension_value_normalized"] = normalize_mapping_key(
            normalized["dimension_value"]
        )
    return normalized


def _normalize_mapping_dimension(mapping: COAMapping) -> None:
    if mapping.dimension_type == MappingDimensionType.DEFAULT:
        mapping.dimension_value = "DEFAULT"
    mapping.dimension_value_normalized = normalize_mapping_key(mapping.dimension_value)


def _period_filter(queryset, instance):
    queryset = queryset.filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=instance.effective_from)
    )
    if instance.effective_to:
        queryset = queryset.filter(effective_from__lte=instance.effective_to)
    return queryset


def _covers_period(parent, child) -> bool:
    if child.effective_from < parent.effective_from:
        return False
    return not parent.effective_to or (
        child.effective_to is not None and child.effective_to <= parent.effective_to
    )


def _validate_mapping(mapping: COAMapping, *, exclude_pk=None):
    if mapping.account.legal_entity_id != mapping.legal_entity_id:
        raise ValidationError({"account": "COA account must belong to the same entity."})
    if mapping.dimension_type == MappingDimensionType.DEFAULT:
        if mapping.dimension_value_normalized != "DEFAULT":
            raise ValidationError({"dimension_value": "DEFAULT dimension value must be DEFAULT."})
    elif not mapping.dimension_value_normalized:
        raise ValidationError({"dimension_value": "Dimension value is required."})
    if not mapping.account.is_posting_allowed or mapping.account.is_header:
        raise ValidationError({"account": "COA Mapping requires a posting account."})
    if not _covers_period(mapping.account, mapping):
        raise ValidationError({"account": "COA account must cover the mapping effective period."})
    mapping.full_clean()
    overlaps = COAMapping.objects.filter(
        legal_entity=mapping.legal_entity,
        module_code=mapping.module_code,
        event_code=mapping.event_code,
        dimension_type=mapping.dimension_type,
        dimension_value_normalized=mapping.dimension_value_normalized,
        line_role=mapping.line_role,
        dc=mapping.dc,
        priority=mapping.priority,
    )
    if exclude_pk:
        overlaps = overlaps.exclude(pk=exclude_pk)
    if _period_filter(overlaps, mapping).exists():
        raise ValidationError(
            {"effective_from": "COA Mapping priority scopes cannot overlap for the same period."}
        )


def _is_effective(instance, business_date) -> bool:
    return instance.effective_from <= business_date and (
        instance.effective_to is None or instance.effective_to >= business_date
    )


def _validate_account_for_resolution(account: COAAccount, business_date):
    if not _is_effective(account, business_date):
        raise FinanceMappingError("Resolved account is not effective for the requested date.")
    if not account.is_active:
        raise FinanceMappingError("Resolved account is inactive.")
    if account.is_header or not account.is_posting_allowed:
        raise FinanceMappingError("Resolved account is not eligible for posting.")


def _audit(instance, *, action, actor, reason, idempotency_key, before=None):
    after = model_snapshot(instance)
    record_audit_event(
        action=action,
        target_type=instance._meta.label_lower,
        target_id=instance.pk,
        actor=actor,
        source="finance.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after) if before else sorted(after),
    )


@transaction.atomic
def create_coa_mapping(*, actor=None, reason="", idempotency_key="", **values):
    values = _normalize(values)
    entity = LegalEntity.objects.select_for_update().get(pk=values["legal_entity"].pk)
    account = COAAccount.objects.select_related("legal_entity").get(pk=values["account"].pk)
    values["legal_entity"] = entity
    values["account"] = account
    mapping = COAMapping(**values)
    _normalize_mapping_dimension(mapping)
    _validate_mapping(mapping)
    mapping.save()
    _audit(
        mapping,
        action="finance.coamapping.created",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    return mapping


@transaction.atomic
def update_coa_mapping(mapping, *, actor=None, reason="", idempotency_key="", **values):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to edit a COA Mapping."})
    LegalEntity.objects.select_for_update().get(pk=mapping.legal_entity_id)
    locked = COAMapping.objects.select_for_update().get(pk=mapping.pk)
    normalized = _normalize(values)
    semantic_fields = {
        "module_code",
        "event_code",
        "dimension_type",
        "dimension_value",
        "line_role",
        "dc",
        "account",
        "priority",
        "effective_from",
    }
    if locked.effective_from <= timezone.localdate() and any(
        field in normalized and getattr(locked, field) != normalized[field]
        for field in semantic_fields
    ):
        raise ValidationError(
            "An effective COA Mapping cannot change historical meaning; "
            "end it and create a new version."
        )
    before = model_snapshot(locked)
    for field, value in normalized.items():
        setattr(locked, field, value)
    _normalize_mapping_dimension(locked)
    _validate_mapping(locked, exclude_pk=locked.pk)
    locked.save()
    _audit(
        locked,
        action="finance.coamapping.updated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked


@transaction.atomic
def deactivate_coa_mapping(mapping, *, actor=None, reason: str, idempotency_key=""):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to deactivate master data."})
    LegalEntity.objects.select_for_update().get(pk=mapping.legal_entity_id)
    locked = COAMapping.objects.select_for_update().get(pk=mapping.pk)
    if not locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = False
    locked.effective_to = max(timezone.localdate(), locked.effective_from)
    locked.full_clean()
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    _audit(
        locked,
        action="finance.coamapping.deactivated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked


@transaction.atomic
def reactivate_coa_mapping(mapping, *, actor=None, reason: str, idempotency_key=""):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to reactivate master data."})
    LegalEntity.objects.select_for_update().get(pk=mapping.legal_entity_id)
    locked = COAMapping.objects.select_for_update().get(pk=mapping.pk)
    if locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = True
    locked.effective_to = None
    _validate_mapping(locked, exclude_pk=locked.pk)
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    _audit(
        locked,
        action="finance.coamapping.reactivated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked


def _candidate_queryset(
    *,
    legal_entity,
    module_code,
    event_code,
    line_role,
    dc,
    business_date,
):
    return (
        COAMapping.objects.select_related("account")
        .filter(
            legal_entity=legal_entity,
            module_code=normalize_mapping_key(module_code),
            event_code=normalize_mapping_key(event_code),
            line_role=normalize_mapping_key(line_role),
            dc=normalize_mapping_key(dc),
            is_active=True,
            effective_from__lte=business_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=business_date))
    )


def _pick_candidate(candidates, *, business_date):
    if not candidates:
        return None
    highest = max(candidate.priority for candidate in candidates)
    winners = [candidate for candidate in candidates if candidate.priority == highest]
    if len(winners) != 1:
        raise FinanceMappingError("Ambiguous COA Mapping candidates at the winning priority.")
    selected = winners[0]
    _validate_account_for_resolution(selected.account, business_date)
    return selected


def resolve_account_mapping(
    *,
    legal_entity,
    module_code,
    event_code,
    line_role,
    dc: str = DCDirection.DEBIT,
    business_date=None,
    context=None,
) -> ResolvedAccountMapping:
    """Resolve one finance mapping deterministically without creating a journal."""

    business_date = business_date or timezone.localdate()
    normalized_context = {
        normalize_mapping_key(key): normalize_mapping_key(value)
        for key, value in (context or {}).items()
        if normalize_mapping_key(value)
    }
    allowed_dimensions = {choice.value for choice in MappingDimensionType}
    invalid_dimensions = set(normalized_context) - allowed_dimensions
    if invalid_dimensions:
        raise FinanceMappingError(f"Unsupported accounting dimensions: {invalid_dimensions}.")
    queryset = _candidate_queryset(
        legal_entity=legal_entity,
        module_code=module_code,
        event_code=event_code,
        line_role=line_role,
        dc=dc,
        business_date=business_date,
    ).filter(dimension_type__in=[*normalized_context.keys(), MappingDimensionType.DEFAULT])
    exact = [
        mapping
        for mapping in queryset
        if mapping.dimension_type != MappingDimensionType.DEFAULT
        and normalized_context.get(mapping.dimension_type) == mapping.dimension_value_normalized
    ]
    selected = _pick_candidate(exact, business_date=business_date)
    if selected is None:
        defaults = [mapping for mapping in queryset if mapping.dimension_type == "DEFAULT"]
        selected = _pick_candidate(defaults, business_date=business_date)
    if selected is None:
        raise FinanceMappingError("No active COA Mapping resolved for the requested context.")
    return ResolvedAccountMapping(
        mapping_id=str(selected.pk),
        account_id=str(selected.account_id),
        account_code=selected.account.account_code,
        account_name=selected.account.account_name,
        module_code=selected.module_code,
        event_code=selected.event_code,
        line_role=selected.line_role,
        dc=selected.dc,
        selected_dimension_type=selected.dimension_type,
        selected_dimension_value=selected.dimension_value,
        priority=selected.priority,
        business_date=business_date,
    )
