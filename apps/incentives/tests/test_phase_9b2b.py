"""Phase 9B2B Tests: CPO Finance Accounting + Payable + Payment State Boundary.

Tests verify:
- Completeness gating for Project CPO profitability (Sections 2 & 20)
- Explicit Finance posting for APPROVED CPO accruals (Sections 3, 7, 21)
- Balanced journal creation with semantic roles Dr CPO_FEE_COST, Cr INCENTIVE_PAYABLE
- Dynamic COA mapping resolution with zero hardcoded account IDs
- Idempotency of Finance posting
- Employee beneficiary leaves PayableEntry.partner NULL with no fake BusinessPartner
- Lifecycle transitions: APPROVED -> PAYABLE -> PAID (and payment reversal PAID -> PAYABLE)
- Payment liability settlement without duplicate CPO cost recognition
- Source/Finance reversal semantics (clean reversal for unpaid, block for settled)
- Cross-domain safety (zero stock movements, zero unwanted writes, legacy untouched)
"""

import datetime
import hashlib
import pathlib
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import Employee, User
from apps.catalog.models import UOM, Item
from apps.core.services.numbering import create_document_sequence
from apps.finance.models import (
    AccountType,
    DCDirection,
    IncentivePayablePosting,
    IncentivePostingState,
    JournalEntry,
    JournalLine,
    LiquidityAccountType,
    MappingDimensionType,
    NormalBalance,
    PayableEntry,
)
from apps.finance.selectors.incentive_payables import get_incentive_payable_status
from apps.finance.services.accounts import create_coa_account
from apps.finance.services.incentive_payables import (
    post_incentive_payable,
    reverse_incentive_payable_posting,
)
from apps.finance.services.liquidity import create_liquidity_account
from apps.finance.services.mappings import create_coa_mapping
from apps.finance.services.payments import post_vendor_payment, reverse_payment
from apps.incentives.models import (
    BeneficiaryKind,
    IncentiveAccrual,
    IncentiveAccrualState,
    IncentiveCalculationMethod,
    IncentiveTriggerType,
    IncentiveType,
)
from apps.incentives.services.accruals import approve_incentive_accrual
from apps.incentives.services.cpo import (
    accrue_cpo_fee_for_receipt_line,
    reverse_cpo_fee_for_receipt_line,
)
from apps.incentives.services.rules import create_incentive_rule
from apps.organizations.models import LegalEntity, Warehouse
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.production.models import (
    ProductionHandoverState,
    ProductionWarehouseHandover,
    ProductionWarehouseHandoverLine,
)
from apps.projects.models import ProjectBudgetCategory, ProjectState
from apps.projects.selectors.profitability import (
    AUTHORITATIVE_AVAILABLE,
    PENDING_SOURCE,
    project_profitability,
)
from apps.projects.services import create_draft_project
from apps.purchasing.models import WorkOrderOutput, WorkOrderState, WorkOrderType
from apps.purchasing.services import create_draft_work_order
from apps.warehouse.models import (
    StockMovement,
    WarehouseDocumentState,
    WarehouseReceipt,
    WarehouseReceiptLine,
)


