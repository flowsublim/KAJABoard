from django.db.models import Q
from django.utils import timezone

from apps.organizations.selectors import accessible_legal_entities
from apps.partners.models import BusinessPartner, PartnerRole


def business_partners(user, *, search: str = "", role_type: str = "", include_inactive=False):
    queryset = BusinessPartner.objects.filter(
        legal_entity__in=accessible_legal_entities(user)
    ).prefetch_related("roles")
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    if role_type:
        today = timezone.localdate()
        queryset = queryset.filter(
            roles__role_type=role_type,
            roles__is_active=True,
            roles__effective_from__lte=today,
        ).filter(Q(roles__effective_to__isnull=True) | Q(roles__effective_to__gte=today))
    if search:
        queryset = queryset.filter(
            Q(code__icontains=search)
            | Q(display_name__icontains=search)
            | Q(legal_name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
        )
    return queryset.distinct().order_by("code")


def effective_partner_roles(partner, *, business_date=None):
    business_date = business_date or timezone.localdate()
    queryset = PartnerRole.objects.filter(
        partner=partner,
        effective_from__lte=business_date,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=business_date))
    if business_date >= timezone.localdate():
        queryset = queryset.filter(is_active=True)
    return queryset


def effective_business_partners(user, *, business_date=None, role_type: str = ""):
    business_date = business_date or timezone.localdate()
    queryset = (
        business_partners(
            user,
            include_inactive=business_date < timezone.localdate(),
        )
        .filter(effective_from__lte=business_date)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=business_date))
    )
    if role_type:
        queryset = queryset.filter(
            roles__role_type=role_type,
            roles__effective_from__lte=business_date,
        ).filter(Q(roles__effective_to__isnull=True) | Q(roles__effective_to__gte=business_date))
        if business_date >= timezone.localdate():
            queryset = queryset.filter(roles__is_active=True)
    return queryset.distinct().order_by("code")
