from django.db import models

from apps.incentives.models import IncentiveRule


def resolve_incentive_rule(
    *,
    legal_entity,
    incentive_type,
    trigger_type,
    target_date,
    item=None,
) -> tuple[str, IncentiveRule | None]:
    """
    Deterministically resolves an active, effective IncentiveRule for a given context and date.

    Returns:
        (status, rule)
        status is one of: 'RESOLVED', 'PENDING_RULE', 'AMBIGUOUS_RULE'
    """
    base_qs = IncentiveRule.objects.filter(
        legal_entity=legal_entity,
        incentive_type=incentive_type,
        trigger_type=trigger_type,
        is_active=True,
        effective_from__lte=target_date,
    ).filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=target_date))

    if item is not None:
        # Check exact item-scoped rules
        item_rules = list(base_qs.filter(item=item))
        if len(item_rules) > 1:
            return "AMBIGUOUS_RULE", None
        if len(item_rules) == 1:
            return "RESOLVED", item_rules[0]
        # Section 5: Exact Item-scoped rules resolve only for that Item.
        # Do NOT silently fall back from missing Item rule to default/unscoped rule.
        return "PENDING_RULE", None

    # Unscoped lookup (item is None)
    unscoped_rules = list(base_qs.filter(item__isnull=True))
    if len(unscoped_rules) > 1:
        return "AMBIGUOUS_RULE", None
    if len(unscoped_rules) == 1:
        return "RESOLVED", unscoped_rules[0]
    return "PENDING_RULE", None


def get_incentive_rules(legal_entity, *, incentive_type=None, is_active=None):
    qs = IncentiveRule.objects.filter(legal_entity=legal_entity)
    if incentive_type:
        qs = qs.filter(incentive_type=incentive_type)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs
