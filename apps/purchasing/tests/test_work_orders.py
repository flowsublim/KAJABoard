from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.catalog.models import UOM, Item
from apps.core.services.numbering import create_document_sequence
from apps.organizations.models import LegalEntity, OrganizationMembership
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.purchasing.models import WorkOrderState, WorkOrderType
from apps.purchasing.selectors import (
    approved_internal_work_orders,
    approved_subcontract_work_orders,
)
from apps.purchasing.services import (
    add_material_allocation,
    add_work_order_output,
    approve_work_order,
    create_draft_work_order,
    submit_work_order,
    void_work_order,
)

User = get_user_model()


def _foundation(code="WO"):
    entity = LegalEntity.objects.create(code=code, name=f"{code} Entity")
    user = User.objects.create_user(f"{code.lower()}@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    uom = UOM.objects.create(code=f"{code}PCS", name="Pieces", dimension="COUNT")
    output = Item.objects.create(
        legal_entity=entity,
        code=f"{code}OUT",
        name="Output",
        uom=uom,
        production_eligible=True,
    )
    material = Item.objects.create(
        legal_entity=entity,
        code=f"{code}MAT",
        name="Material",
        uom=uom,
        inventory_eligible=True,
    )
    create_document_sequence(
        legal_entity=entity,
        document_type="WORK_ORDER",
        name="SPK",
        prefix="SPK",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
    )
    return entity, user, output, material


@pytest.mark.django_db
def test_internal_work_order_has_multiple_outputs_and_explicit_material_pairs():
    entity, user, output, material = _foundation()
    work_order = create_draft_work_order(
        legal_entity=entity,
        document_date=date(2026, 8, 27),
        work_order_type=WorkOrderType.INTERNAL,
        actor=user,
        idempotency_key="internal-one",
    )
    same = create_draft_work_order(
        legal_entity=entity,
        document_date=date(2026, 8, 27),
        work_order_type=WorkOrderType.INTERNAL,
        actor=user,
        idempotency_key="internal-one",
    )
    first = add_work_order_output(work_order, item=output, target_quantity="3", actor=user)
    second = add_work_order_output(work_order, item=output, target_quantity="2", actor=user)
    allocation = add_material_allocation(
        work_order,
        output=first,
        material_item=material,
        planned_quantity="4",
        reference_cost=None,
        actor=user,
    )
    assert same.pk == work_order.pk
    assert first.pk != second.pk
    assert allocation.output_id == first.pk
    assert allocation.reference_cost is None
    submit_work_order(work_order, actor=user, idempotency_key="submit-internal-one")
    submit_work_order(work_order, actor=user, idempotency_key="submit-internal-one")
    approve_work_order(work_order, actor=user, idempotency_key="approve-internal-one")
    approve_work_order(work_order, actor=user, idempotency_key="approve-internal-one")
    assert approved_internal_work_orders(user).get(pk=work_order.pk).outputs.count() == 2


@pytest.mark.django_db
def test_subcontract_requires_effective_same_entity_vendor():
    entity, _, _, _ = _foundation("SUB")
    vendor = BusinessPartner.objects.create(legal_entity=entity, code="SUBV", display_name="Vendor")
    with pytest.raises(ValidationError):
        create_draft_work_order(
            legal_entity=entity,
            document_date=date(2026, 8, 27),
            work_order_type=WorkOrderType.SUBCONTRACT,
            vendor=vendor,
        )
    PartnerRole.objects.create(partner=vendor, role_type=PartnerRoleType.SUBCONTRACTOR)
    work_order = create_draft_work_order(
        legal_entity=entity,
        document_date=date(2026, 8, 27),
        work_order_type=WorkOrderType.SUBCONTRACT,
        vendor=vendor,
    )
    assert work_order.vendor_id == vendor.pk


@pytest.mark.django_db
def test_material_allocation_rejects_output_from_another_spk_and_approved_is_immutable():
    entity, user, output, material = _foundation("PAIR")
    first = create_draft_work_order(
        legal_entity=entity, document_date=date(2026, 8, 27), work_order_type=WorkOrderType.INTERNAL
    )
    second = create_draft_work_order(
        legal_entity=entity, document_date=date(2026, 8, 27), work_order_type=WorkOrderType.INTERNAL
    )
    foreign_output = add_work_order_output(second, item=output, target_quantity=1)
    with pytest.raises(ValidationError):
        add_material_allocation(
            first,
            output=foreign_output,
            material_item=material,
            planned_quantity=1,
        )
    local_output = add_work_order_output(first, item=output, target_quantity=1)
    submit_work_order(first, actor=user)
    approve_work_order(first, actor=user)
    with pytest.raises(ValidationError):
        add_material_allocation(
            first, output=local_output, material_item=material, planned_quantity=Decimal("1")
        )


@pytest.mark.django_db
def test_void_requires_reason_and_removes_approved_subcontract_source():
    entity, user, output, _ = _foundation("VOID")
    vendor = BusinessPartner.objects.create(
        legal_entity=entity, code="VOIDV", display_name="Vendor"
    )
    PartnerRole.objects.create(partner=vendor, role_type=PartnerRoleType.VENDOR)
    work_order = create_draft_work_order(
        legal_entity=entity,
        document_date=date(2026, 8, 27),
        work_order_type=WorkOrderType.SUBCONTRACT,
        vendor=vendor,
    )
    add_work_order_output(work_order, item=output, target_quantity=1)
    submit_work_order(work_order)
    approve_work_order(work_order)
    assert approved_subcontract_work_orders(user).filter(pk=work_order.pk).exists()
    with pytest.raises(ValidationError):
        void_work_order(work_order)
    void_work_order(work_order, actor=user, reason="Commercial correction")
    work_order.refresh_from_db()
    assert work_order.state == WorkOrderState.VOID
    assert not approved_subcontract_work_orders(user).filter(pk=work_order.pk).exists()


@pytest.mark.django_db
def test_spk_ui_is_permission_scoped_and_uses_modal_entry_points(client):
    entity, user, output, _ = _foundation("UIWO")
    work_order = create_draft_work_order(
        legal_entity=entity,
        document_date=date(2026, 8, 27),
        work_order_type=WorkOrderType.INTERNAL,
    )
    add_work_order_output(work_order, item=output, target_quantity=1)
    client.force_login(user)
    assert client.get(reverse("purchasing_operations:work-order-list")).status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="view_workorder"))
    response = client.get(reverse("home:home"))
    assert response.status_code == 200
    assert 'href="/purchasing/spk/"' in response.content.decode()
    detail = client.get(reverse("purchasing_operations:work-order-detail", args=[work_order.pk]))
    assert detail.status_code == 200
    assert b"data-modal" in detail.content
    assert b'target="_blank"' not in detail.content
    assert (
        client.get(
            reverse("purchasing_operations:work-order-print", args=[work_order.pk])
        ).status_code
        == 200
    )
