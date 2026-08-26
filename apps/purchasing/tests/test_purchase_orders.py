from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.catalog.models import UOM, Item
from apps.core.services.numbering import create_document_sequence
from apps.organizations.models import LegalEntity, OrganizationMembership
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.purchasing.models import AccountingTreatment
from apps.purchasing.selectors import committed_cost_sources, treatment_candidates
from apps.purchasing.services import (
    add_purchase_order_line,
    cancel_purchase_order,
    confirm_purchase_order,
    create_draft_purchase_order,
)
from apps.purchasing.services.categories import create_purchase_category

User = get_user_model()


@pytest.mark.django_db
def test_purchase_commitment_snapshots_explicit_category_and_cancellation():
    entity = LegalEntity.objects.create(code="PO", name="PO Entity")
    user = User.objects.create_user("po@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    vendor = BusinessPartner.objects.create(legal_entity=entity, code="V1", display_name="Vendor")
    PartnerRole.objects.create(partner=vendor, role_type=PartnerRoleType.VENDOR)
    uom = UOM.objects.create(code="POPCS", name="Pieces", dimension="COUNT")
    item = Item.objects.create(
        legal_entity=entity, code="POITEM", name="Purchased", uom=uom, purchase_eligible=True
    )
    category = create_purchase_category(
        legal_entity=entity,
        code="INV",
        name="Not inferred",
        accounting_treatment=AccountingTreatment.INVENTORY,
        effective_from=timezone.localdate(),
        actor=user,
    )
    create_document_sequence(
        legal_entity=entity,
        document_type="PURCHASE_ORDER",
        name="PO",
        prefix="PO",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
    )
    order = create_draft_purchase_order(
        legal_entity=entity, vendor=vendor, document_date=timezone.localdate(), actor=user
    )
    line = add_purchase_order_line(
        order,
        purchase_category=category,
        item=item,
        quantity=Decimal("2"),
        unit_price=Decimal("12.50"),
        actor=user,
    )
    assert line.accounting_treatment_snapshot == AccountingTreatment.INVENTORY
    confirm_purchase_order(order, actor=user)
    assert committed_cost_sources(user)[0].amount == Decimal("25.00")
    assert treatment_candidates(user, AccountingTreatment.INVENTORY)[
        0
    ].purchase_order_line_id == str(line.pk)
    cancel_purchase_order(order, actor=user, reason="Commercial correction")
    assert committed_cost_sources(user) == ()


@pytest.mark.django_db
def test_purchase_requires_effective_vendor_role():
    entity = LegalEntity.objects.create(code="POROLE", name="Role Entity")
    vendor = BusinessPartner.objects.create(
        legal_entity=entity, code="NOROLE", display_name="No role"
    )
    create_document_sequence(
        legal_entity=entity,
        document_type="PURCHASE_ORDER",
        name="PO",
        prefix="PO",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
    )
    with pytest.raises(ValidationError):
        create_draft_purchase_order(
            legal_entity=entity, vendor=vendor, document_date=timezone.localdate()
        )
