"""Tests for Phase 9A2B: Project Profitability + Forecast UI + Readiness."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import UOM, Item
from apps.core.services.numbering import allocate_document_number, create_document_sequence
from apps.finance.models import (
    COAAccount,
    JournalEntry,
    JournalLine,
    JournalState,
    LiquidityEntry,
    Payment,
)
from apps.finance.services.posting import reverse_journal
from apps.organizations.models import (
    CostCenter,
    CostCenterCategory,
    LegalEntity,
    OrganizationMembership,
    Warehouse,
)
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.projects.models import (
    ProjectBudgetCategory,
    ProjectForecastLine,
    ProjectState,
)
from apps.projects.selectors.profitability import (
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
)
from apps.purchasing.models import (
    AccountingTreatment,
    PurchaseCategory,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderState,
    WorkOrder,
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
    entity = LegalEntity.objects.create(code="E9A2B", name="Entity 9A2B")
    user = User.objects.create_user("user9a2b@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity, is_active=True)
    # Grant default projects permissions
    for perm_codename in (
        "view_project",
        "add_project",
        "change_project",
        "activate_project",
        "hold_project",
        "complete_project",
        "cancel_project",
        "link_project_salesorder",
    ):
        perm = Permission.objects.get(codename=perm_codename)
        user.user_permissions.add(perm)

    customer = BusinessPartner.objects.create(
        legal_entity=entity, code="CUST-9A2B", display_name="Customer 9A2B"
    )
    PartnerRole.objects.create(partner=customer, role_type=PartnerRoleType.CUSTOMER)
    vendor = BusinessPartner.objects.create(
        legal_entity=entity, code="VEND-9A2B", display_name="Vendor 9A2B"
    )
    PartnerRole.objects.create(partner=vendor, role_type=PartnerRoleType.VENDOR)
    uom = UOM.objects.create(code="PCS9A2B", name="Pieces 9A2B", dimension="COUNT")
    item = Item.objects.create(
        legal_entity=entity, code="ITEM-9A2B", name="Item 9A2B", uom=uom, sales_eligible=True
    )
    warehouse = Warehouse.objects.create(legal_entity=entity, code="WH-9A2B", name="Warehouse 9A2B")
    category = PurchaseCategory.objects.create(
        legal_entity=entity,
        code="MAT-9A2B",
        name="Material Category",
        accounting_treatment=AccountingTreatment.INVENTORY,
    )
    cost_center = CostCenter.objects.create(
        legal_entity=entity,
        code="CC-9A2B",
        name="Cost Center 9A2B",
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
        name="Phase 9A2B Project",
        start_date=timezone.localdate(),
        actor=user,
        idempotency_key="proj-9a2b-init",
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
# 1. Budget MATCH + forecast: budget/forecast variance available.
# =========================================================================
@pytest.mark.django_db
def test_1_budget_match_plus_forecast_variance_available(project_data):
    project = project_data["project"]
    user = project_data["user"]

    add_project_budget_line(
        project,
        actor=user,
        category="MATERIAL",
        description="Fabrics",
        amount=Decimal("10000000"),
    )
    project.refresh_from_db()

    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Forecast",
        amount=Decimal("8000000"),
    )

    prof = project_profitability(project)
    assert prof.budget.status == "MATCH"
    assert prof.variance_budget_forecast == Decimal("2000000.00")


# =========================================================================
# 2. Budget DIFFERENCE: budget vs forecast is PENDING_SOURCE.
# =========================================================================
@pytest.mark.django_db
def test_2_budget_difference_budget_vs_forecast_is_pending_source(project_data):
    project = project_data["project"]
    user = project_data["user"]

    add_project_budget_line(
        project,
        actor=user,
        category="MATERIAL",
        description="Fabrics",
        amount=Decimal("10000000"),
    )
    # Manually simulate header out of sync (difference)
    project.budget_total = Decimal("15000000.00")
    project.save(update_fields=("budget_total",))

    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Forecast",
        amount=Decimal("8000000"),
    )

    prof = project_profitability(project)
    assert prof.budget.status == "DIFFERENCE"
    # When budget reconciliation is DIFFERENCE, variance is held as PENDING_SOURCE
    assert prof.variance_budget_forecast is None


# =========================================================================
# 3. Budget DIFFERENCE: budget vs actual is PENDING_SOURCE.
# =========================================================================
@pytest.mark.django_db
def test_3_budget_difference_budget_vs_actual_is_pending_source(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    user = project_data["user"]
    warehouse = project_data["warehouse"]
    item = project_data["item"]

    add_project_budget_line(
        project,
        actor=user,
        category="MATERIAL",
        description="Fabrics",
        amount=Decimal("10000000"),
    )
    project.budget_total = Decimal("15000000.00")
    project.save(update_fields=("budget_total",))

    # Add actual cost
    consumption = InternalConsumption.objects.create(
        legal_entity=entity,
        warehouse=warehouse,
        project=project,
        transaction_date=timezone.localdate(),
        purpose="Sampling",
        reason="Sampling",
        state=WarehouseDocumentState.POSTED,
    )
    InternalConsumptionLine.objects.create(
        consumption=consumption,
        item=item,
        quantity=Decimal("4"),
        uom_code_snapshot="PCS",
        source_key="IC-9A2B-001",
        sequence=1,
        unit_cost=Decimal("1000000"),
        total_value=Decimal("4000000"),
    )

    prof = project_profitability(project)
    assert prof.budget.status == "DIFFERENCE"
    assert prof.actual_cost == Decimal("4000000.00")
    # Budget vs actual must be PENDING_SOURCE due to reconciliation difference
    assert prof.variance_budget_actual is None


# =========================================================================
# 4. Header 0 + no active budget lines: authoritative zero budget.
# =========================================================================
@pytest.mark.django_db
def test_4_header_zero_no_active_budget_lines_authoritative_zero(project_data):
    project = project_data["project"]
    user = project_data["user"]
    assert project.budget_total == Decimal("0")
    assert project.budget_lines.count() == 0

    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Forecast",
        amount=Decimal("5000000"),
    )

    prof = project_profitability(project)
    assert prof.budget.status == "NO_LINES"
    # Budget is authoritative 0, so 0 - 5,000,000 = -5,000,000
    assert prof.variance_budget_forecast == Decimal("-5000000.00")


# =========================================================================
# 5. PENDING_SOURCE renders explicitly and not as Rp0.
# =========================================================================
@pytest.mark.django_db
def test_5_pending_source_renders_explicitly_and_not_as_rp0(project_data):
    project = project_data["project"]
    user = project_data["user"]
    client = Client()
    client.force_login(user)

    url = reverse("projects:detail", kwargs={"pk": project.pk})
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    # Must contain explicit PENDING SOURCE badge
    assert "PENDING SOURCE" in content
    # Forecast cost has no lines, so it is PENDING SOURCE
    prof = response.context["profitability"]
    assert prof.forecast_cost is None
    assert prof.committed_cost is None


# =========================================================================
# 6. Authoritative zero renders as zero and not PENDING_SOURCE.
# =========================================================================
@pytest.mark.django_db
def test_6_authoritative_zero_renders_as_zero_and_not_pending_source(project_data):
    project = project_data["project"]
    user = project_data["user"]
    client = Client()
    client.force_login(user)

    url = reverse("projects:detail", kwargs={"pk": project.pk})
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    # Recognized Revenue with zero invoices is authoritative 0
    prof = response.context["profitability"]
    assert prof.recognized_revenue == Decimal("0")
    assert "IDR 0" in content


# =========================================================================
# 7. Project detail shows all profitability facts.
# =========================================================================
@pytest.mark.django_db
def test_7_project_detail_shows_all_profitability_facts(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    user = project_data["user"]
    customer = project_data["customer"]
    item = project_data["item"]

    project = activate_project(project, actor=user)

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

    add_project_forecast_line(
        project,
        actor=user,
        reason="Initial forecast",
        category=ProjectBudgetCategory.MATERIAL,
        description="Forecast total cost",
        amount=Decimal("7000000"),
    )

    client = Client()
    client.force_login(user)
    url = reverse("projects:detail", kwargs={"pk": project.pk})
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    assert "Commercial Sales Order Value" in content
    assert "Commercial Invoice Source Value" in content
    assert "Recognized Revenue" in content
    assert "Projected Profit" in content
    assert "Projected Margin %" in content
    assert "10000000" in content  # Revenue
    assert "7000000" in content  # Forecast
    assert "3000000" in content  # Projected profit (10M - 7M)


# =========================================================================
# 8. Category breakdown distinguishes pending vs available.
# =========================================================================
@pytest.mark.django_db
def test_8_category_breakdown_distinguishes_pending_vs_available(project_data):
    project = project_data["project"]
    user = project_data["user"]

    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Fabrics",
        amount=Decimal("6000000"),
    )

    client = Client()
    client.force_login(user)
    url = reverse("projects:detail", kwargs={"pk": project.pk})
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    assert "Category Cost Breakdown" in content
    assert "MATERIAL" in content
    assert "CPO_FEE" in content
    assert "SALES_FEE" in content
    assert "6000000" in content


# =========================================================================
# 9. Forecast list displays active lines.
# =========================================================================
@pytest.mark.django_db
def test_9_forecast_list_displays_active_lines(project_data):
    project = project_data["project"]
    user = project_data["user"]

    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Premium Silk",
        amount=Decimal("9000000"),
        is_active=True,
    )
    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.LABOR,
        description="Inactive draft labor",
        amount=Decimal("4000000"),
        is_active=False,
    )

    client = Client()
    client.force_login(user)
    url = reverse("projects:detail", kwargs={"pk": project.pk})
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    assert "Premium Silk" in content
    assert "Active" in content
    assert "Inactive draft labor" in content
    assert "Inactive" in content


# =========================================================================
# 10. Forecast add allowed for DRAFT without reason.
# =========================================================================
@pytest.mark.django_db
def test_10_forecast_add_allowed_for_draft_without_reason(project_data):
    project = project_data["project"]
    user = project_data["user"]
    assert project.state == ProjectState.DRAFT

    client = Client()
    client.force_login(user)
    url = reverse("projects:forecast-add", kwargs={"pk": project.pk})

    response = client.post(
        url,
        {
            "category": "MATERIAL",
            "description": "Initial draft estimation",
            "amount": "8000000",
            "reason": "",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    assert ProjectForecastLine.objects.filter(project=project, amount=Decimal("8000000")).exists()


# =========================================================================
# 11. ACTIVE forecast add requires reason.
# =========================================================================
@pytest.mark.django_db
def test_11_active_forecast_add_requires_reason(project_data):
    project = project_data["project"]
    user = project_data["user"]
    project = activate_project(project, actor=user)

    client = Client()
    client.force_login(user)
    url = reverse("projects:forecast-add", kwargs={"pk": project.pk})

    # Empty reason fails
    res_fail = client.post(
        url,
        {
            "category": "MATERIAL",
            "description": "Active estimate",
            "amount": "5000000",
            "reason": "",
            "is_active": "on",
        },
    )
    assert res_fail.status_code == 200
    assert not ProjectForecastLine.objects.filter(
        project=project, amount=Decimal("5000000")
    ).exists()

    # With reason succeeds
    res_ok = client.post(
        url,
        {
            "category": "MATERIAL",
            "description": "Active estimate",
            "amount": "5000000",
            "reason": "Updated scope from customer",
            "is_active": "on",
        },
    )
    assert res_ok.status_code == 302
    assert ProjectForecastLine.objects.filter(project=project, amount=Decimal("5000000")).exists()


# =========================================================================
# 12. ON_HOLD forecast add requires reason.
# =========================================================================
@pytest.mark.django_db
def test_12_on_hold_forecast_add_requires_reason(project_data):
    project = project_data["project"]
    user = project_data["user"]
    project = activate_project(project, actor=user)
    project = hold_project(project, actor=user, reason="Hold for review")

    client = Client()
    client.force_login(user)
    url = reverse("projects:forecast-add", kwargs={"pk": project.pk})

    # Empty reason fails
    res_fail = client.post(
        url,
        {
            "category": "LABOR",
            "description": "Hold estimate",
            "amount": "3000000",
            "reason": "",
            "is_active": "on",
        },
    )
    assert res_fail.status_code == 200
    assert not ProjectForecastLine.objects.filter(
        project=project, amount=Decimal("3000000")
    ).exists()

    # With reason succeeds
    res_ok = client.post(
        url,
        {
            "category": "LABOR",
            "description": "Hold estimate",
            "amount": "3000000",
            "reason": "Adjustment during hold",
            "is_active": "on",
        },
    )
    assert res_ok.status_code == 302
    assert ProjectForecastLine.objects.filter(project=project, amount=Decimal("3000000")).exists()


# =========================================================================
# 13. Forecast update calls service and requires reason.
# =========================================================================
@pytest.mark.django_db
def test_13_forecast_update_requires_reason(project_data):
    project = project_data["project"]
    user = project_data["user"]
    line = add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Initial",
        amount=Decimal("5000000"),
    )

    client = Client()
    client.force_login(user)
    url = reverse("projects:forecast-edit", kwargs={"pk": project.pk, "line_pk": line.pk})

    # Empty reason fails
    res_fail = client.post(
        url,
        {
            "category": "MATERIAL",
            "description": "Updated",
            "amount": "7000000",
            "reason": "",
            "is_active": "on",
        },
    )
    assert res_fail.status_code == 200
    line.refresh_from_db()
    assert line.amount == Decimal("5000000.00")

    # With reason succeeds
    res_ok = client.post(
        url,
        {
            "category": "MATERIAL",
            "description": "Updated",
            "amount": "7000000",
            "reason": "Revision based on engineering review",
            "is_active": "on",
        },
    )
    assert res_ok.status_code == 302
    line.refresh_from_db()
    assert line.amount == Decimal("7000000.00")


# =========================================================================
# 14. Forecast remove requires reason.
# =========================================================================
@pytest.mark.django_db
def test_14_forecast_remove_requires_reason(project_data):
    project = project_data["project"]
    user = project_data["user"]
    line = add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="To remove",
        amount=Decimal("2000000"),
    )

    client = Client()
    client.force_login(user)
    url = reverse("projects:forecast-remove", kwargs={"pk": project.pk, "line_pk": line.pk})

    # Empty reason fails
    res_fail = client.post(url, {"reason": ""})
    assert res_fail.status_code == 200
    assert ProjectForecastLine.objects.filter(pk=line.pk).exists()

    # With reason succeeds
    res_ok = client.post(url, {"reason": "Cancelled line by PM"})
    assert res_ok.status_code == 302
    assert not ProjectForecastLine.objects.filter(pk=line.pk).exists()


# =========================================================================
# 15. COMPLETED mutation blocked.
# =========================================================================
@pytest.mark.django_db
def test_15_completed_mutation_blocked(project_data):
    project = project_data["project"]
    user = project_data["user"]
    add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Base",
        amount=Decimal("5000000"),
    )
    project = activate_project(project, actor=user)
    project = complete_project(project, actor=user, reason="Done")

    client = Client()
    client.force_login(user)

    add_url = reverse("projects:forecast-add", kwargs={"pk": project.pk})
    res = client.post(
        add_url,
        {"category": "LABOR", "description": "Post", "amount": "1000000", "reason": "Test"},
    )
    assert res.status_code == 200
    assert not ProjectForecastLine.objects.filter(description="Post").exists()


# =========================================================================
# 16. CANCELLED mutation blocked.
# =========================================================================
@pytest.mark.django_db
def test_16_cancelled_mutation_blocked(project_data):
    project = project_data["project"]
    user = project_data["user"]
    project = cancel_project(project, actor=user, reason="Cancelled")

    client = Client()
    client.force_login(user)

    add_url = reverse("projects:forecast-add", kwargs={"pk": project.pk})
    res = client.post(
        add_url,
        {"category": "LABOR", "description": "Post", "amount": "1000000", "reason": "Test"},
    )
    assert res.status_code == 200
    assert not ProjectForecastLine.objects.filter(description="Post").exists()


# =========================================================================
# 17. GET forecast endpoints create zero writes.
# =========================================================================
@pytest.mark.django_db
def test_17_get_forecast_endpoints_create_zero_writes(project_data):
    project = project_data["project"]
    user = project_data["user"]
    line = add_project_forecast_line(
        project,
        actor=user,
        category=ProjectBudgetCategory.MATERIAL,
        description="Test",
        amount=Decimal("1000000"),
    )

    client = Client()
    client.force_login(user)

    counts_before = ProjectForecastLine.objects.count()

    res1 = client.get(reverse("projects:forecast-add", kwargs={"pk": project.pk}))
    assert res1.status_code == 200

    res2 = client.get(
        reverse("projects:forecast-edit", kwargs={"pk": project.pk, "line_pk": line.pk})
    )
    assert res2.status_code == 200

    res3 = client.get(
        reverse("projects:forecast-remove", kwargs={"pk": project.pk, "line_pk": line.pk})
    )
    assert res3.status_code == 200

    assert ProjectForecastLine.objects.count() == counts_before


# =========================================================================
# 18. Project detail GET creates zero operational or accounting records.
# =========================================================================
@pytest.mark.django_db
def test_18_project_detail_get_creates_zero_records(project_data):
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
    }

    client = Client()
    client.force_login(user)
    response = client.get(reverse("projects:detail", kwargs={"pk": project.pk}))
    assert response.status_code == 200

    counts_after = {
        "JournalEntry": JournalEntry.objects.count(),
        "JournalLine": JournalLine.objects.count(),
        "Payment": Payment.objects.count(),
        "LiquidityEntry": LiquidityEntry.objects.count(),
        "StockMovement": StockMovement.objects.count(),
        "PurchaseOrder": PurchaseOrder.objects.count(),
        "WorkOrder": WorkOrder.objects.count(),
    }

    assert counts_before == counts_after


# =========================================================================
# 19. Permission-denied user cannot mutate forecast.
# =========================================================================
@pytest.mark.django_db
def test_19_permission_denied_user_cannot_mutate_forecast(project_data):
    project = project_data["project"]
    # User without change_project permission
    unauthorized = User.objects.create_user("unauth@example.com", "password")
    OrganizationMembership.objects.create(
        user=unauthorized, legal_entity=project_data["entity"], is_active=True
    )
    unauthorized.user_permissions.add(Permission.objects.get(codename="view_project"))

    client = Client()
    client.force_login(unauthorized)

    url = reverse("projects:forecast-add", kwargs={"pk": project.pk})
    response = client.post(
        url,
        {
            "category": "MATERIAL",
            "description": "Unauthorized",
            "amount": "1000000",
            "reason": "Test",
        },
    )
    assert response.status_code == 403


# =========================================================================
# 20. Existing 9A1 and 9A2A contracts remain green.
# =========================================================================
@pytest.mark.django_db
def test_20_existing_9a1_and_9a2a_contracts_remain_green(project_data):
    project = project_data["project"]
    entity = project_data["entity"]
    user = project_data["user"]
    customer = project_data["customer"]
    vendor = project_data["vendor"]
    category = project_data["category"]
    item = project_data["item"]

    project = activate_project(project, actor=user)

    # 1. Revenue reversal check
    so = create_draft_sales_order(
        legal_entity=entity, customer=customer, document_date=timezone.localdate(), actor=user
    )
    so_line = add_draft_line(
        so, actor=user, item=item, quantity=Decimal("5"), unit_price=Decimal("2000000")
    )
    confirm_sales_order(so, actor=user)
    link_sales_order(project, so, actor=user)

    invoice = make_sales_invoice(entity, customer, so_line, amount=Decimal("10000000"))
    journal = post_revenue_journal(entity, invoice, amount=Decimal("10000000"))
    reverse_journal(journal, actor=user, source_key=f"REV9A2B|{journal.pk}")

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
        document_number="PO-9A2B-MAK",
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

    prof = project_profitability(project)
    assert prof.recognized_revenue == Decimal("0")
    assert prof.committed_categories[ProjectBudgetCategory.MAKLUN].availability == PENDING_SOURCE
    assert prof.committed_cost is None
