from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.services.audit import record_audit_event
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType


def _normalize(values: dict[str, object]) -> dict[str, object]:
    normalized = values.copy()
    for field in ("code", "country_code", "npwp", "nitku"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = "".join(value.split()).upper()
    for field in ("display_name", "legal_name", "pic_name", "bank_name", "bank_account_name"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = value.strip()
    for field in ("email", "pic_email"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = value.strip().casefold()
    return normalized


def _validate_partner(instance: BusinessPartner) -> None:
    if not isinstance(instance.risk_flags, list):
        raise ValidationError({"risk_flags": "Risk flags must be a list of stable flag values."})
    instance.risk_flags = sorted(
        {str(flag).strip().upper() for flag in instance.risk_flags if str(flag).strip()}
    )


@transaction.atomic
def create_business_partner(
    *,
    actor=None,
    role_types=(),
    reason: str = "",
    idempotency_key: str = "",
    **values,
) -> BusinessPartner:
    partner = BusinessPartner(**_normalize(values))
    _validate_partner(partner)
    partner.full_clean()
    partner.save()
    after = model_snapshot(partner)
    record_audit_event(
        action="partners.businesspartner.created",
        target_type=partner._meta.label_lower,
        target_id=partner.pk,
        actor=actor,
        source="partners.service",
        reason=reason,
        idempotency_key=idempotency_key,
        after_state=after,
        changed_fields=sorted(after),
    )
    for role_type in dict.fromkeys(role_types):
        assign_partner_role(
            partner,
            role_type=role_type,
            actor=actor,
            reason=reason.strip() or "Initial partner role assignment",
            idempotency_key=idempotency_key,
        )
    return partner


@transaction.atomic
def update_business_partner(
    partner: BusinessPartner,
    *,
    actor=None,
    reason: str = "",
    idempotency_key: str = "",
    **values,
) -> BusinessPartner:
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to edit a business partner."})
    locked = BusinessPartner.objects.select_for_update().get(pk=partner.pk)
    before = model_snapshot(locked)
    for field, value in _normalize(values).items():
        setattr(locked, field, value)
    _validate_partner(locked)
    locked.full_clean()
    locked.save()
    after = model_snapshot(locked)
    record_audit_event(
        action="partners.businesspartner.updated",
        target_type=locked._meta.label_lower,
        target_id=locked.pk,
        actor=actor,
        source="partners.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    return locked


@transaction.atomic
def update_business_partner_with_roles(
    partner: BusinessPartner,
    *,
    role_types,
    actor=None,
    reason: str,
    idempotency_key: str = "",
    **values,
) -> BusinessPartner:
    """Atomically update partner fields and reconcile its active role assignments."""

    updated = update_business_partner(
        partner,
        actor=actor,
        reason=reason,
        idempotency_key=idempotency_key,
        **values,
    )
    selected = set(role_types)
    unsupported = selected - set(PartnerRoleType.values)
    if unsupported:
        raise ValidationError({"roles": f"Unsupported partner roles: {', '.join(unsupported)}"})
    active_roles = {
        role.role_type: role
        for role in PartnerRole.objects.select_for_update().filter(partner=updated, is_active=True)
    }
    for role_type in selected - active_roles.keys():
        assign_partner_role(
            updated,
            role_type=role_type,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
        )
    for role_type in active_roles.keys() - selected:
        remove_partner_role(
            active_roles[role_type],
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
        )
    return updated


@transaction.atomic
def assign_partner_role(
    partner: BusinessPartner,
    *,
    role_type: str,
    effective_from=None,
    actor=None,
    reason: str = "",
    idempotency_key: str = "",
) -> PartnerRole:
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to assign a partner role."})
    if role_type not in PartnerRoleType.values:
        raise ValidationError({"role_type": "Unsupported partner role."})
    locked_partner = BusinessPartner.objects.select_for_update().get(pk=partner.pk)
    if not locked_partner.is_active:
        raise ValidationError("Roles cannot be assigned to an inactive business partner.")
    existing = PartnerRole.objects.filter(
        partner=locked_partner,
        role_type=role_type,
        is_active=True,
    ).first()
    if existing:
        return existing
    role = PartnerRole(
        partner=locked_partner,
        role_type=role_type,
        effective_from=effective_from or timezone.localdate(),
    )
    role.full_clean()
    role.save()
    after = model_snapshot(role)
    record_audit_event(
        action="partners.partnerrole.assigned",
        target_type=role._meta.label_lower,
        target_id=role.pk,
        actor=actor,
        source="partners.service",
        reference=str(locked_partner.pk),
        reason=reason,
        idempotency_key=idempotency_key,
        after_state=after,
        changed_fields=sorted(after),
    )
    return role


@transaction.atomic
def remove_partner_role(
    role: PartnerRole,
    *,
    actor=None,
    reason: str,
    effective_to=None,
    idempotency_key: str = "",
) -> PartnerRole:
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to remove a partner role."})
    locked = PartnerRole.objects.select_for_update().get(pk=role.pk)
    if not locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = False
    locked.effective_to = effective_to or timezone.localdate()
    if locked.effective_to < locked.effective_from:
        raise ValidationError({"effective_to": "Role removal cannot predate role assignment."})
    locked.full_clean()
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    after = model_snapshot(locked)
    record_audit_event(
        action="partners.partnerrole.removed",
        target_type=locked._meta.label_lower,
        target_id=locked.pk,
        actor=actor,
        source="partners.service",
        reference=str(locked.partner_id),
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    return locked


@transaction.atomic
def deactivate_business_partner(
    partner: BusinessPartner,
    *,
    actor=None,
    reason: str,
    effective_to=None,
    idempotency_key: str = "",
) -> BusinessPartner:
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to deactivate a partner."})
    locked = BusinessPartner.objects.select_for_update().get(pk=partner.pk)
    if not locked.is_active:
        return locked
    end_date = effective_to or timezone.localdate()
    before = model_snapshot(locked)
    locked.is_active = False
    locked.effective_to = max(end_date, locked.effective_from)
    locked.full_clean()
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    after = model_snapshot(locked)
    record_audit_event(
        action="partners.businesspartner.deactivated",
        target_type=locked._meta.label_lower,
        target_id=locked.pk,
        actor=actor,
        source="partners.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    for role in PartnerRole.objects.select_for_update().filter(partner=locked, is_active=True):
        remove_partner_role(
            role,
            actor=actor,
            reason=f"Partner deactivated: {reason}",
            effective_to=locked.effective_to,
            idempotency_key=idempotency_key,
        )
    return locked


@transaction.atomic
def reactivate_business_partner(
    partner: BusinessPartner,
    *,
    actor=None,
    reason: str,
    idempotency_key: str = "",
) -> BusinessPartner:
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to reactivate a partner."})
    locked = BusinessPartner.objects.select_for_update().get(pk=partner.pk)
    if locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = True
    locked.effective_to = None
    locked.full_clean()
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    after = model_snapshot(locked)
    record_audit_event(
        action="partners.businesspartner.reactivated",
        target_type=locked._meta.label_lower,
        target_id=locked.pk,
        actor=actor,
        source="partners.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    return locked
