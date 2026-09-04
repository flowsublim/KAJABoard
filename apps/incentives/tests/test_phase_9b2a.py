"""Phase 9B2A Tests: CPO Finished Goods Fee — Authoritative Source + Beneficiary + Accrual.

Tests verify:
- Authoritative trigger: WarehouseReceipt POSTED + accepted_quantity
- Strict source lineage:
  WarehouseReceiptLine -> WarehouseReceipt -> Handover -> WorkOrder -> Output -> Item
- Explicit Production handover beneficiary (cpo_beneficiary) with zero inference
- Item-scoped rule resolution with no silent generic fallback
- Exact whole-Rupiah PER_UNIT calculations and fractional Rupiah blocking
- Idempotency and deterministic source_key
- Historical immutability of snapshots
- Explicit Project lineage and zero inference
- Project profitability integration (CPO_FEE authoritative vs reversed, SALES_FEE PENDING_SOURCE)
- Zero Finance posting and zero stock movement
- Beneficiary lock after CPO accrual
- Warehouse source reversal and idempotent incentive reversal
- Legacy SMB GAS immutability
"""

import datetime
import hashlib
import pathlib
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Employee
from apps.catalog.models import UOM, Item
from apps.finance.models import JournalEntry, JournalLine, LiquidityEntry, Payment
from apps.incentives.models import (
    BeneficiaryKind,
    IncentiveAccrual,
    IncentiveAccrualReversal,
    IncentiveAccrualState,
    IncentiveCalculationMethod,
    IncentiveRule,
    IncentiveTriggerType,
    IncentiveType,
)
from apps.incentives.selectors.cpo import (
    get_cpo_candidate_for_receipt_line,
    get_cpo_candidates_for_receipt,
    get_eligible_cpo_candidates,
)
from apps.incentives.services.cpo import (
    accrue_cpo_fee_for_receipt_line,
    reverse_cpo_fee_for_receipt_line,
    reverse_cpo_fees_for_receipt,
)
from apps.organizations.models import LegalEntity, Warehouse
from apps.production.models import (
    ProductionHandoverState,
    ProductionWarehouseHandover,
    ProductionWarehouseHandoverLine,
)
from apps.production.services.production import update_handover_draft
from apps.projects.models import ProjectBudgetCategory
from apps.projects.selectors.profitability import (
    AUTHORITATIVE_AVAILABLE,
    PENDING_SOURCE,
    project_profitability,
)
from apps.projects.services import create_draft_project
from apps.purchasing.models import WorkOrderOutput, WorkOrderType
from apps.warehouse.models import (
    StockMovement,
    WarehouseDocumentState,
    WarehouseReceipt,
    WarehouseReceiptLine,
)

User = get_user_model()


