from django.db.models import Q
from django.utils import timezone

from apps.finance.models import COAAccount
from apps.organizations.selectors import accessible_legal_entities


def _effective(queryset, business_date):
    queryset = queryset.filter(effective_from__lte=business_date).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=business_date)
    )
    if business_date >= timezone.localdate():
        queryset = queryset.filter(is_active=True)
    return queryset


def coa_accounts(user, *, include_inactive=False, search="", legal_entity=None):
    queryset = COAAccount.objects.select_related("legal_entity", "parent").filter(
        legal_entity__in=accessible_legal_entities(user)
    )
    if legal_entity is not None:
        queryset = queryset.filter(legal_entity=legal_entity)
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    if search:
        queryset = queryset.filter(
            Q(account_code__icontains=search) | Q(account_name__icontains=search)
        )
    return queryset


def effective_coa_accounts(user, *, business_date=None, **filters):
    filters.setdefault("include_inactive", True)
    return _effective(coa_accounts(user, **filters), business_date or timezone.localdate())


def resolve_coa_account(user, *, legal_entity, account_code, business_date):
    code_key = " ".join(str(account_code).split()).upper()
    queryset = effective_coa_accounts(
        user,
        business_date=business_date,
        legal_entity=legal_entity,
        include_inactive=True,
    ).filter(account_code_normalized=code_key)
    return queryset.get()
