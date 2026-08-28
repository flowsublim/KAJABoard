from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.purchasing.models import SubcontractCostType, WorkOrderType
from apps.purchasing.selectors import (
    dispatch_allowance,
    output_remaining,
    subcontract_fulfillment,
    subcontract_hpp_sources,
    warehouse_material_issue_candidates,
    warehouse_subcontract_receipt_candidates,
)
from apps.purchasing.services import (
    accept_subcontract_receipt,
    add_dispatch_line,
    add_material_allocation,
    add_receipt_cost_line,
    add_receipt_output_line,
    add_work_order_output,
    approve_work_order,
    confirm_material_dispatch,
    create_draft_material_dispatch,
    create_draft_subcontract_receipt,
    create_draft_work_order,
    submit_work_order,
)

from .test_work_orders import _foundation


def _approved_subcontract():
    entity, user, output_item, material = _foundation("B2")
    vendor = BusinessPartner.objects.create(legal_entity=entity, code="B2V", display_name="Maklun")
    PartnerRole.objects.create(
        partner=vendor, role_type=PartnerRoleType.SUBCONTRACTOR, effective_from=date(2026, 1, 1)
    )
    work_order = create_draft_work_order(
        legal_entity=entity,
        document_date=date(2026, 8, 27),
        work_order_type=WorkOrderType.SUBCONTRACT,
        vendor=vendor,
        actor=user,
    )
    output = add_work_order_output(
        work_order, item=output_item, target_quantity=Decimal("10"), actor=user
    )
    allocation = add_material_allocation(
        work_order,
        output=output,
        material_item=material,
        planned_quantity=Decimal("10"),
        reference_cost=None,
        actor=user,
    )
    submit_work_order(work_order, actor=user)
    approve_work_order(work_order, actor=user)
    from apps.core.services.numbering import create_document_sequence

    create_document_sequence(
        legal_entity=entity,
        document_type="SUBCONTRACT_DISPATCH",
        name="KB",
        prefix="KB",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
        effective_from=date(2026, 1, 1),
    )
    create_document_sequence(
        legal_entity=entity,
        document_type="SUBCONTRACT_RECEIPT",
        name="TM",
        prefix="TM",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
        effective_from=date(2026, 1, 1),
    )
    return entity, user, work_order, output, allocation


@pytest.mark.django_db
def test_dispatch_partial_allowance_candidate_and_no_cost_fabrication():
    _, user, work_order, _, allocation = _approved_subcontract()
    draft = create_draft_material_dispatch(
        work_order=work_order, dispatch_date=date(2026, 8, 27), actor=user
    )
    add_dispatch_line(draft, allocation=allocation, quantity=4, actor=user)
    assert dispatch_allowance(allocation) == Decimal("10")
    confirm_material_dispatch(draft, actor=user, idempotency_key="dispatch-1")
    assert dispatch_allowance(allocation) == Decimal("6")
    assert warehouse_material_issue_candidates(user)[0].source_key.endswith(
        str(draft.lines.first().pk)
    )
    assert draft.lines.first().reference_cost_snapshot is None
    second = create_draft_material_dispatch(work_order=work_order, dispatch_date=date(2026, 8, 27))
    add_dispatch_line(second, allocation=allocation, quantity=7)
    with pytest.raises(ValidationError):
        confirm_material_dispatch(second)


@pytest.mark.django_db
def test_receipt_partial_output_and_service_cost_contracts():
    _, user, work_order, output, _ = _approved_subcontract()
    receipt = create_draft_subcontract_receipt(
        work_order=work_order, receipt_date=date(2026, 8, 27), actor=user
    )
    add_receipt_output_line(receipt, output=output, accepted_quantity=4, actor=user)
    add_receipt_cost_line(
        receipt,
        cost_type=SubcontractCostType.SPECIFIC_SERVICE,
        output=output,
        amount=Decimal("25"),
        actor=user,
    )
    add_receipt_cost_line(
        receipt, cost_type=SubcontractCostType.SHARED_SERVICE, amount=Decimal("11"), actor=user
    )
    accept_subcontract_receipt(receipt, actor=user, idempotency_key="receipt-1")
    assert output_remaining(output) == Decimal("6")
    assert subcontract_fulfillment(work_order)["status"] == "PARTIAL"
    sources = subcontract_hpp_sources(work_order)
    assert sources["specific_service"][0]["output_id"] == str(output.pk)
    assert sources["shared_service"][0]["output_id"] is None
    assert warehouse_subcontract_receipt_candidates(user)[0].output_id == str(output.pk)