@pytest.fixture
def cpo_fixture():
    entity = LegalEntity.objects.create(code="E9B2A", name="Entity 9B2A")
    other_entity = LegalEntity.objects.create(code="E_OTHER", name="Entity Other")

    wh = Warehouse.objects.create(
        legal_entity=entity, code="WH-FG", name="Finished Goods Warehouse"
    )
    user = User.objects.create_user("cpo_user@example.com", "password")

    uom = UOM.objects.create(code="PCS9B2", name="Pieces 9B2", dimension="COUNT")

    item_a = Item.objects.create(
        legal_entity=entity,
        code="ITEM-CPO-A",
        name="Finished Product A",
        uom=uom,
        sales_eligible=True,
    )
    item_b = Item.objects.create(
        legal_entity=entity,
        code="ITEM-CPO-B",
        name="Finished Product B",
        uom=uom,
        sales_eligible=True,
    )

    employee = Employee.objects.create(
        legal_entity=entity,
        employee_code="SPV-CPO-01",
        display_name="SPV Production Budi",
        is_active=True,
    )
    inactive_employee = Employee.objects.create(
        legal_entity=entity,
        employee_code="SPV-INACTIVE",
        display_name="Inactive Supervisor",
        is_active=False,
    )
    cross_entity_employee = Employee.objects.create(
        legal_entity=other_entity,
        employee_code="SPV-OTHER",
        display_name="Other Entity Supervisor",
        is_active=True,
    )

    from apps.core.services.numbering import create_document_sequence
    from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType

    customer = BusinessPartner.objects.create(
        legal_entity=entity, code="CUST-CPO-01", display_name="Cust CPO 01"
    )
    PartnerRole.objects.create(partner=customer, role_type=PartnerRoleType.CUSTOMER)

    create_document_sequence(
        legal_entity=entity,
        document_type="PROJECT",
        name="PROJECT",
        prefix="PRJ",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
        effective_from=datetime.date(2026, 1, 1),
    )

    project = create_draft_project(
        legal_entity=entity,
        customer=customer,
        name="Project CPO Test",
        start_date=timezone.localdate(),
        actor=user,
        idempotency_key="prj-cpo-init",
    )
    from apps.projects.models import ProjectState

    project.state = ProjectState.ACTIVE
    project.save(update_fields=("state", "updated_at"))

    create_document_sequence(
        legal_entity=entity,
        document_type="WORK_ORDER",
        name="WORK_ORDER",
        prefix="WO",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
        effective_from=datetime.date(2026, 1, 1),
    )

    from apps.purchasing.models import WorkOrderState
    from apps.purchasing.services import create_draft_work_order

    # Work order with explicit project
    work_order = create_draft_work_order(
        legal_entity=entity,
        document_date=datetime.date(2026, 3, 1),
        work_order_type=WorkOrderType.INTERNAL,
        project=project,
        actor=user,
        idempotency_key="wo-cpo-001",
    )
    work_order.state = WorkOrderState.APPROVED
    work_order.save(update_fields=("state", "updated_at"))

    output_a = WorkOrderOutput.objects.create(
        work_order=work_order,
        item=item_a,
        item_code_snapshot=item_a.code,
        item_name_snapshot=item_a.name,
        uom_code_snapshot=uom.code,
        target_quantity=Decimal("100"),
        line_number=1,
    )
    output_b = WorkOrderOutput.objects.create(
        work_order=work_order,
        item=item_b,
        item_code_snapshot=item_b.code,
        item_name_snapshot=item_b.name,
        uom_code_snapshot=uom.code,
        target_quantity=Decimal("50"),
        line_number=2,
    )

    # Work order without project
    work_order_no_proj = create_draft_work_order(
        legal_entity=entity,
        document_date=datetime.date(2026, 3, 1),
        work_order_type=WorkOrderType.INTERNAL,
        project=None,
        actor=user,
        idempotency_key="wo-cpo-noproj",
    )
    work_order_no_proj.state = WorkOrderState.APPROVED
    work_order_no_proj.save(update_fields=("state", "updated_at"))
    output_no_proj = WorkOrderOutput.objects.create(
        work_order=work_order_no_proj,
        item=item_a,
        item_code_snapshot=item_a.code,
        item_name_snapshot=item_a.name,
        uom_code_snapshot=uom.code,
        target_quantity=Decimal("100"),
        line_number=1,
    )

    # Production Handover
    handover = ProductionWarehouseHandover.objects.create(
        legal_entity=entity,
        work_order=work_order,
        handover_date=datetime.date(2026, 3, 2),
        cpo_beneficiary=employee,
        state=ProductionHandoverState.READY_FOR_GUDANG,
        created_by=user,
        ready_by=user,
    )
    ho_line_a = ProductionWarehouseHandoverLine.objects.create(
        handover=handover,
        output=output_a,
        item=item_a,
        item_code_snapshot=item_a.code,
        item_name_snapshot=item_a.name,
        uom_code_snapshot=uom.code,
        quantity=Decimal("100"),
        sequence=1,
    )
    ho_line_b = ProductionWarehouseHandoverLine.objects.create(
        handover=handover,
        output=output_b,
        item=item_b,
        item_code_snapshot=item_b.code,
        item_name_snapshot=item_b.name,
        uom_code_snapshot=uom.code,
        quantity=Decimal("50"),
        sequence=2,
    )

    # CPO Incentive Rule for item_a
    rule_item_a = IncentiveRule.objects.create(
        legal_entity=entity,
        code="RULE-CPO-ITEM-A",
        name="CPO Fee Item A",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
        item=item_a,
        is_active=True,
    )

    return {
        "entity": entity,
        "other_entity": other_entity,
        "wh": wh,
        "user": user,
        "uom": uom,
        "item_a": item_a,
        "item_b": item_b,
        "employee": employee,
        "inactive_employee": inactive_employee,
        "cross_entity_employee": cross_entity_employee,
        "project": project,
        "work_order": work_order,
        "work_order_no_proj": work_order_no_proj,
        "output_a": output_a,
        "output_b": output_b,
        "output_no_proj": output_no_proj,
        "handover": handover,
        "ho_line_a": ho_line_a,
        "ho_line_b": ho_line_b,
        "rule_item_a": rule_item_a,
    }


