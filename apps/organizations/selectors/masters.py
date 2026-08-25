from django.db.models import Count, Q
from django.utils import timezone

from apps.organizations.models import CostCenter, LegalEntity, Warehouse


def accessible_legal_entities(user):
    queryset = LegalEntity.objects.all()
    if user.is_superuser:
        return queryset
    return queryset.filter(memberships__user=user, memberships__is_active=True).distinct()


def user_can_access_entity(user, legal_entity_id) -> bool:
    return accessible_legal_entities(user).filter(pk=legal_entity_id).exists()


def _effective(queryset, business_date):
    queryset = queryset.filter(effective_from__lte=business_date).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=business_date)
    )
    # ``is_active`` represents the current operational switch. A row ended later
    # must remain selectable for an earlier business date.
    if business_date >= timezone.localdate():
        queryset = queryset.filter(is_active=True)
    return queryset


def effective_legal_entities(user, *, business_date=None):
    return _effective(accessible_legal_entities(user), business_date or timezone.localdate())


def effective_cost_centers(user, *, business_date=None):
    queryset = CostCenter.objects.filter(legal_entity__in=accessible_legal_entities(user))
    return _effective(queryset, business_date or timezone.localdate())


def effective_warehouses(user, *, business_date=None):
    queryset = Warehouse.objects.filter(legal_entity__in=accessible_legal_entities(user))
    return _effective(queryset, business_date or timezone.localdate())


def organization_master_counts(user) -> dict[str, int]:
    entities = accessible_legal_entities(user).annotate(
        active_units=Count(
            "business_units", filter=Q(business_units__is_active=True), distinct=True
        ),
        active_departments=Count(
            "departments", filter=Q(departments__is_active=True), distinct=True
        ),
        active_cost_centers=Count(
            "cost_centers", filter=Q(cost_centers__is_active=True), distinct=True
        ),
        active_warehouses=Count("warehouses", filter=Q(warehouses__is_active=True), distinct=True),
    )
    return {
        "legal_entities": entities.filter(is_active=True).count(),
        "business_units": sum(entity.active_units for entity in entities),
        "departments": sum(entity.active_departments for entity in entities),
        "cost_centers": sum(entity.active_cost_centers for entity in entities),
        "warehouses": sum(entity.active_warehouses for entity in entities),
    }