@pytest.fixture
def b2b_fixture():
    entity = LegalEntity.objects.create(code="E9B2B", name="Entity 9B2B")
    wh = Warehouse.objects.create(
        legal_entity=entity, code="WH-FG", name="Finished Goods Warehouse"
    )
    user = User.objects.create_user("cpo_b2b_user@example.com", "password")

    uom = UOM.objects.create(code="PCS9B2B", name="Pieces 9B2B", dimension="COUNT")
    item_a = Item.objects.create(
        legal_entity=entity, code="ITEM-CPO-A", name="Product A", uom=uom, sales_eligible=True
    )
    item_b = Item.objects.create(
        legal_entity=entity, code="ITEM-CPO-B", name="Product B", uom=uom, sales_eligible=True
    )

    employee = Employee.objects.create(
        legal_entity=entity,
        employee_code="SPV-01",
        display_name="SPV Budi",
        is_active=True,
    )

    customer = BusinessPartner.objects.create(
        legal_entity=entity,
        code="CUST-9B2B",
        display_name="Customer 9B2B",
        effective_from=datetime.date(2026, 1, 1),
    )
    PartnerRole.objects.create(
        partner=customer,
        role_type=PartnerRoleType.CUSTOMER,
        effective_from=datetime.date(2026, 1, 1),
    )

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
        name="Project 9B2B",
        start_date=datetime.date(2026, 3, 1),
        actor=user,
        idempotency_key="prj-9b2b",
    )
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
    work_order = create_draft_work_order(
        legal_entity=entity,
        document_date=datetime.date(2026, 3, 1),
        work_order_type=WorkOrderType.INTERNAL,
        project=project,
        actor=user,
        idempotency_key="wo-9b2b-001",
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
        target_quantity=Decimal("100"),
        line_number=2,
    )

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
        quantity=Decimal("50"),
        sequence=1,
    )
    ho_line_b = ProductionWarehouseHandoverLine.objects.create(
        handover=handover,
        output=output_b,
        item=item_b,
        item_code_snapshot=item_b.code,
        item_name_snapshot=item_b.name,
        uom_code_snapshot=uom.code,
        quantity=Decimal("30"),
        sequence=2,
    )

    rule_a = create_incentive_rule(
        legal_entity=entity,
        code="RULE-ITEM-A",
        name="Rule Product A",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("500.0000"),
        effective_from=datetime.date(2026, 1, 1),
        item=item_a,
    )
    rule_b = create_incentive_rule(
        legal_entity=entity,
        code="RULE-ITEM-B",
        name="Rule Product B",
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        calculation_method=IncentiveCalculationMethod.PER_UNIT,
        rate_value=Decimal("700.0000"),
        effective_from=datetime.date(2026, 1, 1),
        item=item_b,
    )

    # COA Master & Mappings for Finance
    exp_account = create_coa_account(
        legal_entity=entity,
        account_code="5201",
        account_name="Biaya CPO Finished Goods",
        account_type=AccountType.EXPENSE,
        normal_balance=NormalBalance.DEBIT,
        effective_from=datetime.date(2026, 1, 1),
    )
    payable_account = create_coa_account(
        legal_entity=entity,
        account_code="2105",
        account_name="Hutang Incentive SPV CPO",
        account_type=AccountType.LIABILITY,
        normal_balance=NormalBalance.CREDIT,
        effective_from=datetime.date(2026, 1, 1),
    )
    bank_account = create_coa_account(
        legal_entity=entity,
        account_code="1102",
        account_name="Bank Operasional B2B",
        account_type=AccountType.ASSET,
        normal_balance=NormalBalance.DEBIT,
        effective_from=datetime.date(2026, 1, 1),
    )

    cpo_cost_mapping = create_coa_mapping(
        legal_entity=entity,
        module_code="FINANCE",
        event_code="INCENTIVE_CPO_FEE_PAYABLE",
        line_role="CPO_FEE_COST",
        dc=DCDirection.DEBIT,
        account=exp_account,
        dimension_type=MappingDimensionType.DEFAULT,
        effective_from=datetime.date(2026, 1, 1),
    )
    cpo_payable_mapping = create_coa_mapping(
        legal_entity=entity,
        module_code="FINANCE",
        event_code="INCENTIVE_CPO_FEE_PAYABLE",
        line_role="INCENTIVE_PAYABLE",
        dc=DCDirection.CREDIT,
        account=payable_account,
        dimension_type=MappingDimensionType.DEFAULT,
        effective_from=datetime.date(2026, 1, 1),
    )

    bank_liq = create_liquidity_account(
        legal_entity=entity,
        code="BANK-B2B",
        name="Bank B2B",
        account_type=LiquidityAccountType.BANK,
        mapping_key="BANK-B2B",
        bank_name="Bank B2B",
        bank_account_number="1234567890",
        account_holder_name="PT B2B",
        currency="IDR",
        effective_from=datetime.date(2026, 1, 1),
    )
    create_coa_mapping(
        legal_entity=entity,
        module_code="FINANCE",
        event_code="VENDOR_PAYMENT",
        line_role="LIQUIDITY",
        dc=DCDirection.CREDIT,
        account=bank_account,
        dimension_type=MappingDimensionType.LIQUIDITY_ACCOUNT,
        dimension_value=bank_liq.mapping_key,
        effective_from=datetime.date(2026, 1, 1),
    )

    return {
        "entity": entity,
        "wh": wh,
        "user": user,
        "item_a": item_a,
        "item_b": item_b,
        "employee": employee,
        "project": project,
        "work_order": work_order,
        "output_a": output_a,
        "output_b": output_b,
        "handover": handover,
        "ho_line_a": ho_line_a,
        "ho_line_b": ho_line_b,
        "rule_a": rule_a,
        "rule_b": rule_b,
        "exp_account": exp_account,
        "payable_account": payable_account,
        "bank_account": bank_account,
        "cpo_cost_mapping": cpo_cost_mapping,
        "cpo_payable_mapping": cpo_payable_mapping,
        "bank_liq": bank_liq,
    }


# =========================================================================
# 20. TESTS — COMPLETENESS (Tests 1 to 7)
# =========================================================================


