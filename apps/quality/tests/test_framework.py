from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.models import Employee
from apps.catalog.models import UOM, Item
from apps.core.services.numbering import create_document_sequence
from apps.organizations.models import LegalEntity, OrganizationMembership, Warehouse
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.production.models import ProductionStage
from apps.production.selectors.wip import production_quality_reconciliation
from apps.production.tests.test_wip import _post_work, _ready_handover
from apps.purchasing.models import WorkOrderType
from apps.purchasing.services import (
    add_material_allocation,
    add_work_order_output,
    approve_work_order,
    create_draft_work_order,
    submit_work_order,
)
from apps.quality.models import (
    InspectionType,
    QualityInspection,
    QualityInspectionLine,
    QualityResult,
)
from apps.quality.selectors import (
    quality_disposition_totals,
    quality_pass_authorization,
    return_quality_source_contract,
    rework_candidates,
    subcontract_pass_authorization,
    warehouse_pass_authorizations,
)
from apps.quality.services import (
    add_inspection_line,
    create_from_production_handover,
    create_inspection,
    post_inspection,
    reverse_inspection,
    reverse_inspection_line,
    update_draft_line,
)
from apps.warehouse.models import StockMovement
from apps.warehouse.services import (
    add_production_receipt_line,
    create_production_receipt,
    post_production_receipt,
)

User = get_user_model()


def _quality_source(code="QF"):
    entity = LegalEntity.objects.create(code=code, name=f"{code} Entity")
    user = User.objects.create_user(f"{code.lower()}@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    uom = UOM.objects.create(
        code=f"{code}PCS", name="Pieces", dimension="COUNT", effective_from=date(2026, 1, 1)
    )
    output = Item.objects.create(
        legal_entity=entity,
        code=f"{code}OUT0",
        name="Output 0",
        uom=uom,
        production_eligible=True,
        effective_from=date(2026, 1, 1),
    )
    material = Item.objects.create(
        legal_entity=entity,
        code=f"{code}MAT",
        name="Material",
        uom=uom,
        inventory_eligible=True,
        effective_from=date(2026, 1, 1),
    )
    create_document_sequence(
        legal_entity=entity,
        document_type="WORK_ORDER",
        name="SPK",
        prefix="SPK",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
        effective_from=date(2026, 1, 1),
    )
    order = create_draft_work_order(
        legal_entity=entity,
        document_date=date(2026, 8, 27),
        work_order_type=WorkOrderType.INTERNAL,
        actor=user,
    )
    output = add_work_order_output(order, item=output, target_quantity="100", actor=user)
    add_material_allocation(
        order,
        output=output,
        material_item=material,
        planned_quantity="12",
        reference_cost=None,
        actor=user,
    )
    submit_work_order(order, actor=user)
    approve_work_order(order, actor=user)
    outputs = [output]
    output = outputs[0]
    _post_work(entity, user, order, [(output, 10)], ProductionStage.CUT, f"{code}-cut")
    _post_work(entity, user, order, [(output, 10)], ProductionStage.SEW, f"{code}-sew")
    _post_work(entity, user, order, [(output, 10)], ProductionStage.QC_PACKING, f"{code}-qc")
    handover = _ready_handover(entity, user, order, [(output, 10)], f"{code}-handover")
    employee = Employee.objects.create(
        legal_entity=entity, employee_code=f"{code}-QC", display_name="Quality Inspector"
    )
    return entity, user, order, output, handover, handover.lines.get(), employee


def _posted_inspection(source_line, employee, user, *, quantities, key):
    inspection = create_from_production_handover(
        source_line, inspector=employee, actor=user, inspection_date=date(2026, 8, 27)
    )
    update_draft_line(inspection.lines.get(), actor=user, **quantities)
    return post_inspection(inspection, actor=user, idempotency_key=key)


@pytest.mark.django_db
def test_mixed_line_quantity_conservation_and_pass_only_authorization():
    entity, user, _, _, handover, source_line, employee = _quality_source("MIX")
    posted = _posted_inspection(
        source_line,
        employee,
        user,
        quantities={
            "qty_inspected": 10,
            "qty_pass": 7,
            "qty_hold": 1,
            "qty_reject": 1,
            "qty_rework": 1,
            "reason_text": "Mixed result review",
        },
        key="mix-post",
    )
    line = posted.lines.get()
    assert line.result == ""
    assert quality_disposition_totals(source_line)["inspected_quantity"] == Decimal("10")
    authorization = quality_pass_authorization(source_line)
    assert authorization["remaining_pass_quantity"] == Decimal("7")
    assert StockMovement.objects.count() == 0
    assert (
        warehouse_pass_authorizations(user, handover_line=source_line)[0]["posted_pass_quantity"]
        == 7
    )
    assert production_quality_reconciliation(handover.work_order)[0]["quality_reject_quantity"] == 1


