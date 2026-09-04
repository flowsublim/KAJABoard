from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.services.audit import record_audit_event
from apps.incentives.models import IncentiveRule


def check_rule_overlap(
    *,
    legal_entity,
    incentive_type,
    trigger_type,
    effective_from,
    effective_to=None,
    item=None,
    exclude_rule_id=None,
) -> IncentiveRule | None:
    """
    Checks if an active rule exists that overlaps with the given effective dates.
    Returns overlapping rule if found, else None.
    """
    qs = IncentiveRule.objects.filter(
        legal_entity=legal_entity,
        incentive_type=incentive_type,
        trigger_type=trigger_type,
        is_active=True,
    )
    if item is not None:
        qs = qs.filter(item=item)
    else:
        qs = qs.filter(item__isnull=True)

    if exclude_rule_id:
        qs = qs.exclude(pk=exclude_rule_id)

    # Overlap logic: (StartA <= EndB) and (EndA >= StartB)
    # where null End means infinity
    for rule in qs:
        # If existing rule has no end, it overlaps if new rule starts or ends after existing start
        if rule.effective_to is None:
            if effective_to is None or effective_to >= rule.effective_from:
                return rule
        else:
            # existing rule has end
            if effective_to is None:
                if effective_from <= rule.effective_to:
                    return rule
            else:
                if effective_from <= rule.effective_to and effective_to >= rule.effective_from:
                    return rule
    return None


@transaction.atomic
def create_incentive_rule(
    *,
    legal_entity,
    code: str,
    name: str,
    incentive_type: str,
    trigger_type: str,
    calculation_method: str,
    rate_value,
    effective_from,
    effective_to=None,
    item=None,
    currency: str = "IDR",
    notes: str = "",
    is_active: bool = True,
    actor=None,
) -> IncentiveRule:
    rule = IncentiveRule(
        legal_entity=legal_entity,
        code=code.strip(),
        name=name.strip(),
        incentive_type=incentive_type,
        trigger_type=trigger_type,
        calculation_method=calculation_method,
        rate_value=rate_value,
        effective_from=effective_from,
        effective_to=effective_to,
        item=item,
        currency=currency,
        notes=notes,
        is_active=is_active,
    )
    rule.full_clean()

    if is_active:
        overlapping = check_rule_overlap(
            legal_entity=legal_entity,
            incentive_type=incentive_type,
            trigger_type=trigger_type,
            effective_from=effective_from,
            effective_to=effective_to,
            item=item,
        )
        if overlapping:
            raise ValidationError(
                f"Overlapping active rule '{overlapping.code}' already exists for this "
                "context and date range."
            )

    rule.save()

    if actor:
        record_audit_event(
            actor=actor,
            action="INCENTIVE_RULE_CREATED",
            target_type="IncentiveRule",
            target_id=str(rule.pk),
            after_state=f"{rule.code} ({rule.incentive_type})",
            metadata={
                "code": rule.code,
                "rate": str(rule.rate_value),
                "calculation_method": rule.calculation_method,
            },
        )
    return rule


@transaction.atomic
def update_incentive_rule(
    rule: IncentiveRule,
    *,
    actor=None,
    **kwargs,
) -> IncentiveRule:
    before_state = f"{rule.code} (active={rule.is_active}, rate={rule.rate_value})"
    changed_fields = []
    for key, value in kwargs.items():
        if hasattr(rule, key):
            setattr(rule, key, value)
            changed_fields.append(key)

    rule.full_clean()

    if rule.is_active:
        overlapping = check_rule_overlap(
            legal_entity=rule.legal_entity,
            incentive_type=rule.incentive_type,
            trigger_type=rule.trigger_type,
            effective_from=rule.effective_from,
            effective_to=rule.effective_to,
            item=rule.item,
            exclude_rule_id=rule.pk,
        )
        if overlapping:
            raise ValidationError(
                f"Overlapping active rule '{overlapping.code}' already exists for this "
                "context and date range."
            )

    rule.save()

    if actor:
        record_audit_event(
            actor=actor,
            action="INCENTIVE_RULE_UPDATED",
            target_type="IncentiveRule",
            target_id=str(rule.pk),
            before_state=before_state,
            after_state=f"{rule.code} (active={rule.is_active}, rate={rule.rate_value})",
            changed_fields=changed_fields,
        )
    return rule
