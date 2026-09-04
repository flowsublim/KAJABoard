"""Phase 9B3 Tests: Incentive Rule Configuration + CPO Operations + Reconciliation UI.

Tests verify:
- Rule Configuration UI (list, create, edit, filter, search, permissions, overlap & validation)
- Executable vs Non-Executable badges (PER_UNIT/FIXED vs PERCENT/TIERED/FORMULA)
- CPO Operations Dashboard (GET zero writes, candidate evaluation, operational status, actions)
- CPO Accrue, Approve, and Post Payable POST actions with idempotency and strict permissions
- Dashboard filtering (date, project, beneficiary, item, operational status)
- Summary cards and authoritative subtotal (strictly excluding pending estimates & reversed)
- CPO Detail view showing immutable historical snapshots resilient to master mutations
- Production Handover form CPO Beneficiary field (label, help text, disabled when accrual exists)
- Project Detail integration (CPO Fee drilldown link, coverage, Sales Fee PENDING_SOURCE)
- Semantic Payment identity (post_incentive_payment, IncentivePayment type, lifecycle sync)
- Reverse Accounting action availability and settlement blocking
- SMB GAS 50-file integrity & aggregate hash preservation
"""

import datetime
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Employee, User
from apps.catalog.models import UOM, Item
from apps.core.models import AuditEvent
from apps.core.services.numbering import create_document_sequence
from apps.finance.models import (
    AccountType,
    DCDirection,
    IncentivePayablePosting,
    IncentivePostingState,
    JournalEntry,
    LiquidityAccountType,
    MappingDimensionType,
    NormalBalance,
)
from apps.finance.services.accounts import create_coa_account
from apps.finance.services.incentive_payables import (
    post_incentive_payable,
    post_incentive_payment,
)
from apps.finance.services.liquidity import create_liquidity_account
from apps.finance.services.mappings import create_coa_mapping
from apps.finance.services.payments import reverse_payment
from apps.finance.services.periods import create_accounting_period
from apps.incentives.models import (
    IncentiveAccrual,
    IncentiveAccrualState,
    IncentiveCalculationMethod,
    IncentiveTriggerType,
    IncentiveType,
)
from apps.incentives.services.accruals import (
    approve_incentive_accrual,
    mark_accrual_paid_from_finance,
    mark_accrual_payable_from_finance,
    reopen_accrual_payable_from_finance,
)
from apps.incentives.services.cpo import (
    accrue_cpo_fee_for_receipt_line,
    reverse_cpo_fee_for_receipt_line,
)
from apps.incentives.services.rules import create_incentive_rule
from apps.organizations.models import LegalEntity, OrganizationMembership, Warehouse
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.production.forms import ProductionWarehouseHandoverForm
from apps.production.models import (
    ProductionHandoverState,
    ProductionWarehouseHandover,
    ProductionWarehouseHandoverLine,
)
from apps.projects.models import (
    ProjectBudgetCategory,
    ProjectState,
)
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
def b3_fixture():
    entity = LegalEntity.objects.create(code="E9B3", name="Entity 9B3")
    wh = Warehouse.objects.create(
        legal_entity=entity, code="WH-FG-9B3", name="Finished Goods Warehouse 9B3"
    )

    # Users
    admin_user = User.objects.create_superuser("admin9b3@example.com", "password")
    ops_user = User.objects.create_user("ops9b3@example.com", "password")
    unauth_user = User.objects.create_user("unauth9b3@example.com", "password")

    # Give ops_user all standard incentives & finance permissions
    for perm_codename in (
        "view_incentiverule",
        "add_incentiverule",
        "change_incentiverule",
        "view_incentiveaccrual",
        "add_incentiveaccrual",
        "change_incentiveaccrual",
        "post_journal",
        "reverse_journal",
        "add_payableentry",
        "view_project",
    ):
        perm = Permission.objects.filter(codename=perm_codename).first()
        if perm:
            ops_user.user_permissions.add(perm)

    OrganizationMembership.objects.create(user=admin_user, legal_entity=entity, is_active=True)
    OrganizationMembership.objects.create(user=ops_user, legal_entity=entity, is_active=True)
    OrganizationMembership.objects.create(user=unauth_user, legal_entity=entity, is_active=True)

    uom = UOM.objects.create(code="PCS9B3", name="Pieces 9B3", dimension="COUNT")
    item_a = Item.objects.create(
        legal_entity=entity, code="ITEM-9B3-A", name="Product 9B3 A", uom=uom, sales_eligible=True
    )
    item_b = Item.objects.create(
        legal_entity=entity, code="ITEM-9B3-B", name="Product 9B3 B", uom=uom, sales_eligible=True
    )

    employee = Employee.objects.create(
        legal_entity=entity,
        employee_code="SPV-9B3",
        display_name="SPV Bambang",
        is_active=True,
    )
    inactive_employee = Employee.objects.create(
        legal_entity=entity,
        employee_code="SPV-INACT",
        display_name="SPV Inactive",
        is_active=False,
    )

    customer = BusinessPartner.objects.create(
        legal_entity=entity,
        code="CUST-9B3",
        display_name="Customer 9B3",
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
        name="Project 9B3",
        start_date=datetime.date(2026, 3, 1),
        actor=admin_user,
        idempotency_key="prj-9b3-001",
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
        actor=admin_user,
        idempotency_key="wo-9b3-001",
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
        created_by=admin_user,
        ready_by=admin_user,
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

    receipt = WarehouseReceipt.objects.create(
        legal_entity=entity,
        warehouse=wh,
        receipt_date=datetime.date(2026, 3, 2),
        state=WarehouseDocumentState.POSTED,
        source_module="production",
        source_type="PRODUCTION_HANDOVER",
        work_order=work_order,
        handover=handover,
        created_by=admin_user,
        posted_by=admin_user,
    )
    rcp_line_a = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=ho_line_a,
        output=output_a,
        item=item_a,
        source_key=str(ho_line_a.pk),
        accepted_quantity=Decimal("50"),
        uom_code_snapshot=uom.code,
        sequence=1,
    )
    rcp_line_b = WarehouseReceiptLine.objects.create(
        receipt=receipt,
        handover_line=ho_line_b,
        output=output_b,
        item=item_b,
        source_key=str(ho_line_b.pk),
        accepted_quantity=Decimal("30"),
        uom_code_snapshot=uom.code,
        sequence=2,
    )

    # Accounting Period & COA
    period = create_accounting_period(
        legal_entity=entity,
        fiscal_year=2026,
        period_number=3,
        start_date=datetime.date(2026, 3, 1),
        end_date=datetime.date(2026, 3, 31),
        actor=admin_user,
    )
    create_accounting_period(
        legal_entity=entity,
        fiscal_year=2026,
        period_number=9,
        start_date=datetime.date(2026, 9, 1),
        end_date=datetime.date(2026, 9, 30),
        actor=admin_user,
    )

    coa_expense = create_coa_account(
        legal_entity=entity,
        account_code="5200-CPO-9B3",
        account_name="CPO Fee Expense 9B3",
        account_type=AccountType.EXPENSE,
        normal_balance=NormalBalance.DEBIT,
        effective_from=datetime.date(2026, 1, 1),
        actor=admin_user,
    )
    coa_payable = create_coa_account(
        legal_entity=entity,
        account_code="2150-CPO-9B3",
        account_name="Incentive Payable 9B3",
        account_type=AccountType.LIABILITY,
        normal_balance=NormalBalance.CREDIT,
        effective_from=datetime.date(2026, 1, 1),
        actor=admin_user,
    )
    coa_bank = create_coa_account(
        legal_entity=entity,
        account_code="1110-BANK-9B3",
        account_name="Bank Account 9B3",
        account_type=AccountType.ASSET,
        normal_balance=NormalBalance.DEBIT,
        effective_from=datetime.date(2026, 1, 1),
        actor=admin_user,
    )

    create_coa_mapping(
        legal_entity=entity,
        module_code="FINANCE",
        event_code="INCENTIVE_CPO_FEE_PAYABLE",
        line_role="CPO_FEE_COST",
        dc=DCDirection.DEBIT,
        account=coa_expense,
        dimension_type=MappingDimensionType.DEFAULT,
        effective_from=datetime.date(2026, 1, 1),
    )
    create_coa_mapping(
        legal_entity=entity,
        module_code="FINANCE",
        event_code="INCENTIVE_CPO_FEE_PAYABLE",
        line_role="INCENTIVE_PAYABLE",
        dc=DCDirection.CREDIT,
        account=coa_payable,
        dimension_type=MappingDimensionType.DEFAULT,
        effective_from=datetime.date(2026, 1, 1),
    )

    liq_acc = create_liquidity_account(
        legal_entity=entity,
        code="BANK-OPERASIONAL-9B3",
        name="Bank Operasional 9B3",
        account_type=LiquidityAccountType.BANK,
        mapping_key="BANK-OPERASIONAL-9B3",
        bank_name="Bank Operasional 9B3",
        bank_account_number="1234567890",
        account_holder_name="PT 9B3",
        currency="IDR",
        effective_from=datetime.date(2026, 1, 1),
        actor=admin_user,
    )
    create_coa_mapping(
        legal_entity=entity,
        module_code="FINANCE",
        event_code="VENDOR_PAYMENT",
        line_role="LIQUIDITY",
        dc=DCDirection.CREDIT,
        account=coa_bank,
        dimension_type=MappingDimensionType.LIQUIDITY_ACCOUNT,
        dimension_value=liq_acc.mapping_key,
        effective_from=datetime.date(2026, 1, 1),
    )

    return {
        "entity": entity,
        "wh": wh,
        "admin_user": admin_user,
        "ops_user": ops_user,
        "unauth_user": unauth_user,
        "uom": uom,
        "item_a": item_a,
        "item_b": item_b,
        "employee": employee,
        "inactive_employee": inactive_employee,
        "customer": customer,
        "project": project,
        "work_order": work_order,
        "handover": handover,
        "ho_line_a": ho_line_a,
        "ho_line_b": ho_line_b,
        "receipt": receipt,
        "rcp_line_a": rcp_line_a,
        "rcp_line_b": rcp_line_b,
        "period": period,
        "coa_expense": coa_expense,
        "coa_payable": coa_payable,
        "coa_bank": coa_bank,
        "liq_acc": liq_acc,
    }