@pytest.mark.django_db
def test_partial_quality_inspections_are_source_line_specific():
    _, user, _, _, _, source_line, employee = _quality_source("PART")
    _posted_inspection(
        source_line,
        employee,
        user,
        quantities={"qty_inspected": 4, "qty_pass": 4},
        key="part-a",
    )
    assert quality_pass_authorization(source_line)["pending_inspection_quantity"] == 6
    _posted_inspection(
        source_line,
        employee,
        user,
        quantities={
            "qty_inspected": 3,
            "qty_pass": 2,
            "qty_rework": 1,
            "reason_text": "Rework needed",
        },
        key="part-b",
    )
    authorization = quality_pass_authorization(source_line)
    assert authorization["pending_inspection_quantity"] == 3
    assert authorization["posted_pass_quantity"] == 6
    assert authorization["posted_rework_quantity"] == 1
    assert rework_candidates(user)[0]["source_key"].startswith("QUALITY_REWORK|")


@pytest.mark.django_db
def test_source_lock_capacity_prevents_two_inspections_from_overpresenting():
    _, user, _, _, _, source_line, employee = _quality_source("LOCKQ")
    first = create_from_production_handover(source_line, inspector=employee, actor=user)
    second = create_from_production_handover(source_line, inspector=employee, actor=user)
    update_draft_line(first.lines.get(), qty_inspected=7, qty_pass=7, actor=user)
    update_draft_line(second.lines.get(), qty_inspected=7, qty_pass=7, actor=user)
    post_inspection(first, actor=user, idempotency_key="lock-first")
    with pytest.raises(ValidationError, match="remaining handover quantity"):
        post_inspection(second, actor=user, idempotency_key="lock-second")


@pytest.mark.django_db
def test_post_is_idempotent_and_line_reversal_preserves_posted_history():
    _, user, _, _, _, source_line, employee = _quality_source("IDEMQ")
    inspection = _posted_inspection(
        source_line,
        employee,
        user,
        quantities={"qty_inspected": 4, "qty_pass": 4},
        key="idemq-post",
    )
    assert post_inspection(inspection, actor=user, idempotency_key="idemq-post") == inspection
    line = inspection.lines.get()
    reversal = reverse_inspection_line(
        line, reason="Correction", actor=user, idempotency_key="idemq-line-reverse"
    )
    assert reversal.original_line_id == line.pk
    assert QualityInspectionLine.objects.get(pk=line.pk).qty_pass == Decimal("4")
    assert quality_pass_authorization(source_line)["posted_pass_quantity"] == 0


@pytest.mark.django_db
def test_quality_pass_authorizes_warehouse_only_up_to_pass_quantity():
    entity, user, _, output, handover, source_line, employee = _quality_source("WHQ")
    _posted_inspection(
        source_line,
        employee,
        user,
        quantities={
            "qty_inspected": 10,
            "qty_pass": 6,
            "qty_hold": 2,
            "qty_reject": 2,
            "reason_text": "Disposition review",
        },
        key="whq-post",
    )
    warehouse = Warehouse.objects.create(legal_entity=entity, code="FG", name="Finished")
    receipt = create_production_receipt(
        legal_entity=entity,
        warehouse=warehouse,
        handover=handover,
        receipt_date=date(2026, 8, 27),
        actor=user,
    )
    add_production_receipt_line(receipt, handover_line=source_line, accepted_quantity=6, actor=user)
    post_production_receipt(receipt, actor=user, idempotency_key="whq-receipt")
    assert StockMovement.objects.count() == 1
    blocked = create_production_receipt(
        legal_entity=entity,
        warehouse=warehouse,
        handover=handover,
        receipt_date=date(2026, 8, 27),
        actor=user,
    )
    with pytest.raises(ValidationError, match="PASS authorization"):
        add_production_receipt_line(
            blocked, handover_line=source_line, accepted_quantity=1, actor=user
        )
    assert output.item_id == source_line.item_id


