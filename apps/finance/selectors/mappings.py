from django.db.models import Q

from apps.finance.models import COAMapping
from apps.organizations.selectors import accessible_legal_entities


def coa_mappings(
    user,
    *,
    include_inactive=False,
    search="",
    legal_entity=None,
    module_code="",
    event_code="",
):
    queryset = COAMapping.objects.select_related("legal_entity", "account").filter(
        legal_entity__in=accessible_legal_entities(user)
    )
    if legal_entity is not None:
        queryset = queryset.filter(legal_entity=legal_entity)
    if module_code:
        queryset = queryset.filter(module_code=module_code.strip().upper())
    if event_code:
        queryset = queryset.filter(event_code=event_code.strip().upper())
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    if search:
        queryset = queryset.filter(
            Q(module_code__icontains=search)
            | Q(event_code__icontains=search)
            | Q(line_role__icontains=search)
            | Q(dimension_value__icontains=search)
            | Q(account__account_code__icontains=search)
            | Q(account__account_name__icontains=search)
        )
    return queryset
