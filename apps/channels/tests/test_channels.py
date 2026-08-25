from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.catalog.services import create_item, create_uom, deactivate_catalog_master
from apps.channels.models import ExternalSKUMap, Store
from apps.channels.selectors import resolve_external_sku, resolve_store, sku_mappings
from apps.channels.services import (
    create_external_sku_mapping,
    create_store,
    deactivate_channel_master,
    update_external_sku_mapping,
    update_store,
)
from apps.core.models import AuditEvent
from apps.organizations.models import LegalEntity, OrganizationMembership

User = get_user_model()


@pytest.fixture
def entity():
    return LegalEntity.objects.create(code="KAJA", name="PT KAJA")


@pytest.fixture
def user(entity):
    user = User.objects.create_user("member@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    return user


@pytest.fixture
def unit():
    return create_uom(code="PCS", name="Pieces", dimension="COUNT")


@pytest.fixture
def item(entity, unit):
    return create_item(
        legal_entity=entity,
        code="SKU-001",
        name="Canonical Item",
        uom=unit,
        effective_from=date(2026, 1, 1),
    )


@pytest.fixture
def store(entity):
    return create_store(
        legal_entity=entity,
        code="STORE-KIRAL-SHOPEE-01",
        name="Kiral Official",
        channel="shopee",
        external_account_id="shop-123",
        external_aliases=["Kiral BigSeller", " Kiral Official "],
        effective_from=date(2026, 1, 1),
    )


@pytest.mark.django_db
def test_store_service_normalizes_identity_and_writes_audit(entity):
    actor = User.objects.create_user("owner@example.com", "password")
    store = create_store(
        legal_entity=entity,
        code=" store-kiral-shopee-01 ",
        name="Kiral Official",
        channel=" shopee ",
        external_aliases=["Kiral BigSeller", "kiral bigseller"],
        actor=actor,
        reason="Store onboarding",
    )

    assert store.code == "STORE-KIRAL-SHOPEE-01"
    assert store.channel == "SHOPEE"
    assert store.external_aliases == ["Kiral BigSeller"]
    event = AuditEvent.objects.get(target_id=str(store.pk), action="channels.store.created")
    assert event.actor == actor
    assert event.reason == "Store onboarding"


@pytest.mark.django_db
def test_store_identifiers_cannot_overlap_in_same_channel_and_period(entity):
    create_store(
        legal_entity=entity,
        code="STORE-A",
        name="Kiral A",
        channel="SHOPEE",
        external_aliases=["Shared BigSeller Alias"],
    )

    with pytest.raises(ValidationError, match="cannot overlap"):
        create_store(
            legal_entity=entity,
            code="STORE-B",
            name="Kiral B",
            channel="SHOPEE",
            external_account_id="Shared BigSeller Alias",
        )


@pytest.mark.django_db
def test_store_scope_identity_cannot_be_repurposed(store):
    with pytest.raises(ValidationError, match="stable identity fields"):
        update_store(store, channel="TIKTOK", reason="Move platform")


@pytest.mark.django_db
def test_store_rename_preserves_previous_external_identifiers(store, user, entity):
    updated = update_store(
        store,
        name="Kiral Flagship",
        external_account_id="shop-456",
        external_aliases=["New Alias"],
        reason="Marketplace account rename",
    )

    assert updated.pk == store.pk
    assert {"Kiral Official", "shop-123", "New Alias"} <= set(updated.external_aliases)
    assert (
        resolve_store(
            user,
            legal_entity=entity,
            channel="SHOPEE",
            external_identifier="shop-123",
        )
        == updated
    )


@pytest.mark.django_db
def test_inactive_store_remains_resolvable_for_its_historical_period(entity, user):
    yesterday = timezone.localdate() - timedelta(days=1)
    store = create_store(
        legal_entity=entity,
        code="STORE-A",
        name="Historical Store",
        channel="SHOPEE",
        external_aliases=["Historical Alias"],
        effective_from=yesterday,
    )
    deactivate_channel_master(store, reason="Store closed")

    assert (
        resolve_store(
            user,
            legal_entity=entity,
            channel="SHOPEE",
            external_identifier="historical alias",
            business_date=yesterday,
        )
        == store
    )
    with pytest.raises(ValidationError, match="No effective Store"):
        resolve_store(
            user,
            legal_entity=entity,
            channel="SHOPEE",
            external_identifier="historical alias",
        )


@pytest.mark.django_db
def test_external_sku_mapping_is_store_scoped_and_audited(store, item):
    mapping = create_external_sku_mapping(
        store=store,
        item=item,
        external_sku=" SKU EXT 001 ",
        external_variation=" Black / M ",
        conversion_quantity=Decimal("2.500000"),
        reason="Approved exact mapping",
    )

    assert mapping.external_sku_normalized == "sku ext 001"
    assert mapping.external_variation_normalized == "black / m"
    assert mapping.item == item
    assert mapping.conversion_quantity == Decimal("2.500000")
    assert AuditEvent.objects.filter(
        target_id=str(mapping.pk), action="channels.externalskumap.created"
    ).exists()


@pytest.mark.django_db
def test_overlapping_external_sku_mapping_is_rejected(store, item, entity, unit):
    other_item = create_item(
        legal_entity=entity,
        code="SKU-002",
        name="Other",
        uom=unit,
        effective_from=date(2026, 1, 1),
    )
    create_external_sku_mapping(
        store=store,
        item=item,
        external_sku="EXT-001",
        external_variation="RED",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 6, 30),
    )

    with pytest.raises(ValidationError, match="cannot overlap"):
        create_external_sku_mapping(
            store=store,
            item=other_item,
            external_sku="ext-001",
            external_variation="red",
            effective_from=date(2026, 6, 30),
        )


@pytest.mark.django_db
def test_variations_are_exact_independent_mapping_scopes(store, item, entity, unit):
    blue_item = create_item(legal_entity=entity, code="SKU-BLUE", name="Blue", uom=unit)
    red = create_external_sku_mapping(
        store=store,
        item=item,
        external_sku="EXT-001",
        external_variation="RED",
    )
    blue = create_external_sku_mapping(
        store=store,
        item=blue_item,
        external_sku="EXT-001",
        external_variation="BLUE",
    )

    assert red.pk != blue.pk


@pytest.mark.django_db
def test_historical_as_of_resolution_preserves_old_item_mapping(entity, user, unit):
    old_item = create_item(
        legal_entity=entity,
        code="OLD-ITEM",
        name="Old Item",
        uom=unit,
        effective_from=date(2026, 1, 1),
    )
    new_item = create_item(
        legal_entity=entity,
        code="NEW-ITEM",
        name="New Item",
        uom=unit,
        effective_from=date(2026, 7, 1),
    )
    store = create_store(
        legal_entity=entity,
        code="STORE-A",
        name="Store A",
        channel="SHOPEE",
        effective_from=date(2026, 1, 1),
    )
    old_mapping = create_external_sku_mapping(
        store=store,
        item=old_item,
        external_sku="EXT-001",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 6, 30),
    )
    deactivate_channel_master(
        old_mapping,
        reason="Replaced by canonical Item",
        effective_to=date(2026, 6, 30),
    )
    new_mapping = create_external_sku_mapping(
        store=store,
        item=new_item,
        external_sku="EXT-001",
        effective_from=date(2026, 7, 1),
    )

    assert (
        resolve_external_sku(
            user,
            store=store,
            external_sku="ext-001",
            business_date=date(2026, 3, 15),
        )
        == old_mapping
    )
    assert (
        resolve_external_sku(
            user,
            store=store,
            external_sku="EXT-001",
            business_date=date(2026, 8, 1),
        )
        == new_mapping
    )


@pytest.mark.django_db
def test_mapping_rejects_item_from_another_legal_entity(store, unit):
    other_entity = LegalEntity.objects.create(code="OTHER", name="Other Entity")
    other_item = create_item(
        legal_entity=other_entity,
        code="OTHER-ITEM",
        name="Other Item",
        uom=unit,
    )

    with pytest.raises(ValidationError, match="Store legal entity"):
        create_external_sku_mapping(
            store=store,
            item=other_item,
            external_sku="EXT-001",
        )


@pytest.mark.django_db
def test_mapping_period_must_be_covered_by_referenced_item(store, item):
    item = deactivate_catalog_master(
        item,
        reason="Item discontinued",
        effective_to=timezone.localdate(),
    )

    with pytest.raises(ValidationError, match="complete mapping effective period"):
        create_external_sku_mapping(
            store=store,
            item=item,
            external_sku="EXT-001",
            effective_from=date(2026, 1, 1),
        )


@pytest.mark.django_db
def test_effective_mapping_cannot_be_silently_repointed(store, item, entity, unit):
    other_item = create_item(legal_entity=entity, code="SKU-002", name="Other", uom=unit)
    mapping = create_external_sku_mapping(store=store, item=item, external_sku="EXT-001")

    with pytest.raises(ValidationError, match="cannot change historical meaning"):
        update_external_sku_mapping(
            mapping,
            item=other_item,
            reason="Requested remap",
        )


@pytest.mark.django_db
def test_mapping_selector_enforces_legal_entity_membership(entity, unit):
    user = User.objects.create_user("member@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    allowed_item = create_item(legal_entity=entity, code="ALLOWED", name="Allowed", uom=unit)
    allowed_store = create_store(
        legal_entity=entity,
        code="STORE-A",
        name="Store A",
        channel="SHOPEE",
    )
    allowed = create_external_sku_mapping(
        store=allowed_store,
        item=allowed_item,
        external_sku="ALLOWED",
    )
    other_entity = LegalEntity.objects.create(code="OTHER", name="Other")
    other_item = create_item(legal_entity=other_entity, code="OTHER", name="Other", uom=unit)
    other_store = create_store(
        legal_entity=other_entity,
        code="STORE-B",
        name="Store B",
        channel="SHOPEE",
    )
    create_external_sku_mapping(
        store=other_store,
        item=other_item,
        external_sku="OTHER",
    )

    assert list(sku_mappings(user)) == [allowed]
    assert ExternalSKUMap.objects.count() == 2
    assert Store.objects.count() == 2
