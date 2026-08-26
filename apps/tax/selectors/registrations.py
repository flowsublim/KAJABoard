from django.db.models import Q
from django.utils import timezone

from apps.organizations.selectors import accessible_legal_entities
from apps.tax.models import TaxRegistration


def _base_queryset(user):
    entities = accessible_legal_entities(user)
    return TaxRegistration.objects.select_related(
        "legal_entity",
        "business_partner",
        "business_partner__legal_entity",
    ).filter(Q(legal_entity__in=entities) | Q(business_partner__legal_entity__in=entities))


def _effective(queryset, business_date):
    queryset = queryset.filter(effective_from__lte=business_date).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=business_date)
    )
    if business_date >= timezone.localdate():
        queryset = queryset.filter(is_active=True)
    return queryset


def tax_registrations(user, *, include_inactive=False, search=""):
    queryset = _base_queryset(user)
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    if search:
        queryset = queryset.filter(
            Q(registration_status__icontains=search)
            | Q(tax_classification_key__icontains=search)
            | Q(legal_entity__code__icontains=search)
            | Q(legal_entity__name__icontains=search)
            | Q(business_partner__code__icontains=search)
            | Q(business_partner__display_name__icontains=search)
        )
    return queryset


def effective_tax_registrations(user, *, business_date=None, **filters):
    filters.setdefault("include_inactive", True)
    return _effective(tax_registrations(user, **filters), business_date or timezone.localdate())


def resolve_tax_registration(user, *, legal_entity=None, business_partner=None, business_date):
    queryset = effective_tax_registrations(
        user,
        business_date=business_date,
        include_inactive=True,
    )
    if business_partner is not None:
        queryset = queryset.filter(business_partner=business_partner)
    else:
        queryset = queryset.filter(legal_entity=legal_entity)
    return queryset.get()