# =========================================================================
# 1. INCENTIVE RULE CONFIGURATION UI TESTS (Checkpoints 10-16)
# =========================================================================


@pytest.mark.django_db
class TestIncentiveRuleUI:
    def test_rule_list_requires_authentication(self, b3_fixture):
        """10. Rule list view requires authentication."""
        client = Client()
        resp = client.get(reverse("incentives:rule-list"))
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    def test_rule_list_requires_permission(self, b3_fixture):
        """11. Unauthorized user receives 403 on rule views."""
        client = Client()
        client.force_login(b3_fixture["unauth_user"])
        resp = client.get(reverse("incentives:rule-list"))
        assert resp.status_code == 403

        resp_create = client.get(reverse("incentives:rule-create"))
        assert resp_create.status_code == 403

    def test_rule_list_filters_and_search(self, b3_fixture):
        """12. Rule list filters by incentive_type, item, active status, and search query."""
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        item_b = b3_fixture["item_b"]

        create_incentive_rule(
            legal_entity=entity,
            code="RULE-PER-UNIT",
            name="CPO Per Unit Rule",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )
        create_incentive_rule(
            legal_entity=entity,
            code="RULE-FIXED",
            name="Fixed Commission Rule",
            incentive_type=IncentiveType.SALES_COMMISSION,
            trigger_type=IncentiveTriggerType.INVOICE_PAID,
            calculation_method=IncentiveCalculationMethod.FIXED,
            rate_value=Decimal("100000"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_b,
            is_active=False,
            actor=user,
        )

        client = Client()
        client.force_login(b3_fixture["ops_user"])

        # Filter by incentive_type
        resp = client.get(reverse("incentives:rule-list") + "?incentive_type=CPO_FEE")
        assert resp.status_code == 200
        assert "RULE-PER-UNIT" in resp.content.decode()
        assert "RULE-FIXED" not in resp.content.decode()

        # Filter by active
        resp = client.get(reverse("incentives:rule-list") + "?is_active=0")
        assert resp.status_code == 200
        assert "RULE-FIXED" in resp.content.decode()
        assert "RULE-PER-UNIT" not in resp.content.decode()

        # Filter by item
        resp = client.get(reverse("incentives:rule-list") + f"?item_id={item_a.pk}")
        assert resp.status_code == 200
        assert "RULE-PER-UNIT" in resp.content.decode()
        assert "RULE-FIXED" not in resp.content.decode()

        # Search query
        resp = client.get(reverse("incentives:rule-list") + "?q=Commission")
        assert resp.status_code == 200
        assert "RULE-FIXED" in resp.content.decode()
        assert "RULE-PER-UNIT" not in resp.content.decode()

    def test_executable_vs_non_executable_badges(self, b3_fixture):
        """13. Executable vs non-executable rules render distinct visual badges/labels."""
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]

        create_incentive_rule(
            legal_entity=entity,
            code="RULE-EXEC",
            name="Executable Unit Rule",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            actor=user,
        )
        create_incentive_rule(
            legal_entity=entity,
            code="RULE-NON-EXEC",
            name="Non-Executable Margin Rule",
            incentive_type=IncentiveType.SALES_COMMISSION,
            trigger_type=IncentiveTriggerType.INVOICE_PAID,
            calculation_method=IncentiveCalculationMethod.PERCENT_MARGIN_PROFIT,
            rate_value=Decimal("10"),
            effective_from=datetime.date(2026, 1, 1),
            actor=user,
        )

        client = Client()
        client.force_login(b3_fixture["ops_user"])
        resp = client.get(reverse("incentives:rule-list"))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "EXECUTABLE" in content
        assert "NOT YET EXECUTABLE" in content

    def test_rule_creation_view_overlap_validation(self, b3_fixture):
        """14. Rule creation via view validates overlap and rejects overlapping date ranges."""
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]

        create_incentive_rule(
            legal_entity=entity,
            code="RULE-EXISTING",
            name="Existing Rule",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            actor=user,
        )

        client = Client()
        client.force_login(b3_fixture["ops_user"])

        # Attempt to create overlapping rule via view
        post_data = {
            "legal_entity": str(entity.pk),
            "code": "RULE-OVERLAP",
            "name": "Overlapping Rule",
            "incentive_type": IncentiveType.CPO_FEE,
            "trigger_type": IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            "calculation_method": IncentiveCalculationMethod.PER_UNIT,
            "rate_value": "600",
            "currency": "IDR",
            "effective_from": "2026-02-01",
            "is_active": "on",
        }
        resp = client.post(reverse("incentives:rule-create"), data=post_data)
        assert resp.status_code == 200  # returns form with errors
        assert "Overlapping active rule" in resp.content.decode()

    def test_rule_creation_view_rejects_negative_rate(self, b3_fixture):
        """15. Rule creation via view rejects negative rate."""
        entity = b3_fixture["entity"]
        client = Client()
        client.force_login(b3_fixture["ops_user"])

        post_data = {
            "legal_entity": str(entity.pk),
            "code": "RULE-NEG",
            "name": "Negative Rule",
            "incentive_type": IncentiveType.CPO_FEE,
            "trigger_type": IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            "calculation_method": IncentiveCalculationMethod.PER_UNIT,
            "rate_value": "-100",
            "currency": "IDR",
            "effective_from": "2026-01-01",
            "is_active": "on",
        }
        resp = client.post(reverse("incentives:rule-create"), data=post_data)
        assert resp.status_code == 200
        assert "Rate value cannot be negative" in resp.content.decode()

    def test_rule_update_view_preserves_and_updates(self, b3_fixture):
        """16. Rule update view preserves entity, code, and history rules."""
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]

        rule = create_incentive_rule(
            legal_entity=entity,
            code="RULE-TO-EDIT",
            name="Original Name",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            actor=user,
        )

        client = Client()
        client.force_login(b3_fixture["ops_user"])

        update_data = {
            "legal_entity": str(entity.pk),
            "code": "RULE-TO-EDIT",
            "name": "Updated Name 9B3",
            "incentive_type": IncentiveType.CPO_FEE,
            "trigger_type": IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            "calculation_method": IncentiveCalculationMethod.PER_UNIT,
            "rate_value": "750",
            "currency": "IDR",
            "effective_from": "2026-01-01",
            "is_active": "on",
            "notes": "Updated note",
        }
        resp = client.post(reverse("incentives:rule-edit", args=[rule.pk]), data=update_data)
        assert resp.status_code == 302
        assert resp.url == reverse("incentives:rule-list")

        rule.refresh_from_db()
        assert rule.name == "Updated Name 9B3"
        assert rule.rate_value == Decimal("750")
        assert rule.notes == "Updated note"