# =========================================================================
# 1. Draft WarehouseReceipt produces no CPO candidate ready for accrual
# =========================================================================
@pytest.mark.django_db
def test_1_draft_warehouse_receipt_produces_no_ready_candidate(cpo_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.DRAFT,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("40"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    cand = get_cpo_candidate_for_receipt_line(line)
    assert cand.status == "NOT_POSTED"
    assert "DRAFT" in cand.reason or "Only POSTED" in cand.reason

    with pytest.raises(ValidationError) as exc:
        accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])
    assert "NOT_POSTED" in str(exc.value)


# =========================================================================
# 2. POSTED production WarehouseReceiptLine is an eligible CPO source
# =========================================================================
@pytest.mark.django_db
def test_2_posted_production_receipt_line_is_eligible(cpo_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        posted_at=timezone.now(),
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("60"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    cand = get_cpo_candidate_for_receipt_line(line)
    assert cand.status == "READY"
    assert cand.accepted_quantity == Decimal("60")
    assert cand.rate_value == Decimal("500.0000")
    assert cand.calculated_amount == Decimal("30000")  # 60 * 500


# =========================================================================
# 3. Basis uses accepted_quantity exactly
# 4. Production handover quantity is NOT substituted for Warehouse accepted quantity
# =========================================================================
@pytest.mark.django_db
def test_3_4_basis_uses_accepted_quantity_not_handover_quantity(cpo_fixture):
    # Handover line quantity was 100
    assert cpo_fixture["ho_line_a"].quantity == Decimal("100")

    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    # Warehouse accepts only 75
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("75"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])
    assert accrual.basis_quantity == Decimal("75")
    assert accrual.basis_quantity != Decimal("100")
    assert accrual.amount == Decimal("37500")  # 75 * 500, NOT 100 * 500 = 50000


# =========================================================================
# 5. Wrong Warehouse receipt/source type excluded
# =========================================================================
@pytest.mark.django_db
def test_5_wrong_warehouse_receipt_source_type_excluded(cpo_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="purchasing",
        source_type="PURCHASE_RECEIPT",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("50"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    cand = get_cpo_candidate_for_receipt_line(line)
    assert cand.status == "INVALID_SOURCE"
    with pytest.raises(ValidationError) as exc:
        accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])
    assert "INVALID_SOURCE" in str(exc.value)


# =========================================================================
# 6. Item-specific effective CPO rule selected on receipt_date
# =========================================================================
@pytest.mark.django_db
def test_6_item_specific_effective_rule_selected(cpo_fixture):
    # Rule effective from 2026-01-01 to 2026-06-30
    cpo_fixture["rule_item_a"].effective_to = datetime.date(2026, 6, 30)
    cpo_fixture["rule_item_a"].save()

    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 10),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    cand = get_cpo_candidate_for_receipt_line(line)
    assert cand.status == "READY"
    assert cand.rate_value == Decimal("500.0000")


