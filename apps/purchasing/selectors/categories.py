from django.db.models import Q
from django.utils import timezone

from apps.organizations.selectors import accessible_legal_entities
from apps.purchasing.models import PurchaseCategory


def _effective(queryset, business_date):
    queryset = queryset.filter(effective_from__lte=business_date).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=business_date)
    )
    if business_date >= timezone.localdate():
        queryset = queryset.filter(is_active=True)
    return queryset


def purchase_categories(
    user,
    *,
    include_inactive=False,
    search="",
    legal_entity=None,
    accounting_treatment="",
):
    queryset = PurchaseCategory.objects.select_related("legal_entity", "cost_center").filter(
        legal_entity__in=accessible_legal_entities(user)
    )
    if legal_entity is not None:
        queryset = queryset.filter(legal_entity=legal_entity)
    if accounting_treatment:
        queryset = queryset.filter(accounting_treatment=accounting_treatment)
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    if search:
        queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
    return queryset


def effective_purchase_categories(user, *, business_date=None, **filters):
    filters.setdefault("include_inactive", True)
    return _effective(purchase_categories(user, **filters), business_date or timezone.localdate())


def resolve_purchase_category(user, *, legal_entity, code, business_date):
    code_key = " ".join(str(code).split()).upper()
    queryset = effective_purchase_categories(
        user,
        business_date=business_date,
        legal_entity=legal_entity,
        include_inactive=True,
    ).filter(code_normalized=code_key)
    return queryset.get()