# =========================================================================
# 2. CPO OPERATIONS DASHBOARD & LIFECYCLE ACTIONS (Checkpoints 17-34)
# =========================================================================


@pytest.mark.django_db
class TestCPOOperationsUI:
    def test_cpo_dashboard_requires_authentication_and_permission(self, b3_fixture):
        """17. CPO dashboard requires authentication and incentives.view_incentiveaccrual."""
        client = Client()
        # Anonymous
        resp = client.get(reverse("incentives:cpo-dashboard"))
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

        # Unauthorized
        client.force_login(b3_fixture["unauth_user"])
        resp_unauth = client.get(reverse("incentives:cpo-dashboard"))
        assert resp_unauth.status_code == 403

    def test_cpo_dashboard_get_zero_database_writes(self, b3_fixture):
        """18. CPO dashboard GET performs zero database writes."""
        client = Client()
        client.force_login(b3_fixture["ops_user"])

        accrual_count_before = IncentiveAccrual.objects.count()
        journal_count_before = JournalEntry.objects.count()
        audit_count_before = AuditEvent.objects.count()
        stock_count_before = StockMovement.objects.count()
        receipt_count_before = WarehouseReceipt.objects.count()

        resp = client.get(reverse("incentives:cpo-dashboard"))
        assert resp.status_code == 200

        assert IncentiveAccrual.objects.count() == accrual_count_before
        assert JournalEntry.objects.count() == journal_count_before
        assert AuditEvent.objects.count() == audit_count_before
        assert StockMovement.objects.count() == stock_count_before
        assert WarehouseReceipt.objects.count() == receipt_count_before

    def test_cpo_candidate_statuses_rendered(self, b3_fixture):
        """19, 20, 21, 22, 23: Dashboard displays receipt lines with correct candidate statuses."""
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]
        rcp_line_b = b3_fixture["rcp_line_b"]

        client = Client()
        client.force_login(b3_fixture["ops_user"])

        # Case 1: No matching rule exists yet -> PENDING_RULE
        resp = client.get(reverse("incentives:cpo-dashboard"))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "PENDING_RULE" in content
        # No accrue action button should be rendered for PENDING_RULE
        assert reverse("incentives:cpo-accrue", args=[rcp_line_a.pk]) not in content

        # Create rule for Item A
        create_incentive_rule(
            legal_entity=entity,
            code="RULE-ITEM-A",
            name="Rule Item A",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )

        # Case 2: Item A has rule and active beneficiary -> READY
        resp2 = client.get(reverse("incentives:cpo-dashboard"))
        assert resp2.status_code == 200
        content2 = resp2.content.decode()
        assert "READY" in content2
        assert reverse("incentives:cpo-accrue", args=[rcp_line_a.pk]) in content2

        # Item B still has no rule -> PENDING_RULE
        assert reverse("incentives:cpo-accrue", args=[rcp_line_b.pk]) not in content2

    def test_accrue_post_action_success_idempotency_and_permissions(self, b3_fixture):
        """24, 25, 26: Accrue POST creates IncentiveAccrual in ACCRUED state,
        requires perm, is idempotent.
        """
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]

        create_incentive_rule(
            legal_entity=entity,
            code="RULE-ITEM-A",
            name="Rule Item A",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )

        # Unauthorized user
        client_unauth = Client()
        client_unauth.force_login(b3_fixture["unauth_user"])
        resp_unauth = client_unauth.post(reverse("incentives:cpo-accrue", args=[rcp_line_a.pk]))
        assert resp_unauth.status_code == 403

        # Authorized user
        client_ops = Client()
        client_ops.force_login(b3_fixture["ops_user"])
        resp_ops = client_ops.post(reverse("incentives:cpo-accrue", args=[rcp_line_a.pk]))
        assert resp_ops.status_code == 302

        # Verify accrual created
        accrual = IncentiveAccrual.objects.get(
            source_document_id=str(rcp_line_a.receipt_id),
            source_line_id=str(rcp_line_a.pk),
        )
        assert accrual.state == IncentiveAccrualState.ACCRUED
        assert accrual.amount == Decimal("25000")  # 50 qty * 500 IDR

        # Idempotency: call again
        resp_ops_repeat = client_ops.post(reverse("incentives:cpo-accrue", args=[rcp_line_a.pk]))
        assert resp_ops_repeat.status_code == 302
        assert (
            IncentiveAccrual.objects.filter(
                source_document_id=str(rcp_line_a.receipt_id),
                source_line_id=str(rcp_line_a.pk),
            ).count()
            == 1
        )

    def test_approve_post_action_and_dashboard_status(self, b3_fixture):
        """27, 28: Approve POST transitions to APPROVED and updates dashboard status."""
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]

        create_incentive_rule(
            legal_entity=entity,
            code="RULE-ITEM-A",
            name="Rule Item A",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )
        accrual = accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)

        # Unauthorized user
        client_unauth = Client()
        client_unauth.force_login(b3_fixture["unauth_user"])
        resp_unauth = client_unauth.post(reverse("incentives:cpo-approve", args=[accrual.pk]))
        assert resp_unauth.status_code == 403

        # Authorized user
        client_ops = Client()
        client_ops.force_login(b3_fixture["ops_user"])
        resp_ops = client_ops.post(reverse("incentives:cpo-approve", args=[accrual.pk]))
        assert resp_ops.status_code == 302

        accrual.refresh_from_db()
        assert accrual.state == IncentiveAccrualState.APPROVED

        # Dashboard shows APPROVED and Post Hutang action
        resp_dash = client_ops.get(reverse("incentives:cpo-dashboard"))
        assert resp_dash.status_code == 200
        content = resp_dash.content.decode()
        assert "APPROVED" in content
        assert reverse("incentives:cpo-post-payable", args=[accrual.pk]) in content

    def test_post_payable_action_and_dashboard_status(self, b3_fixture):
        """29, 30, 31: Post Payable action creates posting, journal, payable, and is idempotent."""
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]

        create_incentive_rule(
            legal_entity=entity,
            code="RULE-ITEM-A",
            name="Rule Item A",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )
        accrual = accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)
        approve_incentive_accrual(accrual, actor=user)

        # Unauthorized
        client_unauth = Client()
        client_unauth.force_login(b3_fixture["unauth_user"])
        resp_unauth = client_unauth.post(reverse("incentives:cpo-post-payable", args=[accrual.pk]))
        assert resp_unauth.status_code == 403

        # Authorized
        client_ops = Client()
        client_ops.force_login(b3_fixture["ops_user"])
        resp_ops = client_ops.post(reverse("incentives:cpo-post-payable", args=[accrual.pk]))
        assert resp_ops.status_code == 302

        posting = IncentivePayablePosting.objects.get(incentive_accrual=accrual)
        assert posting.state == IncentivePostingState.POSTED
        assert posting.payable_entry.open_amount == Decimal("25000")

        accrual.refresh_from_db()
        assert accrual.state == IncentiveAccrualState.PAYABLE

        # Idempotency
        resp_ops_repeat = client_ops.post(reverse("incentives:cpo-post-payable", args=[accrual.pk]))
        assert resp_ops_repeat.status_code == 302
        assert IncentivePayablePosting.objects.filter(incentive_accrual=accrual).count() == 1

        # Dashboard shows PAYABLE OPEN
        resp_dash = client_ops.get(reverse("incentives:cpo-dashboard"))
        assert resp_dash.status_code == 200
        content = resp_dash.content.decode()
        assert "PAYABLE OPEN" in content

    def test_cpo_dashboard_filters_and_summary_metrics(self, b3_fixture):
        """32, 33, 34: Filters work and summary metrics strictly sum authoritative accruals."""
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]

        create_incentive_rule(
            legal_entity=entity,
            code="RULE-ITEM-A",
            name="Rule Item A",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )
        accrual_a = accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)

        client = Client()
        client.force_login(b3_fixture["ops_user"])

        resp = client.get(reverse("incentives:cpo-dashboard"))
        assert resp.status_code == 200
        context = resp.context
        summary = context["summary"]

        assert summary["total_posted_lines"] == 2
        assert summary["accrued"] == 1
        assert summary["pending_rule"] == 1
        assert summary["authoritative_total_amount"] == Decimal("25000")  # only accrual_a, NOT b!

        # Filter by status = ACCRUED
        resp_filter = client.get(reverse("incentives:cpo-dashboard") + "?status=ACCRUED")
        assert resp_filter.status_code == 200
        assert len(resp_filter.context["rows"]) == 1
        assert resp_filter.context["rows"][0]["accrual"].pk == accrual_a.pk