@pytest.mark.django_db
def test_reversal_retains_original_and_blocks_after_warehouse_consumption():
    entity, user, _, _, handover, source_line, employee = _quality_source("REVQ")
    inspection = _posted_inspection(
        source_line,
        employee,
        user,
        quantities={"qty_inspected": 10, "qty_pass": 10},
        key="revq-post",
    )
    reverse_inspection(
        inspection, reason="No downstream yet", actor=user, idempotency_key="revq-reverse"
    )
    assert inspection.lines.get().reversal is not None
    assert quality_pass_authorization(source_line)["remaining_pass_quantity"] == 0
    replacement = create_from_production_handover(
        source_line, inspector=employee, actor=user, inspection_date=date(2026, 8, 27)
    )
    update_draft_line(replacement.lines.get(), qty_inspected=10, qty_pass=10, actor=user)
    post_inspection(replacement, actor=user, idempotency_key="revq-replacement")
    warehouse = Warehouse.objects.create(legal_entity=entity, code="REV-FG", name="Finished")
    receipt = create_production_receipt(
        legal_entity=entity, warehouse=warehouse, handover=handover, receipt_date=date(2026, 8, 27)
    )
    add_production_receipt_line(receipt, handover_line=source_line, accepted_quantity=8)
    post_production_receipt(receipt, idempotency_key="revq-wh")
    with pytest.raises(ValidationError, match="Warehouse"):
        reverse_inspection(replacement, reason="Unsafe correction", idempotency_key="revq-block")


@pytest.mark.django_db
def test_legacy_unmapped_is_review_only_and_return_contract_is_nonposting():
    entity, user, _, output, _, _, employee = _quality_source("LEGQ")
    normal = create_inspection(
        legal_entity=entity,
        inspection_type=InspectionType.RANDOM_INSPECTION,
        source_module="sales",
        source_type="QC",
        source_document_id="normal-1",
        source_key="NORMAL|1",
        inspection_date=date(2026, 8, 27),
        inspector=employee,
        actor=user,
    )
    with pytest.raises(ValidationError, match="imported or migrated"):
        add_inspection_line(
            normal,
            source_line_id="normal-line-1",
            item=output.item,
            qty_presented=1,
            qty_inspected=1,
            qty_legacy_unmapped=1,
            result=QualityResult.LEGACY_UNMAPPED,
            actor=user,
        )
    inspection = create_inspection(
        legal_entity=entity,
        inspection_type=InspectionType.RANDOM_INSPECTION,
        source_module="legacy",
        source_type="AMBIGUOUS_QC",
        source_document_id="legacy-1",
        source_key="LEGACY|1",
        inspection_date=date(2026, 8, 27),
        inspector=employee,
        actor=user,
    )
    add_inspection_line(
        inspection,
        source_line_id="legacy-line-1",
        item=output.item,
        qty_presented=5,
        qty_inspected=5,
        qty_legacy_unmapped=5,
        result=QualityResult.LEGACY_UNMAPPED,
        actor=user,
    )
    post_inspection(inspection, actor=user, idempotency_key="legacy-post")
    assert quality_pass_authorization(_quality_source("LEGQ2")[5])["posted_pass_quantity"] == 0
    assert (
        return_quality_source_contract(
            legal_entity_id=entity.pk,
            source_module="sales",
            source_type="CUSTOMER_RETURN",
            source_document_id="return-1",
            source_key="RETURN|1",
            source_line_id="return-line-1",
            item_id=output.pk,
            quantity=2,
        )["stock_effect"]
        == "NONE"
    )


@pytest.mark.django_db
def test_customer_return_pass_is_only_a_future_warehouse_authorization():
    entity, user, _, output, _, _, employee = _quality_source("RETQ")
    inspection = create_inspection(
        legal_entity=entity,
        inspection_type=InspectionType.CUSTOMER_RETURN,
        source_module="sales",
        source_type="CUSTOMER_RETURN",
        source_document_id="return-1",
        source_key="QUALITY|RETURN|1",
        inspection_date=date(2026, 8, 27),
        inspector=employee,
        actor=user,
    )
    add_inspection_line(
        inspection,
        source_line_id="return-line-1",
        item=output.item,
        qty_presented=2,
        qty_inspected=2,
        qty_pass=2,
        actor=user,
    )
    post_inspection(inspection, actor=user, idempotency_key="return-qc-post")
    assert StockMovement.objects.count() == 0