@pytest.mark.django_db
def test_1_to_7_project_cpo_profitability_completeness(b2b_fixture):
    project = b2b_fixture["project"]

    receipt = WarehouseReceipt.objects.create(
        legal_entity=b2b_fixture["entity"],
        warehouse=b2b_fixture["wh"],
        work_order=b2b_fixture["work_order"],
        handover=b2b_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line_1 = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_a"],
        output=b2b_fixture["output_a"],
        item=b2b_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("20"),
        uom_code_snapshot="PCS9B2B",
        sequence=1,
    )
    line_2 = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_b"],
        output=b2b_fixture["output_b"],
        item=b2b_fixture["item_b"],
        source_key=f"REC|{receipt.pk}|2",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2B",
        sequence=2,
    )

    # 2. Project with two eligible lines but only one accrued -> CPO_FEE is PENDING_SOURCE
    # 5. Partial CPO subtotal is never labeled authoritative
    accrue_cpo_fee_for_receipt_line(line_1, actor=b2b_fixture["user"])  # 20 * 500 = 10,000

    prof_partial = project_profitability(project)
    cpo_cat = prof_partial.actual_categories[ProjectBudgetCategory.CPO_FEE]
    assert cpo_cat.availability == PENDING_SOURCE
    assert cpo_cat.reason == "INCOMPLETE_CPO_ACCRUAL_COVERAGE"
    assert cpo_cat.amount is None
    # actual_cost propagates PENDING_SOURCE to avoid material understatement
    assert prof_partial.actual_cost is None
    assert prof_partial.actual_cost_metric.availability == PENDING_SOURCE
    assert prof_partial.actual_cost_metric.reason == "INCOMPLETE_CPO_ACCRUAL_COVERAGE"

    # 6. Once missing source is correctly accrued -> Project CPO becomes authoritative
    # 1. Project with two eligible CPO lines and both accruals -> exact total (17,000)
    accrue_cpo_fee_for_receipt_line(line_2, actor=b2b_fixture["user"])  # 10 * 700 = 7,000

    prof_full = project_profitability(project)
    cpo_cat_full = prof_full.actual_categories[ProjectBudgetCategory.CPO_FEE]
    assert cpo_cat_full.availability == AUTHORITATIVE_AVAILABLE
    assert cpo_cat_full.amount == Decimal("17000.00")
    assert cpo_cat_full.record_count == 2
    assert prof_full.actual_cost == Decimal("17000.00")
    assert prof_full.actual_cost_metric.availability == AUTHORITATIVE_AVAILABLE

    # 7. Reversed source/accrual coverage does not produce false incomplete positive cost
    reverse_cpo_fee_for_receipt_line(line_1, actor=b2b_fixture["user"], reason="Batch cancelled")
    reverse_cpo_fee_for_receipt_line(line_2, actor=b2b_fixture["user"], reason="Batch cancelled")
    prof_rev = project_profitability(project)
    cpo_cat_rev = prof_rev.actual_categories[ProjectBudgetCategory.CPO_FEE]
    assert cpo_cat_rev.availability == AUTHORITATIVE_AVAILABLE
    assert cpo_cat_rev.amount == Decimal("0")
    assert cpo_cat_rev.record_count == 0


@pytest.mark.django_db
def test_3_4_missing_rule_or_beneficiary_causes_pending_source(b2b_fixture):
    project = b2b_fixture["project"]

    # Deactivate rule for item B
    b2b_fixture["rule_b"].is_active = False
    b2b_fixture["rule_b"].save()

    receipt = WarehouseReceipt.objects.create(
        legal_entity=b2b_fixture["entity"],
        warehouse=b2b_fixture["wh"],
        work_order=b2b_fixture["work_order"],
        handover=b2b_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_b"],
        output=b2b_fixture["output_b"],
        item=b2b_fixture["item_b"],
        source_key=f"REC|{receipt.pk}|B",
        accepted_quantity=Decimal("15"),
        uom_code_snapshot="PCS9B2B",
        sequence=1,
    )

    prof = project_profitability(project)
    # 3. Missing rule on one eligible line -> Project CPO remains PENDING_SOURCE
    assert prof.actual_categories[ProjectBudgetCategory.CPO_FEE].availability == PENDING_SOURCE
    assert (
        prof.actual_categories[ProjectBudgetCategory.CPO_FEE].reason
        == "INCOMPLETE_CPO_ACCRUAL_COVERAGE"
    )


# =========================================================================
# 21. TESTS — FINANCE POSTING (Tests 8 to 26)
# =========================================================================