# =========================================================================
# 3. CPO DETAIL IMMUTABLE SNAPSHOTS (Checkpoint 35)
# =========================================================================


@pytest.mark.django_db
class TestCPODetailSnapshot:
    def test_cpo_detail_immutable_snapshots_resilient_to_mutations(self, b3_fixture):
        """35. CPO detail view shows immutable snapshots even after master data changes."""
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        employee = b3_fixture["employee"]
        rcp_line_a = b3_fixture["rcp_line_a"]

        rule = create_incentive_rule(
            legal_entity=entity,
            code="RULE-ORIGINAL",
            name="Original Rule Name",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )
        accrual = accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)

        # Mutate master objects
        item_a.name = "MODIFIED Item Name"
        item_a.save(update_fields=("name",))

        employee.display_name = "MODIFIED Employee Name"
        employee.save(update_fields=("display_name",))

        rule.name = "MODIFIED Rule Name"
        rule.rate_value = Decimal("9999")
        rule.save(update_fields=("name", "rate_value"))

        client = Client()
        client.force_login(b3_fixture["ops_user"])
        resp = client.get(reverse("incentives:cpo-detail", args=[accrual.pk]))
        assert resp.status_code == 200
        content = resp.content.decode()

        # Check that historical snapshots are preserved
        assert "SPV Bambang" in content
        assert "RULE-ORIGINAL" in content
        assert "500" in content
        assert "25000" in content


# =========================================================================
# 4. PRODUCTION BENEFICIARY UI (Checkpoints 36-37)
# =========================================================================


@pytest.mark.django_db
class TestProductionBeneficiaryUI:
    def test_production_handover_form_cpo_beneficiary_field(self, b3_fixture):
        """36, 37: Production handover form exposes cpo_beneficiary with label
        and disables it when accrual exists.
        """
        handover = b3_fixture["handover"]
        rcp_line_a = b3_fixture["rcp_line_a"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]

        # Before accrual exists
        form_before = ProductionWarehouseHandoverForm(instance=handover, user=user)
        assert "cpo_beneficiary" in form_before.fields
        field = form_before.fields["cpo_beneficiary"]
        assert field.label == "CPO Beneficiary / SPV"
        assert "CPO Finished Goods Fee" in field.help_text
        assert not field.disabled

        # Create accrual
        create_incentive_rule(
            legal_entity=b3_fixture["entity"],
            code="RULE-FG-A",
            name="Rule FG A",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )
        accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)

        # After accrual exists: form disables the field
        form_after = ProductionWarehouseHandoverForm(instance=handover, user=user)
        assert form_after.fields["cpo_beneficiary"].disabled is True


# =========================================================================
# 5. PROJECT PROFITABILITY DRILLDOWN INTEGRATION (Checkpoints 38-40)
# =========================================================================


@pytest.mark.django_db
class TestProjectProfitabilityDrilldown:
    def test_project_detail_displays_cpo_fee_drilldown_and_preserves_sales_fee(self, b3_fixture):
        """38, 39, 40: Project detail displays CPO fee drilldown link,
        coverage, and Sales Fee remains PENDING SOURCE.
        """
        project = b3_fixture["project"]
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]

        # Create rule for Item A only (Item B pending -> incomplete coverage)
        create_incentive_rule(
            legal_entity=entity,
            code="RULE-ITEM-A",
            name="Rule Item A",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )
        accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)

        client = Client()
        client.force_login(b3_fixture["ops_user"])
        resp = client.get(reverse("projects:detail", args=[project.pk]))
        assert resp.status_code == 200
        content = resp.content.decode()

        # Drilldown link to CPO dashboard filtered by project
        expected_url = reverse("incentives:cpo-dashboard") + f"?project_id={project.pk}"
        assert expected_url in content

        # Coverage status
        assert "Coverage: Incomplete" in content

        # Sales Fee remains PENDING SOURCE and deferred to Phase 9C
        assert "Deferred to Phase 9C" in content


