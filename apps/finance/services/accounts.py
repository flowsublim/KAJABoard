from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.services.audit import record_audit_event
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.finance.models import COAAccount
from apps.organizations.models import LegalEntity


def normalize_account_code(value: str) -> str:
    return " ".join(str(value or "").split()).upper()


def _normalize(values):
    normalized = values.copy()
    for field in (
        "account_code",
        "account_name",
        "account_type",
        "report_group",
        "report_subgroup",
        "normal_balance",
        "notes",
    ):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = " ".join(value.split()) if field != "notes" else value.strip()
    if "account_code" in normalized:
        normalized["account_code_normalized"] = normalize_account_code(normalized["account_code"])
    for field in ("account_type", "normal_balance"):
        if field in normalized:
            normalized[field] = str(normalized[field]).upper()
    return normalized


def _validate_no_cycle(account: COAAccount):
    parent = account.parent
    visited = {account.pk} if account.pk else set()
    while parent:
        if parent.pk in visited:
            raise ValidationError({"parent": "COA account hierarchy cannot contain a cycle."})
        visited.add(parent.pk)
        parent = parent.parent


def _validate_account(account: COAAccount):
    if not account.account_code_normalized:
        raise ValidationError({"account_code": "Account code is required."})
    if account.parent:
        if account.parent.legal_entity_id != account.legal_entity_id:
            raise ValidationError({"parent": "Parent account must belong to the same entity."})
        if account.effective_from < account.parent.effective_from:
            raise ValidationError({"parent": "Parent account must cover the account period."})
        if account.parent.effective_to and (
            account.effective_to is None or account.effective_to > account.parent.effective_to
        ):
            raise ValidationError({"parent": "Parent account must cover the account period."})
    if account.is_header and account.is_posting_allowed:
        raise ValidationError({"is_posting_allowed": "Header accounts cannot allow posting."})
    _validate_no_cycle(account)
    account.full_clean()
    overlaps = COAAccount.objects.filter(
        legal_entity=account.legal_entity,
        account_code_normalized=account.account_code_normalized,
    )
    if account.pk:
        overlaps = overlaps.exclude(pk=account.pk)
    overlaps = overlaps.filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=account.effective_from)
    )
    if account.effective_to:
        overlaps = overlaps.filter(effective_from__lte=account.effective_to)
    if overlaps.exists():
        raise ValidationError(
            {"effective_from": "COA account versions cannot overlap for the same code."}
        )


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
def create_coa_account(*, actor=None, reason="", idempotency_key="", **values):
    values = _normalize(values)
    entity = LegalEntity.objects.select_for_update().get(pk=values["legal_entity"].pk)
    values["legal_entity"] = entity
    account = COAAccount(**values)
    _validate_account(account)
    account.save()
    _audit(
        account,
        action="finance.coaaccount.created",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    return account


@transaction.atomic
def update_coa_account(account, *, actor=None, reason="", idempotency_key="", **values):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to edit a COA account."})
    LegalEntity.objects.select_for_update().get(pk=account.legal_entity_id)
    locked = COAAccount.objects.select_for_update().get(pk=account.pk)
    normalized = _normalize(values)
    for field in ("legal_entity", "account_code"):
        if field not in normalized:
            continue
        current = getattr(locked, f"{field}_id" if field == "legal_entity" else field)
        incoming = normalized[field].pk if field == "legal_entity" else normalized[field]
        if current != incoming:
            raise ValidationError("Legal entity and account code are stable COA identity fields.")
    semantic_fields = {
        "account_type",
        "normal_balance",
        "parent",
        "is_header",
        "is_posting_allowed",
        "manual_journal_allowed",
        "is_cash_bank",
        "is_control_account",
        "effective_from",
    }
    if locked.effective_from <= timezone.localdate() and any(
        field in normalized and getattr(locked, field) != normalized[field]
        for field in semantic_fields
    ):
        raise ValidationError(
            "An effective COA account cannot change historical meaning; "
            "end it and create a new account/version."
        )
    before = model_snapshot(locked)
    for field, value in normalized.items():
        setattr(locked, field, value)
    _validate_account(locked)
    locked.save()
    _audit(
        locked,
        action="finance.coaaccount.updated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked


@transaction.atomic
def deactivate_coa_account(account, *, actor=None, reason: str, idempotency_key=""):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to deactivate master data."})
    LegalEntity.objects.select_for_update().get(pk=account.legal_entity_id)
    locked = COAAccount.objects.select_for_update().get(pk=account.pk)
    if not locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = False
    locked.effective_to = max(timezone.localdate(), locked.effective_from)
    locked.full_clean()
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    _audit(
        locked,
        action="finance.coaaccount.deactivated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked


@transaction.atomic
def reactivate_coa_account(account, *, actor=None, reason: str, idempotency_key=""):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to reactivate master data."})
    LegalEntity.objects.select_for_update().get(pk=account.legal_entity_id)
    locked = COAAccount.objects.select_for_update().get(pk=account.pk)
    if locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = True
    locked.effective_to = None
    _validate_account(locked)
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    _audit(
        locked,
        action="finance.coaaccount.reactivated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked
