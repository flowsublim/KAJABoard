import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.catalog.services import create_item, create_uom
from apps.channels.services import create_external_sku_mapping, create_store
from apps.core.services import create_document_sequence
from apps.organizations.models import LegalEntity, OrganizationMembership

User = get_user_model()


@pytest.mark.django_db
def test_superuser_can_render_phase_2b_lists_and_preview(client):
    user = User.objects.create_superuser("admin@example.com", "password")
    entity = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    sequence = create_document_sequence(
        legal_entity=entity,
        document_type="SO",
        name="Sales Order",
        prefix="SO-",
        format_template="{prefix}{yyyymmdd}-{seq}",
        padding=4,
    )
    client.force_login(user)

    responses = (
        client.get(reverse("numbering:list")),
        client.get(reverse("numbering:preview", args=(sequence.pk,))),
        client.get(reverse("channels:store-list")),
        client.get(reverse("channels:mapping-list")),
    )

    assert all(response.status_code == 200 for response in responses)
    assert b"Phase 3B" in responses[0].content
    assert b"SO-" in responses[1].content


@pytest.mark.django_db
def test_phase_2b_navigation_is_permission_aware(client):
    user = User.objects.create_user("limited@example.com", "password")
    client.force_login(user)

    response = client.get(reverse("organizations:workspace"))

    assert response.status_code == 200
    assert b"Document Numbering" not in response.content
    assert b"Stores &amp; Channels" not in response.content
    assert b"External SKU Mapping" not in response.content


@pytest.mark.django_db
def test_view_permission_does_not_authorize_store_mutation(client):
    user = User.objects.create_user("viewer@example.com", "password")
    entity = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(Permission.objects.get(codename="view_store"))
    client.force_login(user)

    assert client.get(reverse("channels:store-list")).status_code == 200
    assert client.get(reverse("channels:store-create")).status_code == 403


@pytest.mark.django_db
def test_store_and_mapping_lists_enforce_membership_scope(client):
    user = User.objects.create_user("member@example.com", "password")
    allowed_entity = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    other_entity = LegalEntity.objects.create(code="OTHER", name="Other Entity")
    OrganizationMembership.objects.create(user=user, legal_entity=allowed_entity)
    user.user_permissions.add(
        Permission.objects.get(codename="view_store"),
        Permission.objects.get(codename="view_externalskumap"),
    )
    unit = create_uom(code="PCS", name="Pieces", dimension="COUNT")
    allowed_item = create_item(
        legal_entity=allowed_entity,
        code="ALLOWED-ITEM",
        name="Allowed Item",
        uom=unit,
    )
    other_item = create_item(
        legal_entity=other_entity,
        code="OTHER-ITEM",
        name="Other Item",
        uom=unit,
    )
    allowed_store = create_store(
        legal_entity=allowed_entity,
        code="ALLOWED-STORE",
        name="Allowed Store",
        channel="SHOPEE",
    )
    other_store = create_store(
        legal_entity=other_entity,
        code="OTHER-STORE",
        name="Other Store",
        channel="SHOPEE",
    )
    create_external_sku_mapping(
        store=allowed_store,
        item=allowed_item,
        external_sku="ALLOWED-EXT",
    )
    create_external_sku_mapping(
        store=other_store,
        item=other_item,
        external_sku="OTHER-EXT",
    )
    client.force_login(user)

    store_response = client.get(reverse("channels:store-list"), {"inactive": "1"})
    mapping_response = client.get(reverse("channels:mapping-list"), {"inactive": "1"})

    assert b"ALLOWED-STORE" in store_response.content
    assert b"OTHER-STORE" not in store_response.content
    assert b"ALLOWED-EXT" in mapping_response.content
    assert b"OTHER-EXT" not in mapping_response.content