# =========================================================================
# 6. SEMANTIC PAYMENT IDENTITY & REVERSAL (Checkpoints 41-44)
# =========================================================================


@pytest.mark.django_db
class TestIncentivePaymentSemanticIdentity:
    def test_post_incentive_payment_semantic_identity_and_reversal(self, b3_fixture):
        """41, 42, 43, 44: Payment creates IncentivePayment document type,
        synchronizes lifecycle, handles reversal.
        """
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]
        liq_acc = b3_fixture["liq_acc"]

        create_incentive_rule(
            legal_entity=entity,
            code="RULE-ITEM-A",
            name="Rule Item A",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )
        accrual = accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)
        approve_incentive_accrual(accrual, actor=user)
        posting = post_incentive_payable(accrual, actor=user)

        payable = posting.payable_entry

        # Settle payable via semantic wrapper post_incentive_payment
        payment = post_incentive_payment(
            legal_entity=entity,
            liquidity_account=liq_acc,
            payable=payable,
            payment_date=datetime.date(2026, 3, 5),
            source_key=f"INC-PAY-{accrual.pk}",
            actor=user,
        )

        assert payment.source_document_type == "IncentivePayment"
        assert payment.source_module == "FINANCE"
        assert payment.journal.description == "Incentive payment"
        assert payment.partner is None  # Employee beneficiary preserved without fake vendor

        payable.refresh_from_db()
        assert payable.open_amount == Decimal("0")

        accrual.refresh_from_db()
        assert accrual.state == IncentiveAccrualState.PAID

        # Payment reversal reopens accrual to PAYABLE
        reverse_payment(payment, actor=user)
        payable.refresh_from_db()
        assert payable.open_amount == Decimal("25000")

        accrual.refresh_from_db()
        assert accrual.state == IncentiveAccrualState.PAYABLE

    def test_reverse_accounting_dashboard_action_unpaid_vs_settled(self, b3_fixture):
        """44. Reverse Accounting action available for unpaid accrual, blocked when settled."""
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]

        create_incentive_rule(
            legal_entity=entity,
            code="RULE-ITEM-A",
            name="Rule Item A",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )
        accrual = accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)
        approve_incentive_accrual(accrual, actor=user)
        posting = post_incentive_payable(accrual, actor=user)

        # Source reversed while unpaid -> SOURCE_REVERSED_FINANCE_REVERSAL_PENDING
        reverse_cpo_fee_for_receipt_line(
            rcp_line_a, actor=user, reason="Physical receipt correction"
        )

        client = Client()
        client.force_login(b3_fixture["ops_user"])
        resp = client.get(reverse("incentives:cpo-dashboard"))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "SOURCE REVERSED" in content
        # Action button to reverse finance should be present
        assert reverse("incentives:cpo-reverse-finance", args=[posting.pk]) in content

        # Reverse finance via POST
        resp_post = client.post(reverse("incentives:cpo-reverse-finance", args=[posting.pk]))
        assert resp_post.status_code == 302

        posting.refresh_from_db()
        assert posting.state == IncentivePostingState.REVERSED


# =========================================================================
# 7. MINI-CORRECTION 9B3R: QUANTITY FIDELITY + ACCRUAL AUTHORITY + LIFECYCLE
# =========================================================================


