from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.catalog.models import UOM, Item
from apps.catalog.selectors import effective_items
from apps.catalog.services import (
    create_item,
    create_item_category,
    create_uom,
    deactivate_catalog_master,
    update_item,
)
from apps.core.models import AuditEvent
from apps.organizations.models import LegalEntity, OrganizationMembership
from apps.partners.models import PartnerRoleType
from apps.partners.services import create_business_partner

User = get_user_model()


@pytest.fixture
def entity():
    return LegalEntity.objects.create(code="KAJA", name="PT KAJA")


@pytest.fixture
def unit():
    return create_uom(code="PCS", name="Pieces", dimension="COUNT", decimal_places=3)


@pytest.mark.django_db
def test_uom_precision_is_configurable_and_code_is_case_insensitively_unique(unit):
    assert unit.decimal_places == 3

    with pytest.raises(IntegrityError), transaction.atomic():
        UOM.objects.create(code="pcs", name="Duplicate", dimension="COUNT")


@pytest.mark.django_db
def test_item_uses_decimal_quantity_and_explicit_behavior_flags(entity, unit):
    category = create_item_category(code="PROD", name="Production Named Classification")
    item = create_item(
        legal_entity=entity,
        code="SKU-001",
        name="Fractional Item",
        uom=unit,
        category=category,
        minimum_stock=Decimal("0.125000"),
        sales_eligible=True,
        purchase_eligible=False,
        production_eligible=False,
        inventory_eligible=True,
    )

    assert item.minimum_stock == Decimal("0.125000")
    assert item.sales_eligible is True
    assert item.purchase_eligible is False
    assert category.name == "Production Named Classification"


@pytest.mark.django_db
def test_variant_is_a_canonical_item_identity_not_a_duplicate_ledger(entity, unit):
    parent = create_item(legal_entity=entity, code="TSHIRT", name="T-Shirt", uom=unit)
    variant = create_item(
        legal_entity=entity,
        code="TSHIRT-BLK-M",
        name="T-Shirt Black M",
        uom=unit,
        parent_item=parent,
        variant_attributes={"color": "Black", "size": "M"},
    )

    assert isinstance(variant, Item)
    assert variant.parent_item == parent
    assert variant.variant_attributes["size"] == "M"


@pytest.mark.django_db
def test_item_parent_hierarchy_rejects_indirect_cycle(entity, unit):
    parent = create_item(legal_entity=entity, code="PARENT", name="Parent", uom=unit)
    child = create_item(
        legal_entity=entity,
        code="CHILD",
        name="Child",
        uom=unit,
        parent_item=parent,
    )

    with pytest.raises(ValidationError, match="cannot contain a cycle"):
        update_item(parent, parent_item=child, reason="Invalid variant hierarchy")


@pytest.mark.django_db
def test_subcategory_must_belong_to_selected_category(entity, unit):
    category = create_item_category(code="APP", name="Apparel")
    other = create_item_category(code="OTHER", name="Other")
    wrong_subcategory = create_item_category(code="SUB", name="Sub", parent=other)

    with pytest.raises(ValidationError, match="child of the selected category"):
        create_item(
            legal_entity=entity,
            code="SKU-001",
            name="Item",
            uom=unit,
            category=category,
            subcategory=wrong_subcategory,
        )


@pytest.mark.django_db
def test_preferred_vendor_requires_effective_vendor_role(entity, unit):
    customer = create_business_partner(
        legal_entity=entity,
        code="BP-001",
        display_name="Customer Only",
        role_types=(PartnerRoleType.CUSTOMER,),
    )

    with pytest.raises(ValidationError, match="VENDOR role"):
        create_item(
            legal_entity=entity,
            code="SKU-001",
            name="Item",
            uom=unit,
            preferred_vendor=customer,
        )


@pytest.mark.django_db
def test_effective_item_selector_uses_business_date_and_membership_scope(entity, unit):
    user = User.objects.create_user("member@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    create_item(
        legal_entity=entity,
        code="CURRENT",
        name="Current",
        uom=unit,
        effective_from=timezone.localdate(),
    )
    create_item(
        legal_entity=entity,
        code="FUTURE",
        name="Future",
        uom=unit,
        effective_from=timezone.localdate() + timedelta(days=1),
    )

    assert list(effective_items(user).values_list("code", flat=True)) == ["CURRENT"]


@pytest.mark.django_db
def test_catalog_deactivation_preserves_referenced_master_and_audit(entity, unit):
    item = create_item(legal_entity=entity, code="SKU-001", name="Item", uom=unit)
    item = deactivate_catalog_master(item, reason="Discontinued")

    assert item.is_active is False
    assert Item.objects.filter(pk=item.pk).exists()
    assert AuditEvent.objects.filter(
        target_id=str(item.pk), action="catalog.item.deactivated"
    ).exists()
    with pytest.raises(ProtectedError):
        unit.delete()


@pytest.mark.django_db
def test_deactivated_item_remains_selectable_for_prior_business_date(entity, unit):
    user = User.objects.create_user("member@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    yesterday = timezone.localdate() - timedelta(days=1)
    item = create_item(
        legal_entity=entity,
        code="SKU-001",
        name="Item",
        uom=unit,
        effective_from=yesterday,
    )

    deactivate_catalog_master(item, reason="Discontinued")

    assert effective_items(user, business_date=yesterday).get() == item
    assert not effective_items(user).filter(pk=item.pk).exists()