# =========================================================================
# 7. No exact Item rule → PENDING_RULE; no silent generic fallback
# =========================================================================
@pytest.mark.django_db
def test_7_no_exact_item_rule_pending_rule_no_generic_fallback(cpo_fixture):
    # Create a generic unscoped rule (item=None)
    IncentiveRule.objects.create(
        legal_entity=cpo_fixture["entity"],
        code="RULE-CPO-GENERIC",
        name="Generic CPO Fee",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("200.0000"),
        effective_from=datetime.date(2026, 1, 1),
        item=None,
        is_active=True,
    )
    # Line for item_b which has no item-specific rule
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 10),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line_b = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_b"],
        output=cpo_fixture["output_b"],
        item=cpo_fixture["item_b"],
        source_key=f"REC|{receipt.pk}|2",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2",
        sequence=2,
    )
    cand = get_cpo_candidate_for_receipt_line(line_b)
    # Must NOT silently fall back to generic rule!
    assert cand.status == "PENDING_RULE"
    with pytest.raises(ValidationError) as exc:
        accrue_cpo_fee_for_receipt_line(line_b, actor=cpo_fixture["user"])
    assert "PENDING_RULE" in str(exc.value)


# =========================================================================
# 8. Missing explicit handover beneficiary → PENDING_BENEFICIARY
# 9. posted_by / ready_by / actor never becomes beneficiary by inference
# =========================================================================
@pytest.mark.django_db
def test_8_9_missing_beneficiary_pending_no_actor_inference(cpo_fixture):
    # Handover without beneficiary
    handover_no_ben = ProductionWarehouseHandover.objects.create(
        legal_entity=cpo_fixture["entity"],
        work_order=cpo_fixture["work_order"],
        handover_date=datetime.date(2026, 3, 2),
        cpo_beneficiary=None,  # MISSING
        state=ProductionHandoverState.READY_FOR_GUDANG,
        created_by=cpo_fixture["user"],
        ready_by=cpo_fixture["user"],
    )
    ho_line = ProductionWarehouseHandoverLine.objects.create(
        handover=handover_no_ben,
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        item_code_snapshot=cpo_fixture["item_a"].code,
        item_name_snapshot=cpo_fixture["item_a"].name,
        uom_code_snapshot="PCS9B2",
        quantity=Decimal("50"),
        sequence=1,
    )
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=handover_no_ben,
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        posted_by=cpo_fixture["user"],
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=ho_line,
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("50"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    cand = get_cpo_candidate_for_receipt_line(line)
    assert cand.status == "PENDING_BENEFICIARY"
    # Never infer from posted_by, ready_by, or actor
    assert cand.beneficiary_id is None
    with pytest.raises(ValidationError) as exc:
        accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])
    assert "PENDING_BENEFICIARY" in str(exc.value)


# =========================================================================
# 10. Explicit Employee beneficiary snapshot preserved
# =========================================================================
@pytest.mark.django_db
def test_10_explicit_beneficiary_snapshot_preserved(cpo_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("20"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])
    assert accrual.beneficiary_type == BeneficiaryKind.EMPLOYEE
    assert accrual.beneficiary_id == str(cpo_fixture["employee"].pk)
    assert accrual.beneficiary_code_snapshot == "SPV-CPO-01"
    assert accrual.beneficiary_name_snapshot == "SPV Production Budi"


# =========================================================================
# 11. Cross-entity beneficiary rejected
# =========================================================================
@pytest.mark.django_db
def test_11_cross_entity_beneficiary_rejected(cpo_fixture):
    # Model clean rejects cross-entity beneficiary
    invalid_handover = ProductionWarehouseHandover(
        legal_entity=cpo_fixture["entity"],
        work_order=cpo_fixture["work_order"],
        handover_date=datetime.date(2026, 3, 2),
        cpo_beneficiary=cpo_fixture["cross_entity_employee"],
    )
    with pytest.raises(ValidationError) as exc:
        invalid_handover.full_clean()
    assert "cpo_beneficiary" in exc.value.message_dict


