"""Tests for Phase 9A1: Project Profitability Source Contracts + Core Read Model."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.catalog.models import UOM, Item
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
from apps.organizations.models import LegalEntity, Warehouse
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.production.models import (
    ProductionDirectExtraCost,
    ProductionEntryState,
    ProductionExtraCostCategory,
)
from apps.projects.models import Project, ProjectBudgetCategory
from apps.projects.selectors.profitability import (
    AUTHORITATIVE_AVAILABLE,
    PENDING_SOURCE,
    calculate_margin_percent,
    calculate_profit,
    project_profitability,
)
from apps.projects.services import (
    activate_project,
    add_project_budget_line,
    create_draft_project,
    link_sales_order,
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
    WorkOrderOutput,
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
    WarehousePurchaseReceipt,
    WarehousePurchaseReceiptLine,
)

User = get_user_model()


def make_po(entity, project, vendor, grand_total=Decimal("0"), state=PurchaseOrderState.CONFIRMED):
    alloc = allocate_document_number(entity, "PURCHASE_ORDER", business_date=timezone.localdate())
    return PurchaseOrder.objects.create(
        legal_entity=entity,
        project=project,
        vendor=vendor,
        vendor_code_snapshot=vendor.code,
        vendor_name_snapshot=vendor.display_name,
        document_allocation=alloc,
        document_number=alloc.number,
        document_date=timezone.localdate(),
        state=state,
        grand_total=grand_total,
    )


def make_work_order(entity, project, vendor, state=WorkOrderState.APPROVED):
    alloc = allocate_document_number(entity, "WORK_ORDER", business_date=timezone.localdate())
    return WorkOrder.objects.create(
        legal_entity=entity,
        project=project,
        vendor=vendor,
        document_allocation=alloc,
        document_number=alloc.number,
        document_date=timezone.localdate(),
        state=state,
    )


def make_subcontract_receipt(entity, wo, vendor, state=SubcontractReceiptState.ACCEPTED):
    alloc = allocate_document_number(
        entity, "SUBCONTRACT_RECEIPT", business_date=timezone.localdate()
    )
    return SubcontractReceipt.objects.create(
        legal_entity=entity,
        document_allocation=alloc,
        document_number=alloc.number,
        work_order=wo,
        vendor=vendor,
        vendor_code_snapshot=vendor.code,
        vendor_name_snapshot=vendor.display_name,
        receipt_date=timezone.localdate(),
        state=state,
    )


def make_sales_invoice(entity, customer, so_line, amount=Decimal("10000000")):
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


def post_revenue_journal(entity, invoice, amount=Decimal("10000000")):
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
    entity = LegalEntity.objects.create(code="E9A", name="Entity 9A")
    user = User.objects.create_user("user9a@example.com", "password")
    customer = BusinessPartner.objects.create(
        legal_entity=entity, code="CUST-9A", display_name="Customer 9A"
    )
    PartnerRole.objects.create(partner=customer, role_type=PartnerRoleType.CUSTOMER)
    vendor = BusinessPartner.objects.create(
        legal_entity=entity, code="VEND-9A", display_name="Vendor 9A"
    )
    PartnerRole.objects.create(partner=vendor, role_type=PartnerRoleType.VENDOR)
    uom = UOM.objects.create(code="PCS9A", name="Pieces 9A", dimension="COUNT")
    item = Item.objects.create(
        legal_entity=entity, code="ITEM-9A", name="Item 9A", uom=uom, sales_eligible=True
    )
    warehouse = Warehouse.objects.create(legal_entity=entity, code="WH-9A", name="Warehouse 9A")
    category = PurchaseCategory.objects.create(
        legal_entity=entity,
        code="MAT-9A",
        name="Material Category",
        accounting_treatment=AccountingTreatment.INVENTORY,
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
        name="Phase 9A Project",
        start_date=timezone.localdate(),
        actor=user,
        idempotency_key="proj-9a-init",
    )
    activate_project(project, actor=user)

    return {
        "entity": entity,
        "user": user,
        "customer": customer,
        "vendor": vendor,
        "item": item,
        "warehouse": warehouse,
        "category": category,
        "project": project,
    }


@pytest.mark.django_db
def test_1_empty_project_unavailable_actual_and_forecast_remain_pending_source(project_data):
    project = project_data["project"]
    profitability = project_profitability(project)

    assert profitability.commercial_order_value == Decimal("0")
    assert profitability.commercial_invoice_source_value == Decimal("0")
    assert profitability.recognized_revenue == Decimal("0")

    assert profitability.committed_cost is None
    assert profitability.committed_cost_metric.availability == PENDING_SOURCE

    assert profitability.actual_cost is None
    assert profitability.actual_cost_metric.availability == PENDING_SOURCE
    assert profitability.actual_cost_metric.amount is None

    assert profitability.forecast_cost is None
    assert profitability.forecast_cost_metric.availability == PENDING_SOURCE

    assert profitability.projected_profit is None
    assert profitability.projected_margin_percent is None
    assert not profitability.data_complete

    assert (
        profitability.actual_categories[ProjectBudgetCategory.CPO_FEE].availability
        == PENDING_SOURCE
    )
    assert (
        profitability.actual_categories[ProjectBudgetCategory.SALES_FEE].availability
        == PENDING_SOURCE
    )


@pytest.mark.django_db
def test_2_commercial_sales_order_is_not_automatically_recognized_revenue(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    user = project_data["user"]
    customer = project_data["customer"]
    item = project_data["item"]

    so = create_draft_sales_order(
        legal_entity=entity, customer=customer, document_date=timezone.localdate(), actor=user
    )
    add_draft_line(so, actor=user, item=item, quantity=Decimal("5"), unit_price=Decimal("1000000"))
    confirm_sales_order(so, actor=user)
    link_sales_order(project, so, actor=user)

    profitability = project_profitability(project)

    assert profitability.commercial_order_value == Decimal("5000000.00")
    assert profitability.recognized_revenue != profitability.commercial_order_value
    assert profitability.recognized_revenue == Decimal("0")


@pytest.mark.django_db
def test_3_budget_header_and_lines_behavior_deterministic_and_explainable(project_data):
    project = project_data["project"]
    user = project_data["user"]

    add_project_budget_line(
        project,
        actor=user,
        reason="Project budget fabrics",
        category="MATERIAL",
        description="Fabrics",
        amount=Decimal("20000000"),
    )
    add_project_budget_line(
        project,
        actor=user,
        reason="Project budget sewing",
        category="LABOR",
        description="Sewing",
        amount=Decimal("10000000"),
    )
    project.refresh_from_db()

    profitability = project_profitability(project)

    assert profitability.budget_value == Decimal("30000000.00")
    assert profitability.budget.header_total == Decimal("30000000.00")
    assert profitability.budget.active_lines_total == Decimal("30000000.00")
    assert profitability.budget.status == "MATCH"
    assert profitability.budget.difference == Decimal("0.00")
    assert profitability.budget.line_count == 2


@pytest.mark.django_db
def test_4_budget_mismatch_is_visible_rather_than_silently_corrected(project_data):
    project = project_data["project"]
    user = project_data["user"]

    add_project_budget_line(
        project,
        actor=user,
        reason="Initial fabrics line",
        category="MATERIAL",
        description="Fabrics",
        amount=Decimal("20000000"),
    )
    Project.objects.filter(pk=project.pk).update(budget_total=Decimal("35000000"))
    project.refresh_from_db()

    profitability = project_profitability(project)

    assert profitability.budget.header_total == Decimal("35000000.00")
    assert profitability.budget.active_lines_total == Decimal("20000000.00")
    assert profitability.budget.status == "DIFFERENCE"
    assert profitability.budget.difference == Decimal("15000000.00")
    assert project.budget_total == Decimal("35000000.00")


@pytest.mark.django_db
def test_5_confirmed_procurement_commitment_included_authoritatively(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    vendor = project_data["vendor"]
    category = project_data["category"]
    item = project_data["item"]

    po = make_po(
        entity, project, vendor, grand_total=Decimal("12000000"), state=PurchaseOrderState.CONFIRMED
    )
    PurchaseOrderLine.objects.create(
        purchase_order=po,
        line_number=1,
        item=item,
        purchase_category=category,
        category_code_snapshot=category.code,
        category_name_snapshot=category.name,
        accounting_treatment_snapshot="INVENTORY",
        quantity=Decimal("12"),
        unit_price=Decimal("1000000"),
        line_total=Decimal("12000000"),
    )

    profitability = project_profitability(project)

    assert profitability.committed_cost == Decimal("12000000.00")
    assert profitability.committed_cost_metric.availability == AUTHORITATIVE_AVAILABLE
    assert profitability.committed_cost_metric.record_count == 1
    assert profitability.committed_categories[ProjectBudgetCategory.MATERIAL].amount == Decimal(
        "12000000.00"
    )


@pytest.mark.django_db
def test_6_partial_actualized_commitment_does_not_double_count_fulfilled_cost(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    vendor = project_data["vendor"]
    category = project_data["category"]
    item = project_data["item"]
    warehouse = project_data["warehouse"]

    po = make_po(
        entity, project, vendor, grand_total=Decimal("10000000"), state=PurchaseOrderState.CONFIRMED
    )
    po_line = PurchaseOrderLine.objects.create(
        purchase_order=po,
        line_number=1,
        item=item,
        purchase_category=category,
        category_code_snapshot=category.code,
        category_name_snapshot=category.name,
        accounting_treatment_snapshot="INVENTORY",
        quantity=Decimal("10"),
        unit_price=Decimal("1000000"),
        line_total=Decimal("10000000"),
    )

    # Warehouse receives 4 units via a POSTED receipt
    receipt = WarehousePurchaseReceipt.objects.create(
        legal_entity=entity,
        warehouse=warehouse,
        vendor=vendor,
        vendor_code_snapshot=vendor.code,
        vendor_name_snapshot=vendor.display_name,
        purchase_order=po,
        receipt_date=timezone.localdate(),
        state=WarehouseDocumentState.POSTED,
    )
    WarehousePurchaseReceiptLine.objects.create(
        receipt=receipt,
        purchase_order_line=po_line,
        item=item,
        item_code_snapshot=item.code,
        item_name_snapshot=item.name,
        uom_code_snapshot="PCS",
        purchase_category_code_snapshot=category.code,
        purchase_category_name_snapshot=category.name,
        accounting_treatment_snapshot="INVENTORY",
        vendor_id_snapshot=str(vendor.pk),
        quantity=Decimal("4"),
        unit_cost_snapshot=Decimal("1000000"),
        total_value_snapshot=Decimal("4000000"),
        source_key="REC-LINE-001",
        sequence=1,
    )

    profitability = project_profitability(project)

    # Remaining commitment is 6 units @ 1,000,000 = 6,000,000 (net of 4,000,000 received!)
    assert profitability.committed_cost == Decimal("6000000.00")


@pytest.mark.django_db
def test_7_authoritative_actual_cost_sources_with_explicit_lineage(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    warehouse = project_data["warehouse"]
    item = project_data["item"]
    vendor = project_data["vendor"]

    # 1. Warehouse Internal Consumption (MATERIAL)
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
        quantity=Decimal("2"),
        uom_code_snapshot="PCS",
        source_key="IC-LINE-001",
        sequence=1,
        unit_cost=Decimal("1500000"),
        total_value=Decimal("3000000"),
    )

    # 2. Purchasing Subcontract (MAKLUN)
    wo = make_work_order(entity, project, vendor, state=WorkOrderState.APPROVED)
    sub_receipt = make_subcontract_receipt(
        entity, wo, vendor, state=SubcontractReceiptState.ACCEPTED
    )
    SubcontractReceiptCostLine.objects.create(
        receipt=sub_receipt,
        line_number=1,
        cost_type=SubcontractCostType.SHARED_SERVICE,
        amount=Decimal("1200000"),
    )

    # 3. Production Labor (LABOR) via DAILY_WAGE
    output = WorkOrderOutput.objects.create(
        work_order=wo,
        line_number=1,
        item=item,
        item_code_snapshot=item.code,
        item_name_snapshot=item.name,
        uom_code_snapshot="PCS",
        target_quantity=Decimal("10"),
    )
    ProductionDirectExtraCost.objects.create(
        legal_entity=entity,
        work_order=wo,
        output=output,
        cost_date=timezone.localdate(),
        category=ProductionExtraCostCategory.DAILY_WAGE,
        description="Daily wage operator",
        amount=Decimal("800000"),
        state=ProductionEntryState.POSTED,
    )

    profitability = project_profitability(project)

    assert profitability.actual_cost == Decimal("5000000.00")
    assert profitability.actual_cost_metric.availability == AUTHORITATIVE_AVAILABLE
    assert profitability.actual_categories[ProjectBudgetCategory.MATERIAL].amount == Decimal(
        "3000000.00"
    )
    assert profitability.actual_categories[ProjectBudgetCategory.MAKLUN].amount == Decimal(
        "1200000.00"
    )
    assert profitability.actual_categories[ProjectBudgetCategory.LABOR].amount == Decimal(
        "800000.00"
    )


@pytest.mark.django_db
def test_8_cancelled_void_and_draft_sources_are_excluded(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    warehouse = project_data["warehouse"]
    item = project_data["item"]
    vendor = project_data["vendor"]

    # Draft consumption
    draft_c = InternalConsumption.objects.create(
        legal_entity=entity,
        warehouse=warehouse,
        project=project,
        transaction_date=timezone.localdate(),
        purpose="Draft consumption",
        reason="Test",
        state=WarehouseDocumentState.DRAFT,
    )
    InternalConsumptionLine.objects.create(
        consumption=draft_c,
        item=item,
        quantity=Decimal("5"),
        uom_code_snapshot="PCS",
        source_key="IC-DRAFT-001",
        sequence=1,
        unit_cost=Decimal("1000000"),
        total_value=Decimal("5000000"),
    )

    # Cancelled PO
    make_po(
        entity, project, vendor, grand_total=Decimal("9000000"), state=PurchaseOrderState.CANCELLED
    )

    profitability = project_profitability(project)

    assert profitability.actual_cost is None
    assert profitability.committed_cost is None


@pytest.mark.django_db
def test_9_reversal_correction_is_netted_out(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    vendor = project_data["vendor"]
    item = project_data["item"]

    wo = make_work_order(entity, project, vendor, state=WorkOrderState.APPROVED)
    output = WorkOrderOutput.objects.create(
        work_order=wo,
        line_number=1,
        item=item,
        item_code_snapshot=item.code,
        item_name_snapshot=item.name,
        uom_code_snapshot="PCS",
        target_quantity=Decimal("10"),
    )

    # Direct extra labor cost reversed
    ProductionDirectExtraCost.objects.create(
        legal_entity=entity,
        work_order=wo,
        output=output,
        cost_date=timezone.localdate(),
        category=ProductionExtraCostCategory.DAILY_WAGE,
        description="Reversed labor",
        amount=Decimal("2500000"),
        state=ProductionEntryState.POSTED,
        reversed_at=timezone.now(),
    )
    # Valid active labor cost
    ProductionDirectExtraCost.objects.create(
        legal_entity=entity,
        work_order=wo,
        output=output,
        cost_date=timezone.localdate(),
        category=ProductionExtraCostCategory.DAILY_WAGE,
        description="Active labor",
        amount=Decimal("1500000"),
        state=ProductionEntryState.POSTED,
        reversed_at=None,
    )

    profitability = project_profitability(project)

    assert profitability.actual_cost == Decimal("1500000.00")
    assert profitability.actual_categories[ProjectBudgetCategory.LABOR].amount == Decimal(
        "1500000.00"
    )


@pytest.mark.django_db
def test_10_missing_project_lineage_is_never_assigned_by_inference(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    warehouse = project_data["warehouse"]
    item = project_data["item"]
    vendor = project_data["vendor"]
    customer = project_data["customer"]
    user = project_data["user"]

    # Consumption without project
    c_unlinked = InternalConsumption.objects.create(
        legal_entity=entity,
        warehouse=warehouse,
        project=None,
        transaction_date=timezone.localdate(),
        purpose="General consumption",
        reason="General",
        state=WarehouseDocumentState.POSTED,
    )
    InternalConsumptionLine.objects.create(
        consumption=c_unlinked,
        item=item,
        quantity=Decimal("10"),
        uom_code_snapshot="PCS",
        source_key="IC-NO-PROJ",
        sequence=1,
        unit_cost=Decimal("1000000"),
        total_value=Decimal("10000000"),
    )

    # PO for same vendor and entity, but no project
    make_po(
        entity, None, vendor, grand_total=Decimal("8000000"), state=PurchaseOrderState.CONFIRMED
    )

    # Sales order for same customer, but not linked to project
    unlinked_so = create_draft_sales_order(
        legal_entity=entity, customer=customer, document_date=timezone.localdate(), actor=user
    )
    add_draft_line(
        unlinked_so, actor=user, item=item, quantity=Decimal("5"), unit_price=Decimal("1000000")
    )
    confirm_sales_order(unlinked_so, actor=user)

    profitability = project_profitability(project)

    assert profitability.commercial_order_value == Decimal("0")
    assert profitability.committed_cost is None
    assert profitability.actual_cost is None


@pytest.mark.django_db
def test_11_profit_and_margin_calculated_only_when_components_authoritative():
    assert calculate_profit(None, Decimal("1000")) is None
    assert calculate_profit(Decimal("1000"), None) is None
    assert calculate_margin_percent(None, Decimal("100")) is None
    assert calculate_margin_percent(Decimal("1000"), None) is None
    assert calculate_margin_percent(Decimal("0"), Decimal("100")) is None

    profit = calculate_profit(Decimal("10000000"), Decimal("8000000"))
    assert profit == Decimal("2000000")
    margin = calculate_margin_percent(Decimal("10000000"), profit)
    assert margin == Decimal("20.00")


@pytest.mark.django_db
def test_12_selector_read_safety_creates_zero_accounting_or_operational_records(project_data):
    project = project_data["project"]

    counts_before = {
        "JournalEntry": JournalEntry.objects.count(),
        "JournalLine": JournalLine.objects.count(),
        "ReceivableEntry": ReceivableEntry.objects.count(),
        "PayableEntry": PayableEntry.objects.count(),
        "Payment": Payment.objects.count(),
        "LiquidityEntry": LiquidityEntry.objects.count(),
        "StockMovement": StockMovement.objects.count(),
        "PurchaseOrder": PurchaseOrder.objects.count(),
        "WorkOrder": WorkOrder.objects.count(),
        "InternalConsumption": InternalConsumption.objects.count(),
    }

    _ = project_profitability(project)
    _ = project_profitability(project)

    counts_after = {
        "JournalEntry": JournalEntry.objects.count(),
        "JournalLine": JournalLine.objects.count(),
        "ReceivableEntry": ReceivableEntry.objects.count(),
        "PayableEntry": PayableEntry.objects.count(),
        "Payment": Payment.objects.count(),
        "LiquidityEntry": LiquidityEntry.objects.count(),
        "StockMovement": StockMovement.objects.count(),
        "PurchaseOrder": PurchaseOrder.objects.count(),
        "WorkOrder": WorkOrder.objects.count(),
        "InternalConsumption": InternalConsumption.objects.count(),
    }

    assert counts_before == counts_after


@pytest.mark.django_db
def test_13_recognized_revenue_original_journal_correct_positive_amount(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    user = project_data["user"]
    customer = project_data["customer"]
    item = project_data["item"]

    so = create_draft_sales_order(
        legal_entity=entity, customer=customer, document_date=timezone.localdate(), actor=user
    )
    so_line = add_draft_line(
        so, actor=user, item=item, quantity=Decimal("10"), unit_price=Decimal("1000000")
    )
    confirm_sales_order(so, actor=user)
    link_sales_order(project, so, actor=user)

    invoice = make_sales_invoice(entity, customer, so_line, amount=Decimal("10000000"))
    post_revenue_journal(entity, invoice, amount=Decimal("10000000"))

    profitability = project_profitability(project)

    assert profitability.recognized_revenue == Decimal("10000000")
    assert profitability.revenue_metric.availability == AUTHORITATIVE_AVAILABLE
    assert profitability.revenue_metric.amount == Decimal("10000000")
    assert profitability.revenue_metric.record_count == 1


@pytest.mark.django_db
def test_14_recognized_revenue_full_reversal_evaluates_to_zero(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    user = project_data["user"]
    customer = project_data["customer"]
    item = project_data["item"]

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

    # Reversal of the revenue journal
    reverse_journal(journal, actor=user, source_key=f"REV|{journal.pk}")

    profitability = project_profitability(project)

    # Net economic revenue is exactly 0, NOT -10,000,000
    assert profitability.recognized_revenue == Decimal("0")
    assert profitability.recognized_revenue != Decimal("-10000000")
    assert profitability.revenue_metric.availability == AUTHORITATIVE_AVAILABLE
    assert profitability.revenue_metric.record_count == 2


@pytest.mark.django_db
def test_15_unrelated_project_reversal_is_excluded(project_data):
    project1 = project_data["project"]
    entity = project_data["entity"]
    user = project_data["user"]
    customer = project_data["customer"]
    item = project_data["item"]

    # Create unrelated Project 2
    project2 = create_draft_project(
        legal_entity=entity,
        customer=customer,
        name="Project 2",
        start_date=timezone.localdate(),
        actor=user,
        idempotency_key="proj2-init",
    )
    activate_project(project2, actor=user)

    so2 = create_draft_sales_order(
        legal_entity=entity, customer=customer, document_date=timezone.localdate(), actor=user
    )
    so2_line = add_draft_line(
        so2, actor=user, item=item, quantity=Decimal("5"), unit_price=Decimal("2000000")
    )
    confirm_sales_order(so2, actor=user)
    link_sales_order(project2, so2, actor=user)

    invoice2 = make_sales_invoice(entity, customer, so2_line, amount=Decimal("10000000"))
    journal2 = post_revenue_journal(entity, invoice2, amount=Decimal("10000000"))
    reverse_journal(journal2, actor=user, source_key=f"REV|{journal2.pk}")

    # Project 1 (which has no invoices) must remain untouched and uninfluenced
    profitability1 = project_profitability(project1)

    assert profitability1.recognized_revenue == Decimal("0")
    assert profitability1.revenue_metric.record_count == 0


@pytest.mark.django_db
def test_16_maklun_commitment_without_explicit_lineage_is_pending_source_and_preserves_actual_cost(
    project_data,
):
    project = project_data["project"]
    entity = project_data["entity"]
    vendor = project_data["vendor"]
    category = project_data["category"]
    item = project_data["item"]

    # Two distinct confirmed PO commitments with MAKLUN in the same project
    po1 = make_po(
        entity, project, vendor, grand_total=Decimal("3000000"), state=PurchaseOrderState.CONFIRMED
    )
    PurchaseOrderLine.objects.create(
        purchase_order=po1,
        line_number=1,
        item=item,
        purchase_category=category,
        category_code_snapshot=category.code,
        category_name_snapshot=category.name,
        accounting_treatment_snapshot="MAKLUN",
        quantity=Decimal("3"),
        unit_price=Decimal("1000000"),
        line_total=Decimal("3000000"),
    )

    po2 = make_po(
        entity, project, vendor, grand_total=Decimal("2000000"), state=PurchaseOrderState.CONFIRMED
    )
    PurchaseOrderLine.objects.create(
        purchase_order=po2,
        line_number=1,
        item=item,
        purchase_category=category,
        category_code_snapshot=category.code,
        category_name_snapshot=category.name,
        accounting_treatment_snapshot="MAKLUN",
        quantity=Decimal("2"),
        unit_price=Decimal("1000000"),
        line_total=Decimal("2000000"),
    )

    # Subcontract work order on the project actualizes 2,000,000 via an accepted SubcontractReceipt
    wo = make_work_order(entity, project, vendor, state=WorkOrderState.APPROVED)
    sub_receipt = make_subcontract_receipt(
        entity, wo, vendor, state=SubcontractReceiptState.ACCEPTED
    )
    SubcontractReceiptCostLine.objects.create(
        receipt=sub_receipt,
        line_number=1,
        cost_type=SubcontractCostType.SHARED_SERVICE,
        amount=Decimal("2000000"),
    )

    profitability = project_profitability(project)

    # 1. Actual MAKLUN cost is authoritative via accepted
    # SubcontractReceiptCostLine -> WorkOrder -> Project
    assert profitability.actual_cost == Decimal("2000000.00")
    assert (
        profitability.actual_categories[ProjectBudgetCategory.MAKLUN].availability
        == AUTHORITATIVE_AVAILABLE
    )
    assert profitability.actual_categories[ProjectBudgetCategory.MAKLUN].amount == Decimal(
        "2000000.00"
    )

    # 2. Case B: Because no explicit persisted lineage connects PO lines to subcontract receipts,
    # MAKLUN remaining commitment is PENDING_SOURCE and does NOT guess-reduce PO totals
    assert (
        profitability.committed_categories[ProjectBudgetCategory.MAKLUN].availability
        == PENDING_SOURCE
    )
    assert profitability.committed_categories[ProjectBudgetCategory.MAKLUN].amount is None
    assert (
        profitability.committed_categories[ProjectBudgetCategory.MAKLUN].reason
        == "INSUFFICIENT_FULFILLMENT_LINEAGE_FOR_MAKLUN"
    )

    # 3. Overall committed cost preserves PENDING_SOURCE rather than a guessed number
    assert profitability.committed_cost is None
    assert profitability.committed_cost_metric.availability == PENDING_SOURCE
    assert (
        "INSUFFICIENT_FULFILLMENT_LINEAGE_FOR_MAKLUN" in profitability.committed_cost_metric.reason
    )


@pytest.mark.django_db
def test_17_non_inventory_treatment_with_insufficient_fulfillment_lineage_becomes_pending_source(
    project_data,
):
    project = project_data["project"]
    entity = project_data["entity"]
    vendor = project_data["vendor"]
    category = project_data["category"]
    item = project_data["item"]

    # Confirmed PO with EXPENSE line (non-INVENTORY treatment lacking fulfillment lineage)
    po = make_po(
        entity, project, vendor, grand_total=Decimal("4000000"), state=PurchaseOrderState.CONFIRMED
    )
    PurchaseOrderLine.objects.create(
        purchase_order=po,
        line_number=1,
        item=item,
        purchase_category=category,
        category_code_snapshot=category.code,
        category_name_snapshot=category.name,
        accounting_treatment_snapshot="EXPENSE",
        quantity=Decimal("4"),
        unit_price=Decimal("1000000"),
        line_total=Decimal("4000000"),
    )

    profitability = project_profitability(project)

    # Must be PENDING_SOURCE rather than guessing full line balance!
    assert profitability.committed_cost is None
    assert profitability.committed_cost_metric.availability == PENDING_SOURCE
    assert "INSUFFICIENT_FULFILLMENT_LINEAGE" in profitability.committed_cost_metric.reason
    assert (
        profitability.committed_categories[ProjectBudgetCategory.PURCHASING].availability
        == PENDING_SOURCE
    )
