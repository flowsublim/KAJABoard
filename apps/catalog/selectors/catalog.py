from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import UOM, Item, ItemCategory
from apps.organizations.selectors import accessible_legal_entities


def catalog_items(user, *, search: str = "", include_inactive=False):
    queryset = Item.objects.filter(legal_entity__in=accessible_legal_entities(user)).select_related(
        "legal_entity", "uom", "category", "subcategory", "parent_item", "preferred_vendor"
    )
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    if search:
        queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
    return queryset.order_by("code")


def effective_items(user, *, business_date=None):
    business_date = business_date or timezone.localdate()
    return (
        catalog_items(user, include_inactive=business_date < timezone.localdate())
        .filter(effective_from__lte=business_date)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=business_date))
    )


def units_of_measure(*, include_inactive=False):
    queryset = UOM.objects.all()
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("code")


def item_categories(*, include_inactive=False):
    queryset = ItemCategory.objects.select_related("parent")
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("code")