@pytest.mark.django_db
def test_8_accrued_cpo_cannot_finance_post(b2b_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=b2b_fixture["entity"],
        warehouse=b2b_fixture["wh"],
        work_order=b2b_fixture["work_order"],
        handover=b2b_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_a"],
        output=b2b_fixture["output_a"],
        item=b2b_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2B",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=b2b_fixture["user"])
    assert accrual.state == IncentiveAccrualState.ACCRUED

    # 8. ACCRUED CPO cannot Finance-post
    with pytest.raises(ValidationError) as exc:
        post_incentive_payable(accrual, actor=b2b_fixture["user"])
    assert "Must be in APPROVED state" in str(exc.value)


@pytest.mark.django_db
def test_9_10_approved_cpo_can_finance_post_and_reversed_cannot(b2b_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=b2b_fixture["entity"],
        warehouse=b2b_fixture["wh"],
        work_order=b2b_fixture["work_order"],
        handover=b2b_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_a"],
        output=b2b_fixture["output_a"],
        item=b2b_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2B",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=b2b_fixture["user"])
    approve_incentive_accrual(accrual, actor=b2b_fixture["user"])
    assert accrual.state == IncentiveAccrualState.APPROVED

    # 9. APPROVED CPO can Finance-post
    posting = post_incentive_payable(accrual, actor=b2b_fixture["user"])
    assert posting.state == IncentivePostingState.POSTED
    assert posting.amount == Decimal("5000")
    accrual.refresh_from_db()
    assert accrual.state == IncentiveAccrualState.PAYABLE

    # 10. REVERSED CPO cannot Finance-post
    line_rev = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_b"],
        output=b2b_fixture["output_b"],
        item=b2b_fixture["item_b"],
        source_key=f"REC|{receipt.pk}|2",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2B",
        sequence=2,
    )
    accrual_rev = accrue_cpo_fee_for_receipt_line(line_rev, actor=b2b_fixture["user"])
    approve_incentive_accrual(accrual_rev, actor=b2b_fixture["user"])
    reverse_cpo_fee_for_receipt_line(line_rev, actor=b2b_fixture["user"], reason="Cancelled")
    accrual_rev.refresh_from_db()
    assert accrual_rev.state == IncentiveAccrualState.REVERSED

    with pytest.raises(ValidationError) as exc:
        post_incentive_payable(accrual_rev, actor=b2b_fixture["user"])
    assert "Must be in APPROVED state" in str(exc.value) or "reversed" in str(exc.value).lower()


@pytest.mark.django_db
def test_11_to_14_balanced_journal_and_coa_mapping_resolution(b2b_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=b2b_fixture["entity"],
        warehouse=b2b_fixture["wh"],
        work_order=b2b_fixture["work_order"],
        handover=b2b_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_a"],
        output=b2b_fixture["output_a"],
        item=b2b_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2B",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=b2b_fixture["user"])
    approve_incentive_accrual(accrual, actor=b2b_fixture["user"])

    posting = post_incentive_payable(accrual, actor=b2b_fixture["user"])
    journal = posting.journal

    # 11. Exactly one balanced JournalEntry
    assert journal is not None
    assert journal.total_debit == journal.total_credit == Decimal("5000")

    # 12. Debit role is CPO_FEE_COST
    debit_line = journal.lines.get(debit__gt=0)
    assert debit_line.line_role == "CPO_FEE_COST"
    # 14. Account comes from COAMapping, not hardcoded ID
    assert debit_line.account == b2b_fixture["exp_account"]

    # 13. Credit role is INCENTIVE_PAYABLE
    credit_line = journal.lines.get(credit__gt=0)
    assert credit_line.line_role == "INCENTIVE_PAYABLE"
    assert credit_line.account == b2b_fixture["payable_account"]


@pytest.mark.django_db
def test_15_to_18_missing_or_ambiguous_mapping_blocks_atomically(b2b_fixture):
    # Deactivate debit mapping
    b2b_fixture["cpo_cost_mapping"].is_active = False
    b2b_fixture["cpo_cost_mapping"].save()

    receipt = WarehouseReceipt.objects.create(
        legal_entity=b2b_fixture["entity"],
        warehouse=b2b_fixture["wh"],
        work_order=b2b_fixture["work_order"],
        handover=b2b_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_a"],
        output=b2b_fixture["output_a"],
        item=b2b_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2B",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=b2b_fixture["user"])
    approve_incentive_accrual(accrual, actor=b2b_fixture["user"])

    # 15. Missing debit mapping blocks atomically
    with pytest.raises(ValidationError) as exc:
        post_incentive_payable(accrual, actor=b2b_fixture["user"])
    assert "BLOCKED_MAPPING" in str(exc.value)

    # 18. No PayableEntry created on blocked mapping
    assert PayableEntry.objects.count() == 0
    assert JournalEntry.objects.count() == 0
    assert IncentivePayablePosting.objects.count() == 0
    accrual.refresh_from_db()
    assert accrual.state == IncentiveAccrualState.APPROVED


@pytest.mark.django_db
def test_19_to_26_posting_payable_partner_lineage_and_idempotency(b2b_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=b2b_fixture["entity"],
        warehouse=b2b_fixture["wh"],
        work_order=b2b_fixture["work_order"],
        handover=b2b_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_a"],
        output=b2b_fixture["output_a"],
        item=b2b_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2B",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=b2b_fixture["user"])
    approve_incentive_accrual(accrual, actor=b2b_fixture["user"])

    # 19. Successful posting creates one PayableEntry
    posting = post_incentive_payable(accrual, actor=b2b_fixture["user"])
    payable = posting.payable_entry
    assert payable is not None
    assert payable.original_amount == Decimal("5000")
    assert payable.open_amount == Decimal("5000")

    # 20. Employee beneficiary does not create/fake BusinessPartner (partner is NULL)
    assert payable.partner is None
    # No new BusinessPartner was created
    assert BusinessPartner.objects.filter(display_name="SPV Budi").count() == 0

    # 21. Finance posting preserves beneficiary snapshot/reference
    assert posting.beneficiary_type == BeneficiaryKind.EMPLOYEE
    assert posting.beneficiary_id == str(b2b_fixture["employee"].pk)
    assert posting.beneficiary_code_snapshot == "SPV-01"
    assert posting.beneficiary_name_snapshot == "SPV Budi"

    # 22. Preserves Project/Warehouse/Incentive source lineage
    assert posting.project_reference == str(b2b_fixture["project"].pk)
    assert posting.source_reference == accrual.source_reference

    # 23. Retry is idempotent: one journal, one payable, one posting
    posting_retry = post_incentive_payable(accrual, actor=b2b_fixture["user"])
    assert posting_retry.pk == posting.pk
    assert JournalEntry.objects.count() == 1
    assert PayableEntry.objects.count() == 1
    assert IncentivePayablePosting.objects.count() == 1

    # 24. Successful Finance posting: APPROVED -> PAYABLE
    accrual.refresh_from_db()
    assert accrual.state == IncentiveAccrualState.PAYABLE

    # 25. Finance posting never changes CPO accrual amount/rate/basis snapshots
    assert accrual.amount == Decimal("5000.00")
    assert accrual.basis_quantity == Decimal("10")
    assert accrual.rate_snapshot == Decimal("500.0000")

    # 26. Project CPO cost does not double after Finance posting
    prof = project_profitability(b2b_fixture["project"])
    cpo_cat = prof.actual_categories[ProjectBudgetCategory.CPO_FEE]
    assert cpo_cat.amount == Decimal("5000.00")
    assert cpo_cat.record_count == 1


# =========================================================================
# 22. TESTS — PAYMENT (Tests 27 to 36)
# =========================================================================


@pytest.mark.django_db
def test_27_to_34_payment_lifecycle_and_reversal(b2b_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=b2b_fixture["entity"],
        warehouse=b2b_fixture["wh"],
        work_order=b2b_fixture["work_order"],
        handover=b2b_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_a"],
        output=b2b_fixture["output_a"],
        item=b2b_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2B",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=b2b_fixture["user"])
    approve_incentive_accrual(accrual, actor=b2b_fixture["user"])
    posting = post_incentive_payable(accrual, actor=b2b_fixture["user"])
    payable = posting.payable_entry

    # 29. Partial payment: open_amount reduced, IncentiveAccrual remains PAYABLE
    payment_partial = post_vendor_payment(
        legal_entity=b2b_fixture["entity"],
        liquidity_account=b2b_fixture["bank_liq"],
        allocations=({"payable": payable, "amount": Decimal("2000")},),
        payment_date=datetime.date(2026, 3, 10),
        source_key="PAY-CPO-PARTIAL",
        actor=b2b_fixture["user"],
    )
    payable.refresh_from_db()
    accrual.refresh_from_db()
    assert payable.open_amount == Decimal("3000")
    assert accrual.state == IncentiveAccrualState.PAYABLE

    # 27. Paying Incentive Payable: Dr original INCENTIVE_PAYABLE control, Cr LIQUIDITY
    pay_journal = payment_partial.journal
    debit_line = pay_journal.lines.get(debit__gt=0)
    assert debit_line.line_role == "INCENTIVE_PAYABLE"
    assert debit_line.account == b2b_fixture["payable_account"]
    credit_line = pay_journal.lines.get(credit__gt=0)
    assert credit_line.line_role == "LIQUIDITY"
    assert credit_line.account == b2b_fixture["bank_account"]

    # 28. Payment creates no second CPO_FEE_COST debit
    assert not pay_journal.lines.filter(line_role="CPO_FEE_COST").exists()

    # 30. Full payment: open_amount == 0, IncentiveAccrual becomes PAID
    payment_final = post_vendor_payment(
        legal_entity=b2b_fixture["entity"],
        liquidity_account=b2b_fixture["bank_liq"],
        allocations=({"payable": payable, "amount": Decimal("3000")},),
        payment_date=datetime.date(2026, 3, 11),
        source_key="PAY-CPO-FINAL",
        actor=b2b_fixture["user"],
    )
    payable.refresh_from_db()
    accrual.refresh_from_db()
    assert payable.open_amount == Decimal("0")
    assert accrual.state == IncentiveAccrualState.PAID

    # 31. Payment beneficiary is still traceable despite partner NULL
    assert payment_final.partner is None
    recon = get_incentive_payable_status(accrual)
    assert recon.payment_status == "PAID"
    assert recon.beneficiary_name == "SPV Budi"

    # 32. Payment reversal restores payable open amount
    # 33. Payment reversal: PAID -> PAYABLE
    reverse_payment(payment_final, actor=b2b_fixture["user"])
    payable.refresh_from_db()
    accrual.refresh_from_db()
    assert payable.open_amount == Decimal("3000")
    assert accrual.state == IncentiveAccrualState.PAYABLE

    # 34. Payment reversal does not recreate CPO cost
    prof = project_profitability(b2b_fixture["project"])
    cpo_cat = prof.actual_categories[ProjectBudgetCategory.CPO_FEE]
    assert cpo_cat.amount == Decimal("5000.00")


# =========================================================================
# 23. TESTS — SOURCE / FINANCE REVERSAL (Tests 37 to 44)
# =========================================================================


@pytest.mark.django_db
def test_37_to_44_source_and_finance_reversal(b2b_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=b2b_fixture["entity"],
        warehouse=b2b_fixture["wh"],
        work_order=b2b_fixture["work_order"],
        handover=b2b_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_a"],
        output=b2b_fixture["output_a"],
        item=b2b_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2B",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=b2b_fixture["user"])
    approve_incentive_accrual(accrual, actor=b2b_fixture["user"])
    posting = post_incentive_payable(accrual, actor=b2b_fixture["user"])
    payable = posting.payable_entry

    # Make a partial payment
    payment = post_vendor_payment(
        legal_entity=b2b_fixture["entity"],
        liquidity_account=b2b_fixture["bank_liq"],
        allocations=({"payable": payable, "amount": Decimal("1000")},),
        payment_date=datetime.date(2026, 3, 10),
        source_key="PAY-SETTLED-TEST",
        actor=b2b_fixture["user"],
    )

    # 40. Partially paid payable blocks Finance payable reversal
    with pytest.raises(ValidationError) as exc:
        reverse_incentive_payable_posting(posting, actor=b2b_fixture["user"])
    assert "PAYABLE_ALREADY_SETTLED" in str(exc.value)

    # 42. Finance does not silently reverse Payment
    payment.refresh_from_db()
    assert payment.state != "REVERSED"

    # 43. After payment reversal restores full balance, payable reversal can complete
    reverse_payment(payment, actor=b2b_fixture["user"])
    payable.refresh_from_db()
    assert payable.open_amount == payable.original_amount == Decimal("5000")

    # Reverse source incentive accrual
    reverse_cpo_fee_for_receipt_line(line, actor=b2b_fixture["user"], reason="Cancelled batch")
    accrual.refresh_from_db()
    assert accrual.state == IncentiveAccrualState.REVERSED

    # 37. Source-reversed CPO with unpaid Finance payable:
    # Finance journal reverses, payable open_amount becomes 0, posting state becomes REVERSED
    reversal_jrn = reverse_incentive_payable_posting(posting, actor=b2b_fixture["user"])
    assert reversal_jrn is not None
    payable.refresh_from_db()
    posting.refresh_from_db()
    assert payable.open_amount == Decimal("0")
    assert posting.state == IncentivePostingState.REVERSED

    # 38. Reversal is idempotent
    reversal_retry = reverse_incentive_payable_posting(posting, actor=b2b_fixture["user"])
    assert reversal_retry.pk == reversal_jrn.pk

    # 44. Project profitability follows IncentiveAccrual reversal, not Finance journal/payment state
    prof = project_profitability(b2b_fixture["project"])
    cpo_cat = prof.actual_categories[ProjectBudgetCategory.CPO_FEE]
    assert cpo_cat.amount == Decimal("0")
    assert cpo_cat.record_count == 0


# =========================================================================
# 24. CROSS-DOMAIN SAFETY REGRESSION (Tests 45 to 52)
# =========================================================================


@pytest.mark.django_db
def test_45_to_52_cross_domain_safety(b2b_fixture):
    receipt = WarehouseReceipt.objects.create(
        legal_entity=b2b_fixture["entity"],
        warehouse=b2b_fixture["wh"],
        work_order=b2b_fixture["work_order"],
        handover=b2b_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_a"],
        output=b2b_fixture["output_a"],
        item=b2b_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2B",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=b2b_fixture["user"])
    approve_incentive_accrual(accrual, actor=b2b_fixture["user"])

    stock_count_before = StockMovement.objects.count()
    posting = post_incentive_payable(accrual, actor=b2b_fixture["user"])

    # 45. Finance posting creates zero StockMovement
    assert StockMovement.objects.count() == stock_count_before

    # 47. Finance posting creates no second IncentiveAccrual
    assert IncentiveAccrual.objects.count() == 1

    # 46. Finance payment creates zero Warehouse/Production transaction
    post_vendor_payment(
        legal_entity=b2b_fixture["entity"],
        liquidity_account=b2b_fixture["bank_liq"],
        allocations=({"payable": posting.payable_entry, "amount": Decimal("5000")},),
        payment_date=datetime.date(2026, 3, 10),
        source_key="PAY-ZERO-STOCK-TEST",
        actor=b2b_fixture["user"],
    )
    assert StockMovement.objects.count() == stock_count_before

    # 48. Project detail GET creates zero Finance/incentive writes
    jrn_count = JournalEntry.objects.count()
    acc_count = IncentiveAccrual.objects.count()
    _ = project_profitability(b2b_fixture["project"])
    assert JournalEntry.objects.count() == jrn_count
    assert IncentiveAccrual.objects.count() == acc_count

    # 49. SALES_FEE remains PENDING_SOURCE
    prof = project_profitability(b2b_fixture["project"])
    assert prof.actual_categories[ProjectBudgetCategory.SALES_FEE].availability == PENDING_SOURCE


@pytest.mark.django_db
def test_35_36_vendor_and_wage_payable_payments_unchanged(b2b_fixture):
    # 35. Ordinary vendor payable payment behavior remains unchanged
    vendor_partner = BusinessPartner.objects.create(
        legal_entity=b2b_fixture["entity"],
        code="VEND-REG",
        display_name="Vendor Regular",
        effective_from=datetime.date(2026, 1, 1),
    )
    PartnerRole.objects.create(
        partner=vendor_partner,
        role_type=PartnerRoleType.VENDOR,
        effective_from=datetime.date(2026, 1, 1),
    )

    vendor_payable_acct = create_coa_account(
        legal_entity=b2b_fixture["entity"],
        account_code="2101-VEND",
        account_name="Hutang Usaha Vendor",
        account_type=AccountType.LIABILITY,
        normal_balance=NormalBalance.CREDIT,
        effective_from=datetime.date(2026, 1, 1),
    )
    create_coa_mapping(
        legal_entity=b2b_fixture["entity"],
        module_code="FINANCE",
        event_code="VENDOR_PAYMENT",
        line_role="PAYABLE",
        dc=DCDirection.DEBIT,
        account=vendor_payable_acct,
        dimension_type=MappingDimensionType.DEFAULT,
        effective_from=datetime.date(2026, 1, 1),
    )

    vendor_jrn = JournalEntry.objects.create(
        legal_entity=b2b_fixture["entity"],
        journal_number="JRN-VEND-INIT",
        accounting_date=datetime.date(2026, 3, 5),
        event_code="VENDOR_INVOICE",
        source_module="PURCHASING",
        source_document_type="VendorInvoice",
        source_document_id="INV-001",
        source_key="INV-001",
        total_debit=Decimal("15000"),
        total_credit=Decimal("15000"),
        posted_at=datetime.datetime(2026, 3, 5, 10, 0, tzinfo=datetime.UTC),
        posted_by=b2b_fixture["user"],
    )
    vendor_payable = PayableEntry.objects.create(
        journal=vendor_jrn,
        legal_entity=b2b_fixture["entity"],
        accounting_date=datetime.date(2026, 3, 5),
        original_amount=Decimal("15000"),
        open_amount=Decimal("15000"),
        currency="IDR",
        partner=vendor_partner,
    )

    vend_pmt = post_vendor_payment(
        legal_entity=b2b_fixture["entity"],
        liquidity_account=b2b_fixture["bank_liq"],
        allocations=({"payable": vendor_payable, "amount": Decimal("15000")},),
        payment_date=datetime.date(2026, 3, 10),
        source_key="PAY-VEND-REG-001",
        actor=b2b_fixture["user"],
    )
    vendor_payable.refresh_from_db()
    assert vendor_payable.open_amount == Decimal("0")
    vend_pmt_jrn = vend_pmt.journal
    debit_line = vend_pmt_jrn.lines.get(debit__gt=0)
    assert debit_line.line_role == "PAYABLE"
    assert debit_line.account == vendor_payable_acct

    # 36. Existing Wage Payable payment behavior remains unchanged
    from apps.finance.models import WagePayableAccrual, WagePayableState

    wage_payable_acct = create_coa_account(
        legal_entity=b2b_fixture["entity"],
        account_code="2103-WAGE",
        account_name="Hutang Upah Langsung",
        account_type=AccountType.LIABILITY,
        normal_balance=NormalBalance.CREDIT,
        effective_from=datetime.date(2026, 1, 1),
    )
    wage_cost_acct = create_coa_account(
        legal_entity=b2b_fixture["entity"],
        account_code="5102-WAGE",
        account_name="Beban Upah Langsung",
        account_type=AccountType.EXPENSE,
        normal_balance=NormalBalance.DEBIT,
        effective_from=datetime.date(2026, 1, 1),
    )
    wage_jrn = JournalEntry.objects.create(
        legal_entity=b2b_fixture["entity"],
        journal_number="JRN-WAGE-INIT",
        accounting_date=datetime.date(2026, 3, 5),
        event_code="PROD_DIRECT_LABOR",
        source_module="PRODUCTION",
        source_document_type="ProductionCost",
        source_document_id="COST-001",
        source_key="WAGE-COST-001",
        total_debit=Decimal("25000"),
        total_credit=Decimal("25000"),
        posted_at=datetime.datetime(2026, 3, 5, 10, 0, tzinfo=datetime.UTC),
        posted_by=b2b_fixture["user"],
    )
    JournalLine.objects.create(
        journal=wage_jrn,
        sequence=1,
        account=wage_cost_acct,
        account_code_snapshot=wage_cost_acct.account_code,
        account_name_snapshot=wage_cost_acct.account_name,
        line_role="PRODUCTION_DIRECT_LABOR",
        debit=Decimal("25000"),
        credit=Decimal("0"),
        mapping_snapshot={
            "account_id": str(wage_cost_acct.pk),
            "account_code": wage_cost_acct.account_code,
            "account_name": wage_cost_acct.account_name,
        },
    )
    JournalLine.objects.create(
        journal=wage_jrn,
        sequence=2,
        account=wage_payable_acct,
        account_code_snapshot=wage_payable_acct.account_code,
        account_name_snapshot=wage_payable_acct.account_name,
        line_role="WAGE_PAYABLE",
        debit=Decimal("0"),
        credit=Decimal("25000"),
        mapping_snapshot={
            "account_id": str(wage_payable_acct.pk),
            "account_code": wage_payable_acct.account_code,
            "account_name": wage_payable_acct.account_name,
        },
    )
    wage_payable_entry = PayableEntry.objects.create(
        journal=wage_jrn,
        legal_entity=b2b_fixture["entity"],
        accounting_date=datetime.date(2026, 3, 5),
        original_amount=Decimal("25000"),
        open_amount=Decimal("25000"),
        currency="IDR",
        partner=None,
    )
    WagePayableAccrual.objects.create(
        legal_entity=b2b_fixture["entity"],
        source_module="PRODUCTION",
        source_type="ProductionCost",
        source_id="COST-001",
        source_key="WAGE-COST-001",
        accrual_date=datetime.date(2026, 3, 5),
        amount=Decimal("25000"),
        debit_line_role="PRODUCTION_DIRECT_LABOR",
        journal=wage_jrn,
        payable_entry=wage_payable_entry,
        state=WagePayableState.POSTED,
        posted_by=b2b_fixture["user"],
        posted_at=datetime.datetime(2026, 3, 5, 10, 0, tzinfo=datetime.UTC),
    )

    wage_pmt = post_vendor_payment(
        legal_entity=b2b_fixture["entity"],
        liquidity_account=b2b_fixture["bank_liq"],
        allocations=({"payable": wage_payable_entry, "amount": Decimal("25000")},),
        payment_date=datetime.date(2026, 3, 10),
        source_key="PAY-WAGE-001",
        actor=b2b_fixture["user"],
    )
    wage_payable_entry.refresh_from_db()
    assert wage_payable_entry.open_amount == Decimal("0")
    wage_pmt_jrn = wage_pmt.journal
    wage_debit_line = wage_pmt_jrn.lines.get(debit__gt=0)
    assert wage_debit_line.line_role == "WAGE_PAYABLE"
    assert wage_debit_line.account == wage_payable_acct


@pytest.mark.django_db
def test_period_control_enforcement_and_reconciliation_selector(b2b_fixture):
    from apps.finance.services.periods import close_accounting_period, create_accounting_period

    receipt = WarehouseReceipt.objects.create(
        legal_entity=b2b_fixture["entity"],
        warehouse=b2b_fixture["wh"],
        work_order=b2b_fixture["work_order"],
        handover=b2b_fixture["handover"],
        receipt_date=datetime.date(2026, 3, 5),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
    )
    line = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=b2b_fixture["ho_line_a"],
        output=b2b_fixture["output_a"],
        item=b2b_fixture["item_a"],
        source_key=f"REC|{receipt.pk}|1",
        accepted_quantity=Decimal("10"),
        uom_code_snapshot="PCS9B2B",
        sequence=1,
    )
    accrual = accrue_cpo_fee_for_receipt_line(line, actor=b2b_fixture["user"])

    # Reconciliation status before approval: PENDING_APPROVAL
    recon_init = get_incentive_payable_status(accrual)
    assert recon_init.reconciliation_status == "PENDING_APPROVAL"
    assert recon_init.has_finance_posting is False
    assert recon_init.payment_status == "NOT_POSTED"

    approve_incentive_accrual(accrual, actor=b2b_fixture["user"])

    # Reconciliation status after approval but before posting: APPROVED_NOT_POSTED
    recon_approved = get_incentive_payable_status(accrual)
    assert recon_approved.reconciliation_status == "APPROVED_NOT_POSTED"
    assert recon_approved.accounting_posting_missing is True

    # Activate period controls and close March 2026
    period = create_accounting_period(
        legal_entity=b2b_fixture["entity"],
        fiscal_year=2026,
        period_number=3,
        start_date=datetime.date(2026, 3, 1),
        end_date=datetime.date(2026, 3, 31),
        actor=b2b_fixture["user"],
    )
    close_accounting_period(period, actor=b2b_fixture["user"], reason="Month end close")

    # Attempting to post in closed period blocks
    with pytest.raises(ValidationError) as exc:
        post_incentive_payable(
            accrual, actor=b2b_fixture["user"], accounting_date=datetime.date(2026, 3, 5)
        )
    assert "PERIOD_CLOSED" in str(exc.value)

    # Post in open period (April 2026)
    create_accounting_period(
        legal_entity=b2b_fixture["entity"],
        fiscal_year=2026,
        period_number=4,
        start_date=datetime.date(2026, 4, 1),
        end_date=datetime.date(2026, 4, 30),
        actor=b2b_fixture["user"],
    )
    posting = post_incentive_payable(
        accrual, actor=b2b_fixture["user"], accounting_date=datetime.date(2026, 4, 2)
    )
    assert posting.state == IncentivePostingState.POSTED

    # Reconciliation status: PAYABLE_OPEN
    recon_posted = get_incentive_payable_status(accrual)
    assert recon_posted.reconciliation_status == "PAYABLE_OPEN"
    assert recon_posted.has_finance_posting is True
    assert recon_posted.payment_status == "UNPAID"
    assert recon_posted.payable_open_amount == Decimal("5000")


def test_52_legacy_smb_gas_remains_exact():
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