# =========================================================================
# 12. Inactive beneficiary rejected according to accepted Employee rules
# =========================================================================
@pytest.mark.django_db
def test_12_inactive_beneficiary_rejected(cpo_fixture):
    inactive_handover = ProductionWarehouseHandover(
        legal_entity=cpo_fixture["entity"],
        work_order=cpo_fixture["work_order"],
        handover_date=datetime.date(2026, 3, 2),
        cpo_beneficiary=cpo_fixture["inactive_employee"],
    )
    with pytest.raises(ValidationError) as exc:
        inactive_handover.full_clean()
    assert "cpo_beneficiary" in exc.value.message_dict


# =========================================================================
# 13. PER_UNIT CPO calculation exact
# =========================================================================
@pytest.mark.django_db
def test_13_per_unit_calculation_exact(cpo_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("125"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])
    # 125 * 500 = 62500
    assert accrual.amount == Decimal("62500.00")
    assert accrual.rate_snapshot == Decimal("500.0000")


# =========================================================================
# 14. Fractional Rupiah result blocks accrual
# =========================================================================
@pytest.mark.django_db
def test_14_fractional_rupiah_result_blocks_accrual(cpo_fixture):
    cpo_fixture["rule_item_a"].rate_value = Decimal("500.2500")
    cpo_fixture["rule_item_a"].save()

    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("1"),  # 1 * 500.25 = 500.25 (fractional)
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    cand = get_cpo_candidate_for_receipt_line(line)
    assert cand.status == "NON_WHOLE_RUPIAH_RESULT"
    with pytest.raises(ValidationError) as exc:
        accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])
    assert "NON_WHOLE_RUPIAH_RESULT" in str(exc.value)


# =========================================================================
# 15. One WarehouseReceiptLine → one CPO accrual
# 16. Same line retry idempotent
# 17. Two lines create two distinct accruals
# 18. Source key includes incentive type + line identity
# =========================================================================
@pytest.mark.django_db
def test_15_16_17_18_idempotency_distinct_lines_source_key(cpo_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line_1 = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("30"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    line_2 = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|2",
        accepted_quantity=Decimal("20"),
        uom_code_snapshot="PCS9B2",
        sequence=2,
    )

    accrual_1 = accrue_cpo_fee_for_receipt_line(line_1, actor=cpo_fixture["user"])
    expected_key_1 = f"CPO_FEE|warehouse|WAREHOUSE_RECEIPT_LINE|{line_1.pk}"
    assert accrual_1.source_key == expected_key_1
    assert accrual_1.amount == Decimal("15000.00")

    # 16. Retry same line returns identical object without duplicate
    accrual_1_retry = accrue_cpo_fee_for_receipt_line(line_1, actor=cpo_fixture["user"])
    assert accrual_1_retry.pk == accrual_1.pk
    assert IncentiveAccrual.objects.filter(source_key=expected_key_1).count() == 1

    # 17. Second line creates distinct accrual
    accrual_2 = accrue_cpo_fee_for_receipt_line(line_2, actor=cpo_fixture["user"])
    expected_key_2 = f"CPO_FEE|warehouse|WAREHOUSE_RECEIPT_LINE|{line_2.pk}"
    assert accrual_2.source_key == expected_key_2
    assert accrual_2.amount == Decimal("10000.00")
    assert accrual_1.pk != accrual_2.pk


# =========================================================================
# 19. Rule mutation after accrual does not alter historical CPO rate/amount
# =========================================================================
@pytest.mark.django_db
def test_19_rule_mutation_after_accrual_preserves_history(cpo_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])
    assert accrual.amount == Decimal("5000.00")
    assert accrual.rate_snapshot == Decimal("500.0000")

    # Mutate rule
    rule = cpo_fixture["rule_item_a"]
    rule.rate_value = Decimal("9999.0000")
    rule.save()

    accrual.refresh_from_db()
    assert accrual.amount == Decimal("5000.00")
    assert accrual.rate_snapshot == Decimal("500.0000")


