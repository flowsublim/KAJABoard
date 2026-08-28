from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import Employee
from apps.organizations.models import Warehouse
from apps.production.models import ProductionStage
from apps.production.tests.test_wip import _foundation, _post_work, _ready_handover
from apps.quality.services import (
    create_from_production_handover,
    post_inspection,
    update_draft_line,
)
from apps.warehouse.models import (
    InventoryValuationState,
    MovementDirection,
    MovementType,
    ValuationStatus,
)
from apps.warehouse.selectors import production_material_issue_candidates, stock_movements
from apps.warehouse.services import (
    add_material_issue_line,
    add_production_receipt_line,
    create_material_issue,
    create_production_receipt,
    post_material_issue,
    post_production_receipt,
    post_stock_movement,
)


@pytest.mark.django_db
def test_weighted_average_and_negative_stock_guard():
    entity, user, order, outputs = _foundation("WHAVG")
    warehouse = Warehouse.objects.create(legal_entity=entity, code="FG", name="Finished")
    item = outputs[0].item
    post_stock_movement(
        legal_entity=entity,
        warehouse=warehouse,
        item=item,
        direction=MovementDirection.IN,
        movement_type=MovementType.PRODUCTION_MATERIAL_ISSUE,
        quantity=10,
        source_module="test",
        source_type="OPENING",
        source_document_id="1",
        source_line_id="1",
        source_key="TEST-IN-1",
        transaction_date=date(2026, 8, 27),
        unit_cost=Decimal("10000"),
        total_value=Decimal("100000"),
        actor=user,
        idempotency_key="in-1",
    )
    post_stock_movement(
        legal_entity=entity,
        warehouse=warehouse,
        item=item,
        direction=MovementDirection.IN,
        movement_type=MovementType.PRODUCTION_MATERIAL_ISSUE,
        quantity=10,
        source_module="test",
        source_type="OPENING",
        source_document_id="2",
        source_line_id="2",
        source_key="TEST-IN-2",
        transaction_date=date(2026, 8, 27),
        unit_cost=Decimal("20000"),
        total_value=Decimal("200000"),
        actor=user,
        idempotency_key="in-2",
    )
    state = InventoryValuationState.objects.get(item=item, warehouse=warehouse)
    assert state.quantity_on_hand == Decimal("20")
    assert state.inventory_value == Decimal("300000")
    assert state.average_unit_cost == Decimal("15000")
    with pytest.raises(ValidationError):
        post_stock_movement(
            legal_entity=entity,
            warehouse=warehouse,
            item=item,
            direction=MovementDirection.OUT,
            movement_type=MovementType.PRODUCTION_MATERIAL_ISSUE,
            quantity=21,
            source_module="test",
            source_type="OUT",
            source_document_id="3",
            source_line_id="3",
            source_key="TEST-OUT-1",
            transaction_date=date(2026, 8, 27),
            actor=user,
            idempotency_key="out-too-much",
        )


@pytest.mark.django_db
def test_production_material_issue_is_partial_and_costed():
    entity, user, order, outputs = _foundation("WHISS")
    warehouse = Warehouse.objects.create(legal_entity=entity, code="RM", name="Raw")
    allocation = order.material_allocations.first()
    material = allocation.material_item
    post_stock_movement(
        legal_entity=entity,
        warehouse=warehouse,
        item=material,
        direction=MovementDirection.IN,
        movement_type=MovementType.PRODUCTION_MATERIAL_ISSUE,
        quantity=10,
        source_module="test",
        source_type="OPENING",
        source_document_id="1",
        source_line_id="1",
        source_key="ISS-IN",
        transaction_date=date(2026, 8, 27),
        unit_cost=Decimal("500"),
        total_value=Decimal("5000"),
        actor=user,
        idempotency_key="iss-in",
    )
    issue = create_material_issue(
        legal_entity=entity,
        warehouse=warehouse,
        work_order=order,
        issue_date=date(2026, 8, 27),
        actor=user,
    )
    add_material_issue_line(issue, allocation=allocation, quantity=6, actor=user)
    post_material_issue(issue, actor=user, idempotency_key="issue-1")
    assert production_material_issue_candidates(user, work_order=order)[0][
        "remaining_quantity"
    ] == Decimal("6")
    assert stock_movements(user, item=material).filter(direction=MovementDirection.OUT).count() == 1


@pytest.mark.django_db
def test_production_receipt_accepts_ready_handover_with_pending_valuation():
    entity, user, order, outputs = _foundation("WHREC")
    output = outputs[0]
    _post_work(entity, user, order, [(output, 10)], ProductionStage.CUT, "rec-cut")
    _post_work(entity, user, order, [(output, 10)], ProductionStage.SEW, "rec-sew")
    _post_work(entity, user, order, [(output, 10)], ProductionStage.QC_PACKING, "rec-qc")
    handover = _ready_handover(entity, user, order, [(output, 10)], "rec-hand")
    inspector = Employee.objects.create(
        legal_entity=entity, employee_code="WH-QC", display_name="Warehouse QC"
    )
    inspection = create_from_production_handover(
        handover.lines.first(), inspector=inspector, actor=user, inspection_date=date(2026, 8, 27)
    )
    update_draft_line(inspection.lines.get(), qty_inspected=10, qty_pass=10, actor=user)
    post_inspection(inspection, actor=user, idempotency_key="rec-qc")
    warehouse = Warehouse.objects.create(legal_entity=entity, code="FG2", name="Finished")
    receipt = create_production_receipt(
        legal_entity=entity,
        warehouse=warehouse,
        handover=handover,
        receipt_date=date(2026, 8, 27),
        actor=user,
    )
    add_production_receipt_line(
        receipt, handover_line=handover.lines.first(), accepted_quantity=6, actor=user
    )
    post_production_receipt(receipt, actor=user, idempotency_key="receipt-1")
    state = InventoryValuationState.objects.get(item=output.item, warehouse=warehouse)
    assert state.quantity_on_hand == Decimal("6")
    assert state.valuation_status == ValuationStatus.PENDING_VALUATION
