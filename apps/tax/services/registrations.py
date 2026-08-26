from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.services.audit import record_audit_event
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.organizations.models import LegalEntity
from apps.partners.models import BusinessPartner
from apps.tax.models import TaxRegistration


def _normalize(values):
    normalized = values.copy()
    for field in ("registration_status", "tax_classification_key", "registration_reference"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = " ".join(value.split()).upper()
    if isinstance(normalized.get("notes"), str):
        normalized["notes"] = normalized["notes"].strip()
    return normalized


def _subject_filter(registration: TaxRegistration):
    if registration.legal_entity_id:
        return Q(legal_entity=registration.legal_entity, business_partner__isnull=True)
    return Q(business_partner=registration.business_partner, legal_entity__isnull=True)


def _validate_registration(registration: TaxRegistration, *, exclude_pk=None):
    if bool(registration.legal_entity) == bool(registration.business_partner):
        raise ValidationError("Exactly one tax subject is required.")
    overlaps = TaxRegistration.objects.filter(_subject_filter(registration))
    if exclude_pk:
        overlaps = overlaps.exclude(pk=exclude_pk)
    overlaps = overlaps.filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=registration.effective_from)
    )
    if registration.effective_to:
        overlaps = overlaps.filter(effective_from__lte=registration.effective_to)
    if overlaps.exists():
        raise ValidationError(
            {"effective_from": "Tax registration periods cannot overlap for the same subject."}
        )
    registration.full_clean()


def _audit(instance, *, action, actor, reason, idempotency_key, before=None):
    after = model_snapshot(instance)
    record_audit_event(
        action=action,
        target_type=instance._meta.label_lower,
        target_id=instance.pk,
        actor=actor,
        source="tax.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after) if before else sorted(after),
    )


@transaction.atomic
def create_tax_registration(*, actor=None, reason="", idempotency_key="", **values):
    values = _normalize(values)
    if values.get("legal_entity"):
        values["legal_entity"] = LegalEntity.objects.select_for_update().get(
            pk=values["legal_entity"].pk
        )
    if values.get("business_partner"):
        values["business_partner"] = BusinessPartner.objects.select_for_update().get(
            pk=values["business_partner"].pk
        )
    registration = TaxRegistration(**values)
    _validate_registration(registration)
    registration.save()
    _audit(
        registration,
        action="tax.taxregistration.created",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    return registration


@transaction.atomic
def update_tax_registration(registration, *, actor=None, reason="", idempotency_key="", **values):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to edit tax registration."})
    if registration.legal_entity_id:
        LegalEntity.objects.select_for_update().get(pk=registration.legal_entity_id)
    else:
        BusinessPartner.objects.select_for_update().get(pk=registration.business_partner_id)
    locked = TaxRegistration.objects.select_for_update().get(pk=registration.pk)
    normalized = _normalize(values)
    subject_fields = {"legal_entity", "business_partner"}
    if any(
        field in normalized and getattr(locked, field) != normalized[field]
        for field in subject_fields
    ):
        raise ValidationError("Tax registration subject is stable.")
    semantic_fields = {
        "registration_status",
        "tax_classification_key",
        "registration_reference",
        "effective_from",
    }
    if locked.effective_from <= timezone.localdate() and any(
        field in normalized and getattr(locked, field) != normalized[field]
        for field in semantic_fields
    ):
        raise ValidationError(
            "An effective tax registration cannot change historical meaning; "
            "end it and create a new version."
        )
    before = model_snapshot(locked)
    for field, value in normalized.items():
        setattr(locked, field, value)
    _validate_registration(locked, exclude_pk=locked.pk)
    locked.save()
    _audit(
        locked,
        action="tax.taxregistration.updated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked


@transaction.atomic
def deactivate_tax_registration(registration, *, actor=None, reason: str, idempotency_key=""):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to deactivate master data."})
    locked = TaxRegistration.objects.select_for_update().get(pk=registration.pk)
    if not locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = False
    locked.effective_to = max(timezone.localdate(), locked.effective_from)
    locked.full_clean()
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    _audit(
        locked,
        action="tax.taxregistration.deactivated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked


@transaction.atomic
def reactivate_tax_registration(registration, *, actor=None, reason: str, idempotency_key=""):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to reactivate master data."})
    locked = TaxRegistration.objects.select_for_update().get(pk=registration.pk)
    if locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = True
    locked.effective_to = None
    _validate_registration(locked, exclude_pk=locked.pk)
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    _audit(
        locked,
        action="tax.taxregistration.reactivated",
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        before=before,
    )
    return locked