# =========================================================================
# 20. Beneficiary master rename after accrual does not alter historical snapshot
# =========================================================================
@pytest.mark.django_db
def test_20_beneficiary_rename_preserves_snapshot(cpo_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])
    assert accrual.beneficiary_name_snapshot == "SPV Production Budi"

    # Rename employee
    emp = cpo_fixture["employee"]
    emp.display_name = "Completely Renamed Supervisor"
    emp.save()

    accrual.refresh_from_db()
    assert accrual.beneficiary_name_snapshot == "SPV Production Budi"


# =========================================================================
# 21. WorkOrder.project populates accrual Project only through direct FK
# 22. Missing WorkOrder.project leaves accrual.project null
# 23. No project inference
# =========================================================================
@pytest.mark.django_db
def test_21_22_23_explicit_project_lineage_and_no_inference(cpo_fixture):
    # With project
    receipt_with_proj = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],  # has project
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line_with_proj = WarehouseReceiptLine.objects.create(
        receipt=receipt_with_proj,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt_with_proj.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    accrual_proj = accrue_cpo_fee_for_receipt_line(line_with_proj, actor=cpo_fixture["user"])
    assert accrual_proj.project_id == cpo_fixture["project"].pk

    # Without project
    handover_no_proj = ProductionWarehouseHandover.objects.create(
        legal_entity=cpo_fixture["entity"],
        work_order=cpo_fixture["work_order_no_proj"],  # no project
        handover_date=datetime.date(2026, 3, 2),
        cpo_beneficiary=cpo_fixture["employee"],
        state=ProductionHandoverState.READY_FOR_GUDANG,
    )
    ho_line_no_proj = ProductionWarehouseHandoverLine.objects.create(
        handover=handover_no_proj,
        output=cpo_fixture["output_no_proj"],
        item=cpo_fixture["item_a"],
        item_code_snapshot=cpo_fixture["item_a"].code,
        item_name_snapshot=cpo_fixture["item_a"].name,
        uom_code_snapshot="PCS9B2",
        quantity=Decimal("50"),
        sequence=1,
    )
    receipt_no_proj = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order_no_proj"],
        handover=handover_no_proj,
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line_no_proj = WarehouseReceiptLine.objects.create(
        receipt=receipt_no_proj,
        handover_line=ho_line_no_proj,
        output=cpo_fixture["output_no_proj"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt_no_proj.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    accrual_no_proj = accrue_cpo_fee_for_receipt_line(line_no_proj, actor=cpo_fixture["user"])
    # 22. Missing project leaves accrual.project null; 23. strictly no inference
    assert accrual_no_proj.project is None


# =========================================================================
# 24. Project profitability consumes existing CPO IncentiveAccrual as CPO_FEE actual category
# 25. Project profitability does NOT recalculate CPO from Warehouse qty × current rule
# 26. Reversed CPO accrual no longer contributes as active Project CPO actual cost
# 27. SALES_FEE remains PENDING_SOURCE
# =========================================================================
@pytest.mark.django_db
def test_24_25_26_27_project_profitability_integration(cpo_fixture):
    project = cpo_fixture["project"]

    # Before CPO accrual, CPO_FEE and SALES_FEE are PENDING_SOURCE
    prof_before = project_profitability(project)
    assert (
        prof_before.actual_categories[ProjectBudgetCategory.CPO_FEE].availability == PENDING_SOURCE
    )
    assert (
        prof_before.actual_categories[ProjectBudgetCategory.SALES_FEE].availability
        == PENDING_SOURCE
    )

    # Create CPO accrual for project
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("40"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])
    assert accrual.amount == Decimal("20000.00")  # 40 * 500

    # 24. Project profitability consumes existing CPO IncentiveAccrual
    prof_after = project_profitability(project)
    cpo_cat = prof_after.actual_categories[ProjectBudgetCategory.CPO_FEE]
    assert cpo_cat.availability == AUTHORITATIVE_AVAILABLE
    assert cpo_cat.amount == Decimal("20000.00")
    assert cpo_cat.record_count == 1
    # 27. SALES_FEE remains PENDING_SOURCE
    assert (
        prof_after.actual_categories[ProjectBudgetCategory.SALES_FEE].availability == PENDING_SOURCE
    )

    # 25. Mutating rule does NOT alter profitability CPO cost
    cpo_fixture["rule_item_a"].rate_value = Decimal("9999.0000")
    cpo_fixture["rule_item_a"].save()

    prof_after_mutation = project_profitability(project)
    assert prof_after_mutation.actual_categories[ProjectBudgetCategory.CPO_FEE].amount == Decimal(
        "20000.00"
    )

    # 26. Reverse CPO accrual -> no longer contributes to active actual cost
    reverse_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"], reason="Cancelled batch")
    accrual.refresh_from_db()
    assert accrual.state == IncentiveAccrualState.REVERSED

    prof_after_rev = project_profitability(project)
    cpo_cat_rev = prof_after_rev.actual_categories[ProjectBudgetCategory.CPO_FEE]
    assert cpo_cat_rev.amount == Decimal("0")
    assert cpo_cat_rev.record_count == 0


# =========================================================================
# 28. CPO evaluation creates zero accounting/payment/stock writes
# 29. CPO accrual creates zero: JournalEntry, JournalLine, PayableEntry,
#     Payment, LiquidityEntry, StockMovement
# =========================================================================
@pytest.mark.django_db
def test_28_29_zero_accounting_payment_stock_mutations(cpo_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("15"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )

    # 28. Candidate evaluation writes zero
    counts_before_eval = (
        JournalEntry.objects.count(),
        JournalLine.objects.count(),
        Payment.objects.count(),
        LiquidityEntry.objects.count(),
        StockMovement.objects.count(),
        IncentiveAccrual.objects.count(),
    )
    _ = get_cpo_candidate_for_receipt_line(line)
    counts_after_eval = (
        JournalEntry.objects.count(),
        JournalLine.objects.count(),
        Payment.objects.count(),
        LiquidityEntry.objects.count(),
        StockMovement.objects.count(),
        IncentiveAccrual.objects.count(),
    )
    assert counts_before_eval == counts_after_eval

    # 29. Accrual creates zero Finance or StockMovement records
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])
    assert accrual.state == IncentiveAccrualState.ACCRUED

    assert JournalEntry.objects.count() == 0
    assert JournalLine.objects.count() == 0
    assert Payment.objects.count() == 0
    assert LiquidityEntry.objects.count() == 0
    assert StockMovement.objects.count() == 0


# =========================================================================
# 30. Beneficiary cannot be changed after CPO accrual exists for the handover
# =========================================================================
@pytest.mark.django_db
def test_30_beneficiary_cannot_be_changed_after_cpo_accrual(cpo_fixture):
    handover = cpo_fixture["handover"]
    # Change state to DRAFT to simulate an edit attempt
    handover.state = ProductionHandoverState.DRAFT
    handover.save()

    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=handover,
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])

    other_emp = Employee.objects.create(
        legal_entity=cpo_fixture["entity"],
        employee_code="SPV-NEW",
        display_name="New Supervisor",
        is_active=True,
    )

    # Attempt to change beneficiary via update_handover_draft must be blocked
    with pytest.raises(ValidationError) as exc:
        update_handover_draft(
            handover,
            actor=cpo_fixture["user"],
            cpo_beneficiary=other_emp,
        )
    assert "Cannot change CPO beneficiary after CPO fee accruals have been created" in str(
        exc.value
    )

    # Model clean also blocks it
    handover.cpo_beneficiary = other_emp
    with pytest.raises(ValidationError) as exc:
        handover.full_clean()
    assert "Cannot change CPO beneficiary after CPO fee accruals have been created" in str(
        exc.value
    )