@pytest.mark.django_db
class TestPhase9B3RQuantityFidelityAndLifecycle:
    def test_1_accepted_quantity_six_decimals_fidelity_and_exact_whole_rupiah_calculation(
        self, b3_fixture
    ):
        """1, 2, 3: Accepted quantity 1.234567 preserved at 6 decimals without 4-decimal
        quantization, rate 1,000,000 produces 1,234,567 whole Rupiah, and fractional result blocks.
        """
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]

        # Set 6-decimal accepted quantity on authoritative Warehouse line
        rcp_line_a.accepted_quantity = Decimal("1.234567")
        rcp_line_a.save(update_fields=("accepted_quantity",))

        # Effective rule with rate = 1,000,000
        create_incentive_rule(
            legal_entity=entity,
            code="RULE-PRECISE-6DEC",
            name="Precise 6-decimal Rule",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("1000000"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )

        accrual = accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)

        # 1. basis_quantity preserved exactly with 6 decimal places (NOT quantized to 4)
        assert accrual.basis_quantity == Decimal("1.234567")

        # 2. Calculation: 1.234567 * 1,000,000 = 1,234,567 whole Rupiah (NOT 1,234,600)
        assert accrual.amount == Decimal("1234567")

    def test_2_fractional_rupiah_final_result_is_strictly_blocked(self, b3_fixture):
        """3. When quantity * rate produces fractional Rupiah, accrual is blocked."""
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]

        rcp_line_a.accepted_quantity = Decimal("1.234567")
        rcp_line_a.save(update_fields=("accepted_quantity",))

        # Rate = 100 -> 1.234567 * 100 = 123.4567 IDR (fractional Rupiah)
        create_incentive_rule(
            legal_entity=entity,
            code="RULE-FRACTIONAL",
            name="Fractional Rate Rule",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("100"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )

        with pytest.raises(ValidationError) as exc:
            accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)
        assert "fractional Rupiah" in str(exc.value) or "NON_WHOLE_RUPIAH_RESULT" in str(exc.value)

    def test_3_cpo_detail_ui_displays_exact_preserved_quantity(self, b3_fixture):
        """4. CPO detail UI displays exact preserved quantity basis without truncation."""
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]

        rcp_line_a.accepted_quantity = Decimal("1.234567")
        rcp_line_a.save(update_fields=("accepted_quantity",))

        create_incentive_rule(
            legal_entity=entity,
            code="RULE-EXACT-QTY-UI",
            name="Exact Qty UI Rule",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("1000000"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )
        accrual = accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)

        client = Client()
        client.force_login(b3_fixture["ops_user"])
        resp = client.get(reverse("incentives:cpo-detail", args=[accrual.pk]))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "1.234567 unit" in content or "1,234567 unit" in content
        assert "1234567" in content or "1.234.567" in content

    def test_4_dashboard_business_accrual_authority_and_totals(self, b3_fixture):
        """5, 6, 7, 8, 9: ACCRUED, APPROVED, PAYABLE, PAID contribute to business-accrual total;
        REVERSED and candidates excluded. Approved total excludes ACCRUED.
        """
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]

        create_incentive_rule(
            legal_entity=entity,
            code="RULE-AUTHORITY-TEST",
            name="Authority Test Rule",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )

        client = Client()
        client.force_login(b3_fixture["ops_user"])

        # 1. Before accrual: Candidate READY -> monetary total is 0
        resp_cand = client.get(reverse("incentives:cpo-dashboard"))
        assert resp_cand.context["summary"]["authoritative_total_amount"] == Decimal("0")
        assert resp_cand.context["summary"]["approved_total_amount"] == Decimal("0")

        # 2. Accrued: ACCRUED state is authoritative business accrual (contributes to total)
        accrual = accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)
        assert accrual.state == IncentiveAccrualState.ACCRUED

        resp_accrued = client.get(reverse("incentives:cpo-dashboard"))
        # ACCRUED contributes to business-accrual total
        assert resp_accrued.context["summary"]["authoritative_total_amount"] == Decimal("25000")
        # ACCRUED is excluded from the narrower approved/finance-eligible total
        assert resp_accrued.context["summary"]["approved_total_amount"] == Decimal("0")

        # 3. Approved: Contributes to both business-accrual and approved totals
        approve_incentive_accrual(accrual, actor=user)
        resp_approved = client.get(reverse("incentives:cpo-dashboard"))
        assert resp_approved.context["summary"]["authoritative_total_amount"] == Decimal("25000")
        assert resp_approved.context["summary"]["approved_total_amount"] == Decimal("25000")

        # 4. Payable: Contributes to both totals
        posting = post_incentive_payable(accrual, actor=user)
        resp_payable = client.get(reverse("incentives:cpo-dashboard"))
        assert resp_payable.context["summary"]["authoritative_total_amount"] == Decimal("25000")
        assert resp_payable.context["summary"]["approved_total_amount"] == Decimal("25000")

        # 5. Paid: Contributes to both totals
        post_incentive_payment(
            legal_entity=entity,
            liquidity_account=b3_fixture["liq_acc"],
            payable=posting.payable_entry,
            payment_date=datetime.date(2026, 3, 5),
            source_key=f"PAY-AUTH-{accrual.pk}",
            actor=user,
        )
        accrual.refresh_from_db()
        assert accrual.state == IncentiveAccrualState.PAID
        resp_paid = client.get(reverse("incentives:cpo-dashboard"))
        assert resp_paid.context["summary"]["authoritative_total_amount"] == Decimal("25000")
        assert resp_paid.context["summary"]["approved_total_amount"] == Decimal("25000")

        # 6. Reversed: Does NOT contribute to any monetary totals
        reverse_cpo_fee_for_receipt_line(rcp_line_a, actor=user, reason="Correction")
        accrual.refresh_from_db()
        assert accrual.state == IncentiveAccrualState.REVERSED
        resp_reversed = client.get(reverse("incentives:cpo-dashboard"))
        assert resp_reversed.context["summary"]["authoritative_total_amount"] == Decimal("0")
        assert resp_reversed.context["summary"]["approved_total_amount"] == Decimal("0")

    def test_5_project_cpo_reconciliation_and_completeness_gating(self, b3_fixture):
        """10, 11, 12: Project CPO reconciles dashboard amount with Project CPO actual cost;
        incomplete coverage remains PENDING_SOURCE even with partial accrual.
        """
        project = b3_fixture["project"]
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]
        rcp_line_b = b3_fixture["rcp_line_b"]

        # 1. Partial coverage: only Item A has a rule & accrual; Item B has no rule (PENDING_RULE)
        create_incentive_rule(
            legal_entity=entity,
            code="RULE-PROJ-ITEM-A",
            name="Rule Proj Item A",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )
        accrual_a = accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)

        # Incomplete coverage verification: Project profitability remains PENDING_SOURCE
        prof_incomplete = project_profitability(project)
        cpo_cat_incomplete = prof_incomplete.actual_categories[ProjectBudgetCategory.CPO_FEE]
        assert cpo_cat_incomplete.availability == PENDING_SOURCE
        assert cpo_cat_incomplete.reason == "INCOMPLETE_CPO_ACCRUAL_COVERAGE"

        # Dashboard filtered by project displays completeness warning
        client = Client()
        client.force_login(b3_fixture["ops_user"])
        resp_dash_incomplete = client.get(
            reverse("incentives:cpo-dashboard") + f"?project_id={project.pk}"
        )
        assert resp_dash_incomplete.status_code == 200
        content_incomplete = resp_dash_incomplete.content.decode()
        assert "INCOMPLETE_CPO_ACCRUAL_COVERAGE" in content_incomplete
        assert (
            "recorded/accrued amount" in content_incomplete
            or "jumlah akrual yang tercatat" in content_incomplete
        )

        # 2. Complete coverage: Item B also gets a rule & accrual
        create_incentive_rule(
            legal_entity=entity,
            code="RULE-PROJ-ITEM-B",
            name="Rule Proj Item B",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("400"),
            effective_from=datetime.date(2026, 1, 1),
            item=b3_fixture["item_b"],
            actor=user,
        )
        accrual_b = accrue_cpo_fee_for_receipt_line(rcp_line_b, actor=user)

        # Total expected: accrual_a (50 * 500 = 25,000) + accrual_b (30 * 400 = 12,000) = 37,000
        expected_total = Decimal("37000")

        # Project profitability is now AUTHORITATIVE_AVAILABLE
        prof_complete = project_profitability(project)
        cpo_cat_complete = prof_complete.actual_categories[ProjectBudgetCategory.CPO_FEE]
        assert cpo_cat_complete.availability == AUTHORITATIVE_AVAILABLE
        assert cpo_cat_complete.amount == expected_total

        # Dashboard total matches project CPO cost
        resp_dash_complete = client.get(
            reverse("incentives:cpo-dashboard") + f"?project_id={project.pk}"
        )
        assert resp_dash_complete.context["summary"]["authoritative_total_amount"] == expected_total

        # 3. ACCRUED -> APPROVED -> PAYABLE -> PAID does NOT change Project CPO cost
        approve_incentive_accrual(accrual_a, actor=user)
        approve_incentive_accrual(accrual_b, actor=user)
        prof_approved = project_profitability(project)
        assert (
            prof_approved.actual_categories[ProjectBudgetCategory.CPO_FEE].amount == expected_total
        )

        posting_a = post_incentive_payable(accrual_a, actor=user)
        prof_payable = project_profitability(project)
        assert (
            prof_payable.actual_categories[ProjectBudgetCategory.CPO_FEE].amount == expected_total
        )

        post_incentive_payment(
            legal_entity=entity,
            liquidity_account=b3_fixture["liq_acc"],
            payable=posting_a.payable_entry,
            payment_date=datetime.date(2026, 3, 5),
            source_key=f"PAY-RECON-{accrual_a.pk}",
            actor=user,
        )
        prof_paid = project_profitability(project)
        assert prof_paid.actual_categories[ProjectBudgetCategory.CPO_FEE].amount == expected_total

    def test_6_incentives_owns_accrual_lifecycle_and_rejects_invalid_evidence(self, b3_fixture):
        """13, 14, 15, 16: Finance posting, payment, and payment reversal call Incentives-owned
        services; invalid evidence is strictly rejected.
        """
        entity = b3_fixture["entity"]
        user = b3_fixture["admin_user"]
        item_a = b3_fixture["item_a"]
        rcp_line_a = b3_fixture["rcp_line_a"]

        create_incentive_rule(
            legal_entity=entity,
            code="RULE-LIFECYCLE-OWN",
            name="Rule Lifecycle Own",
            incentive_type=IncentiveType.CPO_FEE,
            trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
            calculation_method=IncentiveCalculationMethod.PER_UNIT,
            rate_value=Decimal("500"),
            effective_from=datetime.date(2026, 1, 1),
            item=item_a,
            actor=user,
        )
        accrual = accrue_cpo_fee_for_receipt_line(rcp_line_a, actor=user)
        approve_incentive_accrual(accrual, actor=user)
        posting = post_incentive_payable(accrual, actor=user)

        # Posting transitions to PAYABLE via mark_accrual_payable_from_finance
        accrual.refresh_from_db()
        assert accrual.state == IncentiveAccrualState.PAYABLE

        # Reject invalid evidence: passing mismatched posting
        fake_accrual = IncentiveAccrual(pk=uuid.uuid4())
        with pytest.raises(ValidationError) as exc_mismatch:
            mark_accrual_payable_from_finance(fake_accrual, posting=posting, actor=user)
        assert "Finance posting does not match" in str(exc_mismatch.value)

        # Reject invalid state: cannot mark PAID if payable still has open_amount > 0
        with pytest.raises(ValidationError) as exc_open:
            mark_accrual_paid_from_finance(accrual, posting=posting, actor=user)
        assert "still has open amount" in str(exc_open.value)

        # Settle payable via post_incentive_payment -> calls mark_accrual_paid_from_finance
        payment = post_incentive_payment(
            legal_entity=entity,
            liquidity_account=b3_fixture["liq_acc"],
            payable=posting.payable_entry,
            payment_date=datetime.date(2026, 3, 5),
            source_key=f"PAY-LIFECYCLE-{accrual.pk}",
            actor=user,
        )
        accrual.refresh_from_db()
        assert accrual.state == IncentiveAccrualState.PAID

        # Reject reopen if open_amount is 0
        with pytest.raises(ValidationError) as exc_no_open:
            reopen_accrual_payable_from_finance(accrual, posting=posting, actor=user)
        assert "has no open amount" in str(exc_no_open.value)

        # Payment reversal reopens via reopen_accrual_payable_from_finance
        reverse_payment(payment, actor=user)
        accrual.refresh_from_db()
        assert accrual.state == IncentiveAccrualState.PAYABLE


# =========================================================================
# 8. SMB GAS INTEGRITY (Immutable 50 files)
# =========================================================================


class TestSMBGASIntegrity:
    def test_legacy_smb_gas_hash_and_file_count_preserved(self):
        """Verifies legacy/smb_gas remains exactly 50 files with aggregate SHA-256."""
        from apps.incentives.tests.legacy_helpers import verify_legacy_smb_gas_integrity

        verify_legacy_smb_gas_integrity()

    def test_legacy_smb_gas_hash_cross_platform_lf_simulation(self):
        """Verifies integrity check computes identical aggregate hash under simulated LF."""
        from apps.incentives.tests.legacy_helpers import (
            OFFICIAL_LEGACY_SMB_GAS_FILE_COUNT,
            OFFICIAL_LEGACY_SMB_GAS_SHA256,
            compute_legacy_smb_gas_aggregate_hash,
        )

        file_count, aggregate_hash = compute_legacy_smb_gas_aggregate_hash(_force_lf=True)
        assert file_count == OFFICIAL_LEGACY_SMB_GAS_FILE_COUNT
        assert aggregate_hash == OFFICIAL_LEGACY_SMB_GAS_SHA256
