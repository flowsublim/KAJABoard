"""Tests for Phase 9A2A: Project Forecast Planning + Variance Core."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.catalog.models import UOM, Item
from apps.core.models import AuditEvent
from apps.core.services.numbering import allocate_document_number, create_document_sequence
from apps.finance.models import (
    COAAccount,
    JournalEntry,
    JournalLine,
    JournalState,
    LiquidityEntry,
    PayableEntry,
    Payment,
    ReceivableEntry,
)
from apps.finance.services.posting import reverse_journal
from apps.organizations.models import CostCenter, CostCenterCategory, LegalEntity, Warehouse
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.projects.models import (
    ProjectBudgetCategory,
    ProjectForecastLine,
    ProjectState,
)
from apps.projects.selectors.profitability import (
    AUTHORITATIVE_AVAILABLE,
    PENDING_SOURCE,
    project_profitability,
)
from apps.projects.services import (
    activate_project,
    add_project_budget_line,
    add_project_forecast_line,
    cancel_project,
    complete_project,
    create_draft_project,
    hold_project,
    link_sales_order,
    remove_project_forecast_line,
    update_project_forecast_line,
)
from apps.purchasing.models import (
    AccountingTreatment,
    PurchaseCategory,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderState,
    SubcontractCostType,
    SubcontractReceipt,
    SubcontractReceiptCostLine,
    SubcontractReceiptState,
    WorkOrder,
    WorkOrderState,
)
from apps.sales.models import (
    SalesInvoice,
    SalesInvoiceDocumentKind,
    SalesInvoiceLine,
    SalesInvoiceState,
)
from apps.sales.services import add_draft_line, confirm_sales_order, create_draft_sales_order
from apps.warehouse.models import (
    InternalConsumption,
    InternalConsumptionLine,
    StockMovement,
    WarehouseDocumentState,
)

User = get_user_model()


def make_sales_invoice(entity, customer, so_line, amount=Decimal("12000000")):
    alloc = allocate_document_number(entity, "SALES_INVOICE", business_date=timezone.localdate())
    inv = SalesInvoice.objects.create(
        legal_entity=entity,
        customer=customer,
        customer_code_snapshot=customer.code,
        customer_name_snapshot=customer.display_name,
        document_allocation=alloc,
        document_number=alloc.number,
        document_kind=SalesInvoiceDocumentKind.INVOICE,
        invoice_date=timezone.localdate(),
        source_mode="SALES_ORDER",
        state=SalesInvoiceState.CONFIRMED,
        subtotal=amount,
        grand_total=amount,
    )
    SalesInvoiceLine.objects.create(
        sales_invoice=inv,
        line_number=1,
        source_sales_order_line=so_line,
        item=so_line.item,
        item_code_snapshot=so_line.item.code,
        item_name_snapshot=so_line.item.name,
        uom_code_snapshot=so_line.uom_code_snapshot,
        quantity=so_line.quantity,
        unit_price=so_line.unit_price,
        line_total=amount,
    )
    return inv


def post_revenue_journal(entity, invoice, amount=Decimal("12000000")):
    account, _ = COAAccount.objects.get_or_create(
        legal_entity=entity,
        account_code="4000",
        defaults={
            "account_code_normalized": "4000",
            "account_name": "Sales Revenue",
            "account_type": "REVENUE",
            "normal_balance": "CREDIT",
            "effective_from": timezone.localdate(),
        },
    )
    ar_account, _ = COAAccount.objects.get_or_create(
        legal_entity=entity,
        account_code="1100",
        defaults={
            "account_code_normalized": "1100",
            "account_name": "AR Control",
            "account_type": "ASSET",
            "normal_balance": "DEBIT",
            "effective_from": timezone.localdate(),
        },
    )
    journal = JournalEntry.objects.create(
        legal_entity=entity,
        journal_number=f"JNL-{invoice.document_number}",
        accounting_date=invoice.invoice_date,
        event_code="SALES_INVOICE",
        source_module="SALES",
        source_document_type="SalesInvoice",
        source_document_id=str(invoice.pk),
        source_key=f"SALES_INVOICE|{invoice.pk}",
        total_debit=amount,
        total_credit=amount,
        state=JournalState.POSTED,
        posted_at=timezone.now(),
    )
    JournalLine.objects.create(
        journal=journal,
        sequence=1,
        line_role="REVENUE",
        account=account,
        account_code_snapshot=account.account_code,
        account_name_snapshot=account.account_name,
        debit=Decimal("0"),
        credit=amount,
    )
    JournalLine.objects.create(
        journal=journal,
        sequence=2,
        line_role="AR_CONTROL",
        account=ar_account,
        account_code_snapshot=ar_account.account_code,
        account_name_snapshot=ar_account.account_name,
        debit=amount,
        credit=Decimal("0"),
    )
    return journal


@pytest.fixture
def project_data():
    entity = LegalEntity.objects.create(code="E9A2", name="Entity 9A2")
    user = User.objects.create_user("user9a2@example.com", "password")
    customer = BusinessPartner.objects.create(
        legal_entity=entity, code="CUST-9A2", display_name="Customer 9A2"
    )
    PartnerRole.objects.create(partner=customer, role_type=PartnerRoleType.CUSTOMER)
    vendor = BusinessPartner.objects.create(
        legal_entity=entity, code="VEND-9A2", display_name="Vendor 9A2"
    )
    PartnerRole.objects.create(partner=vendor, role_type=PartnerRoleType.VENDOR)
    uom = UOM.objects.create(code="PCS9A2", name="Pieces 9A2", dimension="COUNT")
    item = Item.objects.create(
        legal_entity=entity, code="ITEM-9A2", name="Item 9A2", uom=uom, sales_eligible=True
    )
    warehouse = Warehouse.objects.create(legal_entity=entity, code="WH-9A2", name="Warehouse 9A2")
    category = PurchaseCategory.objects.create(
        legal_entity=entity,
        code="MAT-9A2",
        name="Material Category",
        accounting_treatment=AccountingTreatment.INVENTORY,
    )
    cost_center = CostCenter.objects.create(
        legal_entity=entity,
        code="CC-9A2",
        name="Cost Center 9A2",
        category=CostCenterCategory.GENERAL,
        effective_from=timezone.localdate(),
    )

    prefixes = {
        "PROJECT": "PRJ",
        "SALES_ORDER": "SO",
        "SALES_INVOICE": "INV",
        "PURCHASE_ORDER": "PO",
        "WORK_ORDER": "WO",
        "SUBCONTRACT_RECEIPT": "SR",
    }
    for doc_type, pfx in prefixes.items():
        create_document_sequence(
            legal_entity=entity,
            document_type=doc_type,
            name=doc_type,
            prefix=pfx,
            format_template="{prefix}-{yyyymmdd}-{seq}",
            padding=3,
        )

    project = create_draft_project(
        legal_entity=entity,
        customer=customer,
        name="Phase 9A2 Project",
        start_date=timezone.localdate(),
        actor=user,
        idempotency_key="proj-9a2-init",
    )

    return {
        "entity": entity,
        "user": user,
        "customer": customer,
        "vendor": vendor,
        "item": item,
        "warehouse": warehouse,
        "category": category,
        "cost_center": cost_center,
        "project": project,
    }


# =========================================================================
# 1. No forecast lines: forecast = PENDING_SOURCE, not zero.
# =========================================================================
@pytest.mark.django_db
def test_1_no_forecast_lines_returns_pending_source(project_data):
    project = project_data["project"]
    profitability = project_profitability(project)

    assert profitability.forecast_cost is None
    assert profitability.forecast_cost_metric.availability == PENDING_SOURCE
    assert profitability.forecast_cost_metric.amount is None
    assert profitability.forecast_cost != Decimal("0")
    assert "NO_ACTIVE_PROJECT_FORECAST_LINES" in profitability.forecast_cost_metric.reason
    assert "forecast" in profitability.missing_sources


# =========================================================================
# 2. One active forecast line: forecast total available.
# =========================================================================
@pytest.mark.django_db
def test_2_one_active_forecast_line_forecast_total_available(project_data):
    project = project_data["project"]
    user = project_data["user"]

    line = add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Planned material cost",
        amount=Decimal("15000000"),
    )
    assert line.amount == Decimal("15000000.00")

    profitability = project_profitability(project)
    assert profitability.forecast_cost == Decimal("15000000.00")
    assert profitability.forecast_cost_metric.availability == AUTHORITATIVE_AVAILABLE
    assert profitability.forecast_cost_metric.record_count == 1
    assert "forecast" not in profitability.missing_sources


# =========================================================================
# 3. Multiple categories: exact total and category breakdown.
# =========================================================================
@pytest.mark.django_db
def test_3_multiple_categories_exact_total_and_category_breakdown(project_data):
    project = project_data["project"]
    user = project_data["user"]

    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Fabrics",
        amount=Decimal("10000000"),
    )
    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.LABOR,
        description="Sewing labor",
        amount=Decimal("5000000"),
    )
    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MAKLUN,
        description="Printing subcontract",
        amount=Decimal("3000000"),
    )

    profitability = project_profitability(project)
    assert profitability.forecast_cost == Decimal("18000000.00")
    assert profitability.forecast_categories[ProjectBudgetCategory.MATERIAL].amount == Decimal(
        "10000000.00"
    )
    assert profitability.forecast_categories[ProjectBudgetCategory.LABOR].amount == Decimal(
        "5000000.00"
    )
    assert profitability.forecast_categories[ProjectBudgetCategory.MAKLUN].amount == Decimal(
        "3000000.00"
    )
    assert (
        profitability.forecast_categories[ProjectBudgetCategory.MATERIAL].availability
        == AUTHORITATIVE_AVAILABLE
    )
    assert (
        profitability.forecast_categories[ProjectBudgetCategory.CPO_FEE].availability
        == PENDING_SOURCE
    )


# =========================================================================
# 4. Inactive forecast line excluded.
# =========================================================================
@pytest.mark.django_db
def test_4_inactive_forecast_line_excluded(project_data):
    project = project_data["project"]
    user = project_data["user"]

    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Active material",
        amount=Decimal("10000000"),
        is_active=True,
    )
    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Discarded variant",
        amount=Decimal("5000000"),
        is_active=False,
    )

    profitability = project_profitability(project)
    assert profitability.forecast_cost == Decimal("10000000.00")
    assert len(profitability.forecast_line_ids) == 1


# =========================================================================
# 5. DRAFT project forecast create succeeds without reason.
# =========================================================================
@pytest.mark.django_db
def test_5_draft_project_forecast_create_succeeds_without_reason(project_data):
    project = project_data["project"]
    user = project_data["user"]
    assert project.state == ProjectState.DRAFT

    line = add_project_forecast_line(
        project,
        actor=user,
        reason="",
        category=ProjectBudgetCategory.MATERIAL,
        description="Initial draft estimation",
        amount=Decimal("8000000"),
    )
    assert line.amount == Decimal("8000000.00")
    assert line.is_active


# =========================================================================
# 6. ACTIVE project requires reason for forecast create.
# =========================================================================
@pytest.mark.django_db
def test_6_active_project_requires_reason_for_forecast_create(project_data):
    project = project_data["project"]
    user = project_data["user"]
    project = activate_project(project, actor=user)
    assert project.state == ProjectState.ACTIVE

    with pytest.raises(ValidationError) as exc:
        add_project_forecast_line(
            project,
            actor=user,
            reason="",
            category=ProjectBudgetCategory.MATERIAL,
            description="Material update",
            amount=Decimal("5000000"),
        )
    assert "reason" in exc.value.message_dict

    # Succeeds with reason
    line = add_project_forecast_line(
        project,
        actor=user,
        reason="Updated BOM pricing from vendor quote",
        category=ProjectBudgetCategory.MATERIAL,
        description="Material update",
        amount=Decimal("5000000"),
    )
    assert line.amount == Decimal("5000000.00")


# =========================================================================
# 7. ON_HOLD project requires reason for forecast create.
# =========================================================================
@pytest.mark.django_db
def test_7_on_hold_project_requires_reason_for_forecast_create(project_data):
    project = project_data["project"]
    user = project_data["user"]
    project = activate_project(project, actor=user)
    project = hold_project(project, actor=user, reason="Hold for scope review")
    assert project.state == ProjectState.ON_HOLD

    with pytest.raises(ValidationError) as exc:
        add_project_forecast_line(
            project,
            actor=user,
            reason="",
            category=ProjectBudgetCategory.MATERIAL,
            description="Material scope adjustment",
            amount=Decimal("7000000"),
        )
    assert "reason" in exc.value.message_dict

    line = add_project_forecast_line(
        project,
        actor=user,
        reason="Scope negotiation update",
        category=ProjectBudgetCategory.MATERIAL,
        description="Material scope adjustment",
        amount=Decimal("7000000"),
    )
    assert line.amount == Decimal("7000000.00")


# =========================================================================
# 8. COMPLETED project forecast edit blocked.
# =========================================================================
@pytest.mark.django_db
def test_8_completed_project_forecast_edit_blocked(project_data):
    project = project_data["project"]
    user = project_data["user"]
    line = add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Base",
        amount=Decimal("5000000"),
    )
    project = activate_project(project, actor=user)
    project = complete_project(project, actor=user, reason="Project successfully delivered")
    assert project.state == ProjectState.COMPLETED

    with pytest.raises(ValidationError):
        add_project_forecast_line(
            project,
            actor=user,
            reason="Post-complete add",
            category=ProjectBudgetCategory.LABOR,
            description="Extra",
            amount=Decimal("1000000"),
        )

    with pytest.raises(ValidationError):
        update_project_forecast_line(
            line, actor=user, reason="Post-complete update", amount=Decimal("6000000")
        )

    with pytest.raises(ValidationError):
        remove_project_forecast_line(line, actor=user, reason="Post-complete delete")


# =========================================================================
# 9. CANCELLED project forecast edit blocked.
# =========================================================================
@pytest.mark.django_db
def test_9_cancelled_project_forecast_edit_blocked(project_data):
    project = project_data["project"]
    user = project_data["user"]
    line = add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Base",
        amount=Decimal("5000000"),
    )
    project = cancel_project(project, actor=user, reason="Client cancelled engagement")
    assert project.state == ProjectState.CANCELLED

    with pytest.raises(ValidationError):
        add_project_forecast_line(
            project,
            actor=user,
            reason="Post-cancel add",
            category=ProjectBudgetCategory.LABOR,
            description="Extra",
            amount=Decimal("1000000"),
        )

    with pytest.raises(ValidationError):
        update_project_forecast_line(
            line, actor=user, reason="Post-cancel update", amount=Decimal("6000000")
        )

    with pytest.raises(ValidationError):
        remove_project_forecast_line(line, actor=user, reason="Post-cancel delete")


# =========================================================================
# 10. Update requires reason.
# =========================================================================
@pytest.mark.django_db
def test_10_update_requires_reason(project_data):
    project = project_data["project"]
    user = project_data["user"]
    line = add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Base fabrics",
        amount=Decimal("5000000"),
    )

    with pytest.raises(ValidationError) as exc:
        update_project_forecast_line(line, actor=user, reason="", amount=Decimal("7000000"))
    assert "reason" in exc.value.message_dict

    updated = update_project_forecast_line(
        line,
        actor=user,
        reason="Fabric requirement increase after design approval",
        amount=Decimal("7000000"),
    )
    assert updated.amount == Decimal("7000000.00")


# =========================================================================
# 11. Remove requires reason and preserves auditability.
# =========================================================================
@pytest.mark.django_db
def test_11_remove_requires_reason_and_preserves_auditability(project_data):
    project = project_data["project"]
    user = project_data["user"]
    line = add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="To remove",
        amount=Decimal("3000000"),
    )
    line_pk = line.pk

    with pytest.raises(ValidationError) as exc:
        remove_project_forecast_line(line, actor=user, reason="")
    assert "reason" in exc.value.message_dict

    remove_project_forecast_line(line, actor=user, reason="Obsolete forecast line removed by PM")
    assert not ProjectForecastLine.objects.filter(pk=line_pk).exists()

    audit = AuditEvent.objects.filter(
        target_type="projects.projectforecastline",
        target_id=line_pk,
        action="projects.projectforecastline.removed",
    ).first()
    assert audit is not None
    assert audit.reason == "Obsolete forecast line removed by PM"


# =========================================================================
# 12. Cross-entity cost center / purchase category / item rejected.
# =========================================================================
@pytest.mark.django_db
def test_12_cross_entity_dimensions_rejected(project_data):
    project = project_data["project"]
    user = project_data["user"]

    entity2 = LegalEntity.objects.create(code="E9A2-OTHER", name="Entity Other")
    cc_other = CostCenter.objects.create(
        legal_entity=entity2,
        code="CC-OTHER",
        name="Cost Center Other",
        category=CostCenterCategory.GENERAL,
        effective_from=timezone.localdate(),
    )
    cat_other = PurchaseCategory.objects.create(
        legal_entity=entity2,
        code="CAT-OTHER",
        name="Category Other",
        accounting_treatment=AccountingTreatment.INVENTORY,
    )
    uom = UOM.objects.create(code="PCS-OTH", name="Pieces Other", dimension="COUNT")
    item_other = Item.objects.create(
        legal_entity=entity2, code="ITM-OTH", name="Item Other", uom=uom
    )

    with pytest.raises(ValidationError):
        add_project_forecast_line(
            project,
            actor=user,
            category=ProjectBudgetCategory.MATERIAL,
            description="Cross entity cost center",
            amount=Decimal("1000000"),
            cost_center=cc_other,
        )

    with pytest.raises(ValidationError):
        add_project_forecast_line(
            project,
            actor=user,
            category=ProjectBudgetCategory.MATERIAL,
            description="Cross entity purchase category",
            amount=Decimal("1000000"),
            purchase_category=cat_other,
        )

    with pytest.raises(ValidationError):
        add_project_forecast_line(
            project,
            actor=user,
            category=ProjectBudgetCategory.MATERIAL,
            description="Cross entity item",
            amount=Decimal("1000000"),
            item=item_other,
        )


# =========================================================================
# 13. Budget vs forecast variance: positive / zero / negative semantics.
# =========================================================================
@pytest.mark.django_db
def test_13_budget_vs_forecast_variance_semantics(project_data):
    project = project_data["project"]
    user = project_data["user"]

    add_project_budget_line(
        project,
        actor=user,
        reason="Initial budget line",
        category="MATERIAL",
        description="Budgeted fabrics",
        amount=Decimal("20000000"),
    )
    project.refresh_from_db()

    # Case A: Forecast (15,000,000) < Budget (20,000,000) => Positive variance (Under budget)
    f_line = add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Fabrics forecast",
        amount=Decimal("15000000"),
    )
    prof_under = project_profitability(project)
    assert prof_under.variance_budget_forecast == Decimal("5000000.00")

    # Case B: Forecast (20,000,000) == Budget (20,000,000) => Zero variance (On budget)
    update_project_forecast_line(
        f_line, actor=user, reason="Adjust to match budget", amount=Decimal("20000000")
    )
    prof_equal = project_profitability(project)
    assert prof_equal.variance_budget_forecast == Decimal("0.00")

    # Case C: Forecast (25,000,000) > Budget (20,000,000) => Negative variance (Exceeds budget)
    update_project_forecast_line(
        f_line, actor=user, reason="Price escalation adjustment", amount=Decimal("25000000")
    )
    prof_over = project_profitability(project)
    assert prof_over.variance_budget_forecast == Decimal("-5000000.00")


# =========================================================================
# 14. Budget vs actual remains PENDING_SOURCE if actual unavailable.
# =========================================================================
@pytest.mark.django_db
def test_14_budget_vs_actual_remains_pending_source_if_actual_unavailable(project_data):
    project = project_data["project"]
    user = project_data["user"]

    add_project_budget_line(
        project,
        actor=user,
        reason="Budget line",
        category="MATERIAL",
        description="Material",
        amount=Decimal("20000000"),
    )
    profitability = project_profitability(project)

    assert profitability.actual_cost is None
    assert profitability.variance_budget_actual is None


# =========================================================================
# 15. Forecast vs actual only calculated when both authoritative.
# =========================================================================
@pytest.mark.django_db
def test_15_forecast_vs_actual_only_calculated_when_both_authoritative(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    user = project_data["user"]
    warehouse = project_data["warehouse"]
    item = project_data["item"]

    # Forecast only: actual is None
    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Forecast",
        amount=Decimal("10000000"),
    )
    prof1 = project_profitability(project)
    assert prof1.forecast_cost == Decimal("10000000.00")
    assert prof1.actual_cost is None
    assert prof1.remaining_to_forecast is None

    # Now add actual cost via posted InternalConsumption
    consumption = InternalConsumption.objects.create(
        legal_entity=entity,
        warehouse=warehouse,
        project=project,
        transaction_date=timezone.localdate(),
        purpose="Project sampling",
        reason="Sampling",
        state=WarehouseDocumentState.POSTED,
    )
    InternalConsumptionLine.objects.create(
        consumption=consumption,
        item=item,
        quantity=Decimal("4"),
        uom_code_snapshot="PCS",
        source_key="IC-9A2-001",
        sequence=1,
        unit_cost=Decimal("1000000"),
        total_value=Decimal("4000000"),
    )

    prof2 = project_profitability(project)
    assert prof2.forecast_cost == Decimal("10000000.00")
    assert prof2.actual_cost == Decimal("4000000.00")
    # remaining_to_forecast = 10,000,000 - 4,000,000 = 6,000,000
    assert prof2.remaining_to_forecast == Decimal("6000000.00")


# =========================================================================
# 16. actual + committed exposure stays PENDING_SOURCE when committed is PENDING_SOURCE.
# =========================================================================
@pytest.mark.django_db
def test_16_actual_plus_committed_exposure_stays_pending_source_when_committed_is_pending_source(
    project_data,
):
    project = project_data["project"]
    entity = project_data["entity"]
    warehouse = project_data["warehouse"]
    item = project_data["item"]

    # Actual cost exists
    consumption = InternalConsumption.objects.create(
        legal_entity=entity,
        warehouse=warehouse,
        project=project,
        transaction_date=timezone.localdate(),
        purpose="Usage",
        reason="Sampling",
        state=WarehouseDocumentState.POSTED,
    )
    InternalConsumptionLine.objects.create(
        consumption=consumption,
        item=item,
        quantity=Decimal("5"),
        uom_code_snapshot="PCS",
        source_key="IC-9A2-EXP",
        sequence=1,
        unit_cost=Decimal("1000000"),
        total_value=Decimal("5000000"),
    )

    profitability = project_profitability(project)
    assert profitability.actual_cost == Decimal("5000000.00")
    assert profitability.committed_cost is None
    # Must remain PENDING_SOURCE, never silently assume committed = 0
    assert profitability.current_cost_exposure is None


# =========================================================================
# 17. recognized revenue + explicit forecast calculates projected profit.
# =========================================================================
@pytest.mark.django_db
def test_17_recognized_revenue_plus_explicit_forecast_calculates_projected_profit(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    user = project_data["user"]
    customer = project_data["customer"]
    item = project_data["item"]

    activate_project(project, actor=user)

    so = create_draft_sales_order(
        legal_entity=entity, customer=customer, document_date=timezone.localdate(), actor=user
    )
    so_line = add_draft_line(
        so, actor=user, item=item, quantity=Decimal("12"), unit_price=Decimal("1000000")
    )
    confirm_sales_order(so, actor=user)
    link_sales_order(project, so, actor=user)

    invoice = make_sales_invoice(entity, customer, so_line, amount=Decimal("12000000"))
    post_revenue_journal(entity, invoice, amount=Decimal("12000000"))

    add_project_forecast_line(
        project,
        actor=user,
        reason="Expected cost estimate",
        category=ProjectBudgetCategory.MATERIAL,
        description="Forecast total cost",
        amount=Decimal("10000000"),
    )

    profitability = project_profitability(project)
    assert profitability.recognized_revenue == Decimal("12000000.00")
    assert profitability.forecast_cost == Decimal("10000000.00")
    # Projected profit = 12,000,000 - 10,000,000 = 2,000,000
    assert profitability.projected_profit == Decimal("2000000.00")
    # Margin % = (2,000,000 / 12,000,000) * 100 = 16.67%
    assert profitability.projected_margin_percent == Decimal("16.67")


# =========================================================================
# 18. recognized revenue = 0 never divides by zero for margin.
# =========================================================================
@pytest.mark.django_db
def test_18_recognized_revenue_zero_never_divides_by_zero_for_margin(project_data):
    project = project_data["project"]
    user = project_data["user"]

    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Forecast",
        amount=Decimal("5000000"),
    )

    profitability = project_profitability(project)
    assert profitability.recognized_revenue == Decimal("0")
    assert profitability.forecast_cost == Decimal("5000000.00")
    # Projected profit = 0 - 5,000,000 = -5,000,000
    assert profitability.projected_profit == Decimal("-5000000.00")
    # Margin percent is safely None, avoiding ZeroDivisionError
    assert profitability.projected_margin_percent is None


# =========================================================================
# 19. commercial Sales Order value is not substituted for recognized revenue.
# =========================================================================
@pytest.mark.django_db
def test_19_commercial_sales_order_value_is_not_substituted_for_recognized_revenue(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    user = project_data["user"]
    customer = project_data["customer"]
    item = project_data["item"]

    activate_project(project, actor=user)

    so = create_draft_sales_order(
        legal_entity=entity, customer=customer, document_date=timezone.localdate(), actor=user
    )
    add_draft_line(so, actor=user, item=item, quantity=Decimal("50"), unit_price=Decimal("1000000"))
    confirm_sales_order(so, actor=user)
    link_sales_order(project, so, actor=user)

    add_project_forecast_line(
        project,
        actor=user,
        reason="Project forecast",
        category=ProjectBudgetCategory.MATERIAL,
        description="Forecast",
        amount=Decimal("20000000"),
    )

    profitability = project_profitability(project)
    assert profitability.commercial_order_value == Decimal("50000000.00")
    assert profitability.recognized_revenue == Decimal("0")
    # Profit must use recognized_revenue (0 - 20,000,000 = -20,000,000),
    # NEVER 50,000,000 - 20,000,000!
    assert profitability.projected_profit == Decimal("-20000000.00")
    assert profitability.projected_profit != Decimal("30000000.00")


# =========================================================================
# 20. CPO Fee and Sales Fee remain PENDING_SOURCE.
# =========================================================================
@pytest.mark.django_db
def test_20_cpo_fee_and_sales_fee_remain_pending_source(project_data):
    project = project_data["project"]
    profitability = project_profitability(project)

    assert (
        profitability.actual_categories[ProjectBudgetCategory.CPO_FEE].availability
        == PENDING_SOURCE
    )
    assert (
        profitability.actual_categories[ProjectBudgetCategory.SALES_FEE].availability
        == PENDING_SOURCE
    )
    assert (
        profitability.committed_categories[ProjectBudgetCategory.CPO_FEE].availability
        == PENDING_SOURCE
    )
    assert (
        profitability.committed_categories[ProjectBudgetCategory.SALES_FEE].availability
        == PENDING_SOURCE
    )
    assert "incentives" in profitability.missing_sources


# =========================================================================
# 21. forecast selector/service does not create operational/accounting records.
# =========================================================================
@pytest.mark.django_db
def test_21_forecast_selector_and_services_create_zero_operational_accounting_records(project_data):
    project = project_data["project"]
    user = project_data["user"]

    counts_before = {
        "JournalEntry": JournalEntry.objects.count(),
        "JournalLine": JournalLine.objects.count(),
        "Payment": Payment.objects.count(),
        "LiquidityEntry": LiquidityEntry.objects.count(),
        "StockMovement": StockMovement.objects.count(),
        "PurchaseOrder": PurchaseOrder.objects.count(),
        "WorkOrder": WorkOrder.objects.count(),
        "ReceivableEntry": ReceivableEntry.objects.count(),
        "PayableEntry": PayableEntry.objects.count(),
    }

    # Execute service actions and selector queries
    line = add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Forecast 1",
        amount=Decimal("10000000"),
    )
    _ = update_project_forecast_line(
        line, actor=user, reason="Revision", amount=Decimal("12000000")
    )
    _ = project_profitability(project)
    remove_project_forecast_line(line, actor=user, reason="Removed")
    _ = project_profitability(project)

    counts_after = {
        "JournalEntry": JournalEntry.objects.count(),
        "JournalLine": JournalLine.objects.count(),
        "Payment": Payment.objects.count(),
        "LiquidityEntry": LiquidityEntry.objects.count(),
        "StockMovement": StockMovement.objects.count(),
        "PurchaseOrder": PurchaseOrder.objects.count(),
        "WorkOrder": WorkOrder.objects.count(),
        "ReceivableEntry": ReceivableEntry.objects.count(),
        "PayableEntry": PayableEntry.objects.count(),
    }

    assert counts_before == counts_after


# =========================================================================
# 22. Existing 9A1 revenue reversal and MAKLUN lineage tests stay green.
# =========================================================================
@pytest.mark.django_db
def test_22_existing_9a1_revenue_reversal_and_maklun_lineage_remain_green(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    user = project_data["user"]
    customer = project_data["customer"]
    vendor = project_data["vendor"]
    category = project_data["category"]
    item = project_data["item"]

    activate_project(project, actor=user)

    # 1. Revenue reversal check
    so = create_draft_sales_order(
        legal_entity=entity, customer=customer, document_date=timezone.localdate(), actor=user
    )
    so_line = add_draft_line(
        so, actor=user, item=item, quantity=Decimal("10"), unit_price=Decimal("1000000")
    )
    confirm_sales_order(so, actor=user)
    link_sales_order(project, so, actor=user)

    invoice = make_sales_invoice(entity, customer, so_line, amount=Decimal("10000000"))
    journal = post_revenue_journal(entity, invoice, amount=Decimal("10000000"))
    reverse_journal(journal, actor=user, source_key=f"REV|{journal.pk}")

    # 2. Confirmed MAKLUN PO commitment (Case B: no explicit receipt lineage)
    po = PurchaseOrder.objects.create(
        legal_entity=entity,
        project=project,
        vendor=vendor,
        vendor_code_snapshot=vendor.code,
        vendor_name_snapshot=vendor.display_name,
        document_allocation=allocate_document_number(
            entity, "PURCHASE_ORDER", business_date=timezone.localdate()
        ),
        document_number="PO-9A2-MAK",
        document_date=timezone.localdate(),
        state=PurchaseOrderState.CONFIRMED,
        grand_total=Decimal("4000000"),
    )
    PurchaseOrderLine.objects.create(
        purchase_order=po,
        line_number=1,
        item=item,
        purchase_category=category,
        category_code_snapshot=category.code,
        category_name_snapshot=category.name,
        accounting_treatment_snapshot="MAKLUN",
        quantity=Decimal("4"),
        unit_price=Decimal("1000000"),
        line_total=Decimal("4000000"),
    )

    # 3. Accepted subcontract receipt cost on project
    wo = WorkOrder.objects.create(
        legal_entity=entity,
        project=project,
        vendor=vendor,
        document_allocation=allocate_document_number(
            entity, "WORK_ORDER", business_date=timezone.localdate()
        ),
        document_number="WO-9A2-MAK",
        document_date=timezone.localdate(),
        state=WorkOrderState.APPROVED,
    )
    sub_receipt = SubcontractReceipt.objects.create(
        legal_entity=entity,
        document_allocation=allocate_document_number(
            entity, "SUBCONTRACT_RECEIPT", business_date=timezone.localdate()
        ),
        document_number="SR-9A2-MAK",
        work_order=wo,
        vendor=vendor,
        vendor_code_snapshot=vendor.code,
        vendor_name_snapshot=vendor.display_name,
        receipt_date=timezone.localdate(),
        state=SubcontractReceiptState.ACCEPTED,
    )
    SubcontractReceiptCostLine.objects.create(
        receipt=sub_receipt,
        line_number=1,
        cost_type=SubcontractCostType.SHARED_SERVICE,
        amount=Decimal("1500000"),
    )

    profitability = project_profitability(project)

    # Revenue reversal nets to 0
    assert profitability.recognized_revenue == Decimal("0")
    # MAKLUN commitment is PENDING_SOURCE
    assert (
        profitability.committed_categories[ProjectBudgetCategory.MAKLUN].availability
        == PENDING_SOURCE
    )
    assert profitability.committed_cost is None
    # Actual MAKLUN cost remains authoritative
    assert profitability.actual_cost == Decimal("1500000.00")
    assert (
        profitability.actual_categories[ProjectBudgetCategory.MAKLUN].availability
        == AUTHORITATIVE_AVAILABLE
    )
