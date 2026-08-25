from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.channels.models import ExternalSKUMap, Store
from apps.organizations.selectors import accessible_legal_entities


def normalize_external_key(value) -> str:
    return " ".join(str(value or "").split()).casefold()


def stores(user, *, include_inactive=False, search="", channel=""):
    queryset = Store.objects.filter(
        legal_entity__in=accessible_legal_entities(user)
    ).select_related("legal_entity", "business_unit")
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    if channel:
        queryset = queryset.filter(channel=str(channel).strip().upper())
    if search:
        queryset = queryset.filter(
            Q(code__icontains=search)
            | Q(name__icontains=search)
            | Q(external_account_id__icontains=search)
        )
    return queryset.order_by("code")


def effective_stores(user, *, business_date=None, channel=""):
    business_date = business_date or timezone.localdate()
    return (
        stores(
            user,
            include_inactive=business_date < timezone.localdate(),
            channel=channel,
        )
        .filter(effective_from__lte=business_date)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=business_date))
    )


def resolve_store(user, *, legal_entity, channel, external_identifier, business_date=None):
    business_date = business_date or timezone.localdate()
    key = normalize_external_key(external_identifier)
    if not key:
        raise ValidationError({"external_identifier": "External store identifier is required."})
    candidates = effective_stores(
        user,
        business_date=business_date,
        channel=channel,
    ).filter(legal_entity=legal_entity)
    matches = []
    for store in candidates:
        identifiers = {
            normalize_external_key(store.code),
            normalize_external_key(store.name),
            normalize_external_key(store.external_account_id),
            *(normalize_external_key(alias) for alias in store.external_aliases),
        }
        if key in identifiers:
            matches.append(store)
    if not matches:
        raise ValidationError({"external_identifier": "No effective Store mapping was found."})
    if len(matches) > 1:
        raise ValidationError({"external_identifier": "Store mapping is ambiguous."})
    return matches[0]


def sku_mappings(user, *, include_inactive=False, search="", store=None):
    queryset = ExternalSKUMap.objects.filter(
        store__legal_entity__in=accessible_legal_entities(user)
    ).select_related("store", "store__legal_entity", "item")
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    if store:
        queryset = queryset.filter(store=store)
    if search:
        queryset = queryset.filter(
            Q(external_sku__icontains=search)
            | Q(external_product_name__icontains=search)
            | Q(external_variation__icontains=search)
            | Q(item__code__icontains=search)
            | Q(item__name__icontains=search)
        )
    return queryset.order_by("store__code", "external_sku", "external_variation")


def effective_sku_mappings(user, *, business_date=None, store=None):
    business_date = business_date or timezone.localdate()
    queryset = (
        sku_mappings(
            user,
            include_inactive=business_date < timezone.localdate(),
            store=store,
        )
        .filter(
            effective_from__lte=business_date,
            store__effective_from__lte=business_date,
            item__effective_from__lte=business_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=business_date))
        .filter(Q(store__effective_to__isnull=True) | Q(store__effective_to__gte=business_date))
        .filter(Q(item__effective_to__isnull=True) | Q(item__effective_to__gte=business_date))
    )
    if business_date >= timezone.localdate():
        queryset = queryset.filter(store__is_active=True, item__is_active=True)
    return queryset


def resolve_external_sku(
    user,
    *,
    store,
    external_sku,
    external_variation="",
    business_date=None,
):
    business_date = business_date or timezone.localdate()
    sku_key = normalize_external_key(external_sku)
    variation_key = normalize_external_key(external_variation)
    if not sku_key:
        raise ValidationError({"external_sku": "External SKU is required."})
    matches = list(
        effective_sku_mappings(user, business_date=business_date, store=store).filter(
            external_sku_normalized=sku_key,
            external_variation_normalized=variation_key,
        )[:2]
    )
    if not matches:
        raise ValidationError({"external_sku": "No effective external SKU mapping was found."})
    if len(matches) > 1:
        raise ValidationError({"external_sku": "External SKU mapping is ambiguous."})
    return matches[0]