@pytest.mark.django_db
def test_subcontract_qc_preserves_receipt_line_and_exposes_pass_contract():
    entity = LegalEntity.objects.create(code="SUBQ", name="SUBQ Entity")
    user = User.objects.create_user("subq@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    uom = UOM.objects.create(
        code="SUBQPCS", name="Pieces", dimension="COUNT", effective_from=date(2026, 1, 1)
    )
    output_item = Item.objects.create(
        legal_entity=entity,
        code="SUBQOUT",
        name="Subcontract output",
        uom=uom,
        production_eligible=True,
        effective_from=date(2026, 1, 1),
    )
    material = Item.objects.create(
        legal_entity=entity,
        code="SUBQMAT",
        name="Subcontract material",
        uom=uom,
        inventory_eligible=True,
        effective_from=date(2026, 1, 1),
    )
    vendor = BusinessPartner.objects.create(
        legal_entity=entity,
        code="SUBQV",
        display_name="Maklun",
        effective_from=date(2026, 1, 1),
    )
    PartnerRole.objects.create(
        partner=vendor,
        role_type=PartnerRoleType.SUBCONTRACTOR,
        effective_from=date(2026, 1, 1),
    )
    create_document_sequence(
        legal_entity=entity,
        document_type="WORK_ORDER",
        name="SPK",
        prefix="SPK",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
        effective_from=date(2026, 1, 1),
    )
    work_order = create_draft_work_order(
        legal_entity=entity,
        document_date=date(2026, 8, 27),
        work_order_type=WorkOrderType.SUBCONTRACT,
        vendor=vendor,
        actor=user,
    )
    output = add_work_order_output(work_order, item=output_item, target_quantity=10, actor=user)
    add_material_allocation(
        work_order,
        output=output,
        material_item=material,
        planned_quantity=10,
        reference_cost=None,
        actor=user,
    )
    submit_work_order(work_order, actor=user)
    approve_work_order(work_order, actor=user)
    for document_type, name, prefix in (
        ("SUBCONTRACT_DISPATCH", "KB", "KB"),
        ("SUBCONTRACT_RECEIPT", "TM", "TM"),
    ):
        create_document_sequence(
            legal_entity=entity,
            document_type=document_type,
            name=name,
            prefix=prefix,
            format_template="{prefix}-{yyyymmdd}-{seq}",
            padding=3,
            effective_from=date(2026, 1, 1),
        )
    from apps.purchasing.services import (
        accept_subcontract_receipt,
        add_receipt_output_line,
        create_draft_subcontract_receipt,
    )

    receipt = create_draft_subcontract_receipt(
        work_order=work_order, receipt_date=date(2026, 8, 27), actor=user
    )
    add_receipt_output_line(receipt, output=output, accepted_quantity=4, actor=user)
    accept_subcontract_receipt(receipt, actor=user, idempotency_key="sub-qc-receipt")
    receipt_line = receipt.output_lines.get()
    inspector = Employee.objects.create(
        legal_entity=entity, employee_code="SUB-QC", display_name="Subcontract QC"
    )
    inspection = create_inspection(
        legal_entity=entity,
        inspection_type=InspectionType.SUBCONTRACT_RECEIPT,
        source_module="purchasing",
        source_type="SUBCONTRACT_RECEIPT",
        source_document_id=receipt.pk,
        source_key=f"QUALITY|SUBCONTRACT|{receipt_line.pk}",
        inspection_date=date(2026, 8, 27),
        inspector=inspector,
        actor=user,
    )
    add_inspection_line(
        inspection,
        source_line_id=str(receipt_line.pk),
        subcontract_receipt_line=receipt_line,
        work_order_output=output,
        item=output.item,
        qty_presented=4,
        qty_inspected=4,
        qty_pass=4,
        actor=user,
    )
    post_inspection(inspection, actor=user, idempotency_key="sub-qc-post")
    authorization = subcontract_pass_authorization(receipt_line)
    assert authorization["posted_pass_quantity"] == Decimal("4")
    assert authorization["warehouse_posting"] == "NOT_IMPLEMENTED"
    receipt.refresh_from_db()
    assert receipt.state == "ACCEPTED"
    assert StockMovement.objects.count() == 0


@pytest.mark.django_db
def test_quality_routes_are_permission_aware_and_get_is_read_only(client):
    entity, user, _, _, _, _, _ = _quality_source("ROUTEQ")
    client.force_login(user)
    assert client.get(reverse("quality:dashboard")).status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="view_qualityinspection"))
    before = (
        QualityInspection.objects.count(),
        QualityInspectionLine.objects.count(),
        StockMovement.objects.count(),
    )
    assert client.get(reverse("quality:dashboard")).status_code == 200
    assert client.get(reverse("quality:inspection-list")).status_code == 200
    assert client.get(reverse("quality:production-queue")).status_code == 200
    assert (
        QualityInspection.objects.count(),
        QualityInspectionLine.objects.count(),
        StockMovement.objects.count(),
    ) == before