# =========================================================================
# 31. GET/read selectors create zero writes
# =========================================================================
@pytest.mark.django_db
def test_31_get_read_selectors_create_zero_writes(cpo_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )

    before_accruals = IncentiveAccrual.objects.count()
    _ = get_cpo_candidate_for_receipt_line(line)
    _ = get_cpo_candidates_for_receipt(receipt)
    _ = get_eligible_cpo_candidates(legal_entity=cpo_fixture["entity"])
    after_accruals = IncentiveAccrual.objects.count()

    assert before_accruals == after_accruals


# =========================================================================
# 32. Phase 9B1 generic incentive tests remain green (covered in test run)
# 33. legacy/smb_gas remains untouched
# =========================================================================
def test_33_legacy_smb_gas_remains_untouched():
    root = pathlib.Path("legacy/smb_gas")
    files = sorted([f for f in root.rglob("*") if f.is_file()])
    assert len(files) == 50

    lines = []
    for f in files:
        rel_path = f.relative_to(root).as_posix()
        content = f.read_bytes()
        file_bytes = len(content)
        file_sha256 = hashlib.sha256(content).hexdigest().upper()
        lines.append(f"{rel_path}|{file_bytes}|{file_sha256}")

    aggregate_input = "\n".join(lines).encode("utf-8")
    aggregate_hash = hashlib.sha256(aggregate_input).hexdigest().upper()
    assert aggregate_hash == "66F614E4A728F3A7EB8811A39C58EB6F88B16BB4C554DFF96114C569FB6031C2"


# =========================================================================
# 34. Source reversal creates/idempotently maps to IncentiveAccrualReversal
# 35. Duplicate source reversal does not duplicate incentive reversal
# =========================================================================
@pytest.mark.django_db
def test_34_35_source_reversal_maps_to_incentive_accrual_reversal(cpo_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=cpo_fixture["entity"],
        warehouse=cpo_fixture["wh"],
        work_order=cpo_fixture["work_order"],
        handover=cpo_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=cpo_fixture["ho_line_a"],
        output=cpo_fixture["output_a"],
        item=cpo_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("50"),
        uom_code_snapshot="PCS9B2",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=cpo_fixture["user"])
    assert accrual.state == IncentiveAccrualState.ACCRUED

    # Reverse Warehouse Receipt
    receipt.state = WarehouseDocumentState.REVERSED
    receipt.save()

    # Check candidate exposed for reversal
    cand = get_cpo_candidate_for_receipt_line(line)
    assert cand.status == "PENDING_REVERSAL"

    # 34. Reverse CPO fee
    rev_accrual = reverse_cpo_fee_for_receipt_line(
        line, actor=cpo_fixture["user"], reason="Warehouse receipt reversed"
    )
    assert rev_accrual.state == IncentiveAccrualState.REVERSED
    assert hasattr(rev_accrual, "reversal")
    assert rev_accrual.reversal.reason == "Warehouse receipt reversed"
    assert IncentiveAccrualReversal.objects.filter(accrual=accrual).count() == 1

    # Candidate after reversal shows ALREADY_REVERSED
    cand_after = get_cpo_candidate_for_receipt_line(line)
    assert cand_after.status == "ALREADY_REVERSED"

    # 35. Duplicate reversal is idempotent
    rev_accrual_2 = reverse_cpo_fee_for_receipt_line(
        line, actor=cpo_fixture["user"], reason="Warehouse receipt reversed"
    )
    assert rev_accrual_2.pk == rev_accrual.pk
    assert IncentiveAccrualReversal.objects.filter(accrual=accrual).count() == 1

    # Receipt-level batch reversal is also idempotent
    batch_rev = reverse_cpo_fees_for_receipt(
        receipt, actor=cpo_fixture["user"], reason="Warehouse receipt reversed"
    )
    assert len(batch_rev) == 1
    assert IncentiveAccrualReversal.objects.filter(accrual=accrual).count() == 1
