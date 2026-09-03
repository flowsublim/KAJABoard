"""Project profitability read contract and selectors for Phase 9A1."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, Sum

from apps.finance.models import JournalEntry, JournalLine, JournalState
from apps.production.models import (
    ProductionDirectExtraCost,
    ProductionEntryState,
    ProductionExtraCostCategory,
    ProductionLaborCost,
)
from apps.projects.models import Project, ProjectBudgetCategory
from apps.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderState,
    SubcontractReceiptCostLine,
    SubcontractReceiptState,
)
from apps.sales.models import (
    SalesInvoiceDocumentKind,
    SalesInvoiceLine,
    SalesInvoiceState,
    SalesOrder,
    SalesOrderState,
)
from apps.warehouse.models import (
    InternalConsumption,
    WarehouseDocumentState,
)

AUTHORITATIVE_AVAILABLE = "AUTHORITATIVE_AVAILABLE"
PENDING_SOURCE = "PENDING_SOURCE"


@dataclass(frozen=True)
class MetricComponent:
    amount: Decimal | None
    availability: str
    domain: str
    record_count: int
    source_model: str
    reason: str = ""


@dataclass(frozen=True)
class BudgetReconciliation:
    header_total: Decimal
    active_lines_total: Decimal
    status: str  # "MATCH", "DIFFERENCE", "NO_LINES"
    line_count: int
    difference: Decimal


@dataclass(frozen=True)
class CostCategoryItem:
    category: str
    amount: Decimal | None
    availability: str
    domain: str
    record_count: int
    reason: str = ""


@dataclass(frozen=True)
class ProjectProfitability:
    commercial_order_value: Decimal
    commercial_invoice_source_value: Decimal
    budget_value: Decimal
    committed_cost: Decimal | None
    actual_cost: Decimal | None
    forecast_cost: Decimal | None
    projected_profit: Decimal | None
    projected_margin_percent: Decimal | None
    data_complete: bool
    missing_sources: tuple[str, ...]
    recognized_revenue: Decimal | None
    budget: BudgetReconciliation
    revenue_metric: MetricComponent
    commercial_order_metric: MetricComponent
    commercial_invoice_metric: MetricComponent
    committed_cost_metric: MetricComponent
    actual_cost_metric: MetricComponent
    forecast_cost_metric: MetricComponent
    actual_categories: dict[str, CostCategoryItem]
    committed_categories: dict[str, CostCategoryItem]
    forecast_categories: dict[str, CostCategoryItem] = field(default_factory=dict)
    forecast_line_ids: tuple[str, ...] = ()
    variance_budget_forecast: Decimal | None = None
    variance_budget_actual: Decimal | None = None
    remaining_to_forecast: Decimal | None = None
    current_cost_exposure: Decimal | None = None


def calculate_profit(revenue: Decimal | None, total_cost: Decimal | None) -> Decimal | None:
    if revenue is None or total_cost is None:
        return None
    return revenue - total_cost


def calculate_margin_percent(revenue: Decimal | None, profit: Decimal | None) -> Decimal | None:
    if revenue is None or profit is None or revenue <= Decimal("0"):
        return None
    return ((profit / revenue) * Decimal("100")).quantize(Decimal("0.01"))


def project_profitability(project: Project) -> ProjectProfitability:
    """Project profitability read contract. Read-only, zero side-effects."""
    # 1. Commercial Sales Orders
    linked_orders = SalesOrder.objects.filter(
        project_link__project=project,
        state__in=(SalesOrderState.CONFIRMED, SalesOrderState.ON_HOLD, SalesOrderState.CLOSED),
    )
    commercial_order_count = linked_orders.count()
    commercial_order_value = linked_orders.aggregate(v=Sum("grand_total"))["v"] or Decimal("0")
    commercial_order_metric = MetricComponent(
        amount=commercial_order_value,
        availability=AUTHORITATIVE_AVAILABLE,
        domain="sales",
        record_count=commercial_order_count,
        source_model="SalesOrder",
        reason="CONFIRMED_PROJECT_SALES_ORDERS",
    )

    # 2. Commercial Invoices
    invoice_lines = SalesInvoiceLine.objects.filter(
        source_sales_order_line__sales_order__project_link__project=project,
        sales_invoice__state=SalesInvoiceState.CONFIRMED,
        sales_invoice__document_kind=SalesInvoiceDocumentKind.INVOICE,
    )
    commercial_invoice_count = invoice_lines.values("sales_invoice_id").distinct().count()
    commercial_invoice_source_value = invoice_lines.values("sales_invoice_id").distinct().aggregate(
        v=Sum("sales_invoice__grand_total")
    )["v"] or Decimal("0")
    commercial_invoice_metric = MetricComponent(
        amount=commercial_invoice_source_value,
        availability=AUTHORITATIVE_AVAILABLE,
        domain="sales",
        record_count=commercial_invoice_count,
        source_model="SalesInvoice",
        reason="CONFIRMED_COMMERCIAL_SALES_INVOICES",
    )

    # 3. Recognized Revenue (Finance Posted & Reversals Netted)
    invoice_ids = list(invoice_lines.values_list("sales_invoice_id", flat=True).distinct())
    if not invoice_ids:
        recognized_revenue = Decimal("0")
        revenue_metric = MetricComponent(
            amount=Decimal("0"),
            availability=AUTHORITATIVE_AVAILABLE,
            domain="finance",
            record_count=0,
            source_model="JournalEntry",
            reason="NO_PROJECT_INVOICES_ISSUED",
        )
    else:
        journals = JournalEntry.objects.filter(
            source_module="SALES",
            source_document_type="SalesInvoice",
            source_document_id__in=[str(pk) for pk in invoice_ids],
        )
        posted_or_reversed_journals = journals.filter(
            state__in=(JournalState.POSTED, JournalState.REVERSED)
        )
        recorded_invoice_ids = set(
            posted_or_reversed_journals.values_list("source_document_id", flat=True)
        )
        unposted_ids = set(str(pk) for pk in invoice_ids) - recorded_invoice_ids
        if unposted_ids:
            recognized_revenue = None
            revenue_metric = MetricComponent(
                amount=None,
                availability=PENDING_SOURCE,
                domain="finance",
                record_count=len(unposted_ids),
                source_model="JournalEntry",
                reason="CONFIRMED_INVOICES_AWAITING_FINANCE_POSTING",
            )
        else:
            revenue_lines = JournalLine.objects.filter(
                journal__in=posted_or_reversed_journals,
                line_role="REVENUE",
            )
            credit_sum = revenue_lines.aggregate(v=Sum("credit"))["v"] or Decimal("0")
            debit_sum = revenue_lines.aggregate(v=Sum("debit"))["v"] or Decimal("0")
            recognized_revenue = credit_sum - debit_sum
            revenue_metric = MetricComponent(
                amount=recognized_revenue,
                availability=AUTHORITATIVE_AVAILABLE,
                domain="finance",
                record_count=posted_or_reversed_journals.count(),
                source_model="JournalEntry",
                reason="FINANCE_POSTED_REVENUE_JOURNALS_NET_OF_REVERSALS",
            )

    # 4. Budget Reconciliation
    active_lines = project.budget_lines.filter(is_active=True)
    line_count = active_lines.count()
    active_lines_total = active_lines.aggregate(v=Sum("amount"))["v"] or Decimal("0")
    header_total = project.budget_total
    difference = header_total - active_lines_total

    if line_count == 0:
        budget_status = "NO_LINES"
    elif difference == Decimal("0"):
        budget_status = "MATCH"
    else:
        budget_status = "DIFFERENCE"

    budget_reconciliation = BudgetReconciliation(
        header_total=header_total,
        active_lines_total=active_lines_total,
        status=budget_status,
        line_count=line_count,
        difference=difference,
    )

    # 5. Committed Cost (Purchasing — Non-Inventory Actualization & Treatment Authority)
    committed_orders = PurchaseOrder.objects.filter(
        project=project,
        state=PurchaseOrderState.CONFIRMED,
    )
    committed_categories: dict[str, CostCategoryItem] = {}
    for cat in ProjectBudgetCategory.values:
        committed_categories[cat] = CostCategoryItem(
            category=cat,
            amount=None,
            availability=PENDING_SOURCE,
            domain="purchasing",
            record_count=0,
            reason="NO_COMMITTED_PURCHASE_ORDERS",
        )

    if not committed_orders.exists():
        committed_cost = None
        committed_cost_metric = MetricComponent(
            amount=None,
            availability=PENDING_SOURCE,
            domain="purchasing",
            record_count=0,
            source_model="PurchaseOrder",
            reason="NO_COMMITTED_PURCHASE_ORDERS",
        )
    else:
        has_unsupported_treatment = False
        unsupported_treatment_reasons: list[str] = []
        total_committed = Decimal("0")
        total_lines_count = 0
        cat_totals: dict[str, Decimal] = {}
        cat_counts: dict[str, int] = {}

        for order in committed_orders.prefetch_related("lines__warehouse_receipt_lines__receipt"):
            for po_line in order.lines.all():
                total_lines_count += 1
                treatment = po_line.accounting_treatment_snapshot

                if treatment == "INVENTORY":
                    received_qty = sum(
                        r_line.quantity
                        for r_line in po_line.warehouse_receipt_lines.all()
                        if r_line.receipt.state == WarehouseDocumentState.POSTED
                    )
                    rem_qty = max(Decimal("0"), po_line.quantity - received_qty)
                    rem_amount = (rem_qty * po_line.unit_price).quantize(Decimal("0.01"))
                    total_committed += rem_amount
                    target_cat = ProjectBudgetCategory.MATERIAL
                    cat_totals[target_cat] = cat_totals.get(target_cat, Decimal("0")) + rem_amount
                    cat_counts[target_cat] = cat_counts.get(target_cat, 0) + 1

                elif treatment == "MAKLUN":
                    # Case B: No explicit persisted lineage exists between PurchaseOrderLine
                    # and SubcontractReceipt in the repository.
                    has_unsupported_treatment = True
                    reason_code = "INSUFFICIENT_FULFILLMENT_LINEAGE_FOR_MAKLUN"
                    if reason_code not in unsupported_treatment_reasons:
                        unsupported_treatment_reasons.append(reason_code)
                    target_cat = ProjectBudgetCategory.MAKLUN
                    cat_counts[target_cat] = cat_counts.get(target_cat, 0) + 1
                    committed_categories[target_cat] = CostCategoryItem(
                        category=target_cat,
                        amount=None,
                        availability=PENDING_SOURCE,
                        domain="purchasing",
                        record_count=cat_counts[target_cat],
                        reason=reason_code,
                    )

                else:
                    # EXPENSE, SERVICE, ASSET lack authoritative fulfillment
                    # lineage in the current repository
                    has_unsupported_treatment = True
                    reason_code = f"INSUFFICIENT_FULFILLMENT_LINEAGE_FOR_{treatment}"
                    if reason_code not in unsupported_treatment_reasons:
                        unsupported_treatment_reasons.append(reason_code)
                    target_cat = ProjectBudgetCategory.PURCHASING
                    cat_counts[target_cat] = cat_counts.get(target_cat, 0) + 1
                    committed_categories[target_cat] = CostCategoryItem(
                        category=target_cat,
                        amount=None,
                        availability=PENDING_SOURCE,
                        domain="purchasing",
                        record_count=cat_counts[target_cat],
                        reason=reason_code,
                    )

        if ProjectBudgetCategory.MATERIAL in cat_totals:
            committed_categories[ProjectBudgetCategory.MATERIAL] = CostCategoryItem(
                category=ProjectBudgetCategory.MATERIAL,
                amount=cat_totals[ProjectBudgetCategory.MATERIAL],
                availability=AUTHORITATIVE_AVAILABLE,
                domain="purchasing",
                record_count=cat_counts.get(ProjectBudgetCategory.MATERIAL, 0),
                reason="CONFIRMED_PURCHASE_ORDER_LINES_NET_OF_RECEIPTS",
            )

        if has_unsupported_treatment:
            # If any confirmed line lacks authoritative fulfillment lineage,
            # overall committed cost is PENDING_SOURCE
            committed_cost = None
            committed_cost_metric = MetricComponent(
                amount=None,
                availability=PENDING_SOURCE,
                domain="purchasing",
                record_count=total_lines_count,
                source_model="PurchaseOrderLine",
                reason="; ".join(unsupported_treatment_reasons),
            )
        else:
            committed_cost = total_committed
            committed_cost_metric = MetricComponent(
                amount=committed_cost,
                availability=AUTHORITATIVE_AVAILABLE,
                domain="purchasing",
                record_count=total_lines_count,
                source_model="PurchaseOrderLine",
                reason="CONFIRMED_PURCHASE_ORDER_COMMITMENTS_NET_OF_FULFILLMENT",
            )

    # 6. Actual Cost (Warehouse, Purchasing, Production)
    actual_categories: dict[str, CostCategoryItem] = {}
    for cat in ProjectBudgetCategory.values:
        actual_categories[cat] = CostCategoryItem(
            category=cat,
            amount=None,
            availability=PENDING_SOURCE,
            domain="unassigned",
            record_count=0,
            reason=f"NO_AUTHORITATIVE_SOURCE_FOR_{cat}",
        )

    actual_categories[ProjectBudgetCategory.CPO_FEE] = CostCategoryItem(
        category=ProjectBudgetCategory.CPO_FEE,
        amount=None,
        availability=PENDING_SOURCE,
        domain="incentives",
        record_count=0,
        reason="GENERIC_INCENTIVE_ENGINE_DEFERRED_TO_PHASE_9B",
    )
    actual_categories[ProjectBudgetCategory.SALES_FEE] = CostCategoryItem(
        category=ProjectBudgetCategory.SALES_FEE,
        amount=None,
        availability=PENDING_SOURCE,
        domain="incentives",
        record_count=0,
        reason="GENERIC_INCENTIVE_ENGINE_DEFERRED_TO_PHASE_9B",
    )

    # Source 1: Warehouse Internal Consumption (MATERIAL)
    consumptions = InternalConsumption.objects.filter(
        project=project,
        state=WarehouseDocumentState.POSTED,
    ).prefetch_related("lines")
    has_consumption = consumptions.exists()
    consumption_has_unvalued = False
    consumption_total = Decimal("0")
    consumption_line_count = 0
    if has_consumption:
        for c in consumptions:
            for line in c.lines.all():
                consumption_line_count += 1
                if line.total_value is None:
                    consumption_has_unvalued = True
                else:
                    consumption_total += line.total_value

    if has_consumption:
        if consumption_has_unvalued:
            actual_categories[ProjectBudgetCategory.MATERIAL] = CostCategoryItem(
                category=ProjectBudgetCategory.MATERIAL,
                amount=None,
                availability=PENDING_SOURCE,
                domain="warehouse",
                record_count=consumption_line_count,
                reason="UNVALUED_INTERNAL_CONSUMPTION_LINES",
            )
        else:
            actual_categories[ProjectBudgetCategory.MATERIAL] = CostCategoryItem(
                category=ProjectBudgetCategory.MATERIAL,
                amount=consumption_total,
                availability=AUTHORITATIVE_AVAILABLE,
                domain="warehouse",
                record_count=consumption_line_count,
                reason="POSTED_INTERNAL_CONSUMPTION_LINES",
            )

    # Source 2: Purchasing Subcontract Receipt Cost Lines (MAKLUN)
    subcontract_cost_lines = SubcontractReceiptCostLine.objects.filter(
        receipt__work_order__project=project,
        receipt__state=SubcontractReceiptState.ACCEPTED,
    )
    if subcontract_cost_lines.exists():
        maklun_total = subcontract_cost_lines.aggregate(v=Sum("amount"))["v"] or Decimal("0")
        actual_categories[ProjectBudgetCategory.MAKLUN] = CostCategoryItem(
            category=ProjectBudgetCategory.MAKLUN,
            amount=maklun_total,
            availability=AUTHORITATIVE_AVAILABLE,
            domain="purchasing",
            record_count=subcontract_cost_lines.count(),
            reason="ACCEPTED_SUBCONTRACT_RECEIPT_COST_LINES",
        )

    # Source 3: Production Direct Labor (LABOR)
    labor_costs = ProductionLaborCost.objects.filter(
        work_order__project=project,
        reversed_at__isnull=True,
    )
    daily_wage_costs = ProductionDirectExtraCost.objects.filter(
        work_order__project=project,
        category=ProductionExtraCostCategory.DAILY_WAGE,
        state=ProductionEntryState.POSTED,
        reversed_at__isnull=True,
    )
    labor_count = labor_costs.count() + daily_wage_costs.count()
    if labor_count > 0:
        labor_total = (labor_costs.aggregate(v=Sum("amount"))["v"] or Decimal("0")) + (
            daily_wage_costs.aggregate(v=Sum("amount"))["v"] or Decimal("0")
        )
        actual_categories[ProjectBudgetCategory.LABOR] = CostCategoryItem(
            category=ProjectBudgetCategory.LABOR,
            amount=labor_total,
            availability=AUTHORITATIVE_AVAILABLE,
            domain="production",
            record_count=labor_count,
            reason="POSTED_PRODUCTION_LABOR_AND_DAILY_WAGES",
        )

    # Source 4: Production Direct Extra Cost (DIRECT_OVERHEAD)
    extra_costs = ProductionDirectExtraCost.objects.filter(
        work_order__project=project,
        state=ProductionEntryState.POSTED,
        reversed_at__isnull=True,
    ).exclude(category=ProductionExtraCostCategory.DAILY_WAGE)
    if extra_costs.exists():
        extra_total = extra_costs.aggregate(v=Sum("amount"))["v"] or Decimal("0")
        actual_categories[ProjectBudgetCategory.DIRECT_OVERHEAD] = CostCategoryItem(
            category=ProjectBudgetCategory.DIRECT_OVERHEAD,
            amount=extra_total,
            availability=AUTHORITATIVE_AVAILABLE,
            domain="production",
            record_count=extra_costs.count(),
            reason="POSTED_PRODUCTION_DIRECT_EXTRA_COSTS",
        )

    # Aggregate Actual Cost
    authoritative_actual_cats = [
        cat for cat in actual_categories.values() if cat.availability == AUTHORITATIVE_AVAILABLE
    ]
    if consumption_has_unvalued:
        actual_cost = None
        actual_cost_metric = MetricComponent(
            amount=None,
            availability=PENDING_SOURCE,
            domain="warehouse",
            record_count=consumption_line_count,
            source_model="InternalConsumptionLine",
            reason="UNVALUED_INTERNAL_CONSUMPTION_LINES",
        )
    elif authoritative_actual_cats:
        actual_cost = sum(
            (cat.amount for cat in authoritative_actual_cats if cat.amount is not None),
            Decimal("0"),
        )
        total_records = sum(cat.record_count for cat in authoritative_actual_cats)
        actual_cost_metric = MetricComponent(
            amount=actual_cost,
            availability=AUTHORITATIVE_AVAILABLE,
            domain="cross-domain",
            record_count=total_records,
            source_model="InternalConsumption,SubcontractReceipt,ProductionCost",
            reason="SUM_OF_AUTHORITATIVE_ACTUAL_COSTS",
        )
    else:
        actual_cost = None
        actual_cost_metric = MetricComponent(
            amount=None,
            availability=PENDING_SOURCE,
            domain="cross-domain",
            record_count=0,
            source_model="None",
            reason="NO_AUTHORITATIVE_ACTUAL_COST_SOURCES",
        )

    # 7. Forecast Cost (Explicit Project Forecast Planning Layer)
    active_forecast_lines = project.forecast_lines.filter(is_active=True)
    forecast_count = active_forecast_lines.count()
    forecast_line_ids = tuple(str(pk) for pk in active_forecast_lines.values_list("id", flat=True))
    forecast_categories: dict[str, CostCategoryItem] = {}
    for cat in ProjectBudgetCategory.values:
        forecast_categories[cat] = CostCategoryItem(
            category=cat,
            amount=None,
            availability=PENDING_SOURCE,
            domain="projects",
            record_count=0,
            reason=f"NO_ACTIVE_FORECAST_FOR_{cat}",
        )

    if forecast_count == 0:
        forecast_cost = None
        forecast_cost_metric = MetricComponent(
            amount=None,
            availability=PENDING_SOURCE,
            domain="projects",
            record_count=0,
            source_model="ProjectForecastLine",
            reason="NO_ACTIVE_PROJECT_FORECAST_LINES",
        )
    else:
        cat_aggs = active_forecast_lines.values("category").annotate(
            total=Sum("amount"),
            cnt=Count("id"),
        )
        total_forecast = Decimal("0")
        for item in cat_aggs:
            c = item["category"]
            amt = item["total"] or Decimal("0")
            cnt = item["cnt"]
            total_forecast += amt
            forecast_categories[c] = CostCategoryItem(
                category=c,
                amount=amt,
                availability=AUTHORITATIVE_AVAILABLE,
                domain="projects",
                record_count=cnt,
                reason="ACTIVE_PROJECT_FORECAST_LINES",
            )
        forecast_cost = total_forecast
        forecast_cost_metric = MetricComponent(
            amount=forecast_cost,
            availability=AUTHORITATIVE_AVAILABLE,
            domain="projects",
            record_count=forecast_count,
            source_model="ProjectForecastLine",
            reason="ACTIVE_PROJECT_FORECAST_LINES",
        )

    # 8. Variances
    # Determine authoritative budget value for derived variances
    # (Must not silently choose between header and active lines when they differ)
    authoritative_budget: Decimal | None = None
    if budget_status == "MATCH":
        authoritative_budget = active_lines_total
    elif budget_status == "NO_LINES" and header_total == Decimal("0"):
        authoritative_budget = Decimal("0")
    else:
        # DIFFERENCE or (NO_LINES and header_total != 0) -> PENDING_SOURCE
        authoritative_budget = None

    # A. Budget vs Forecast (positive = under budget, negative = over budget)
    if forecast_cost is not None and authoritative_budget is not None:
        variance_budget_forecast = authoritative_budget - forecast_cost
    else:
        variance_budget_forecast = None

    # B. Budget vs Actual
    if actual_cost is not None and authoritative_budget is not None:
        variance_budget_actual = authoritative_budget - actual_cost
    else:
        variance_budget_actual = None

    # C. Forecast vs Actual (remaining to forecast)
    if forecast_cost is not None and actual_cost is not None:
        remaining_to_forecast = forecast_cost - actual_cost
    else:
        remaining_to_forecast = None

    # D. Actual + Authoritative Committed Exposure
    if actual_cost is not None and committed_cost is not None:
        current_cost_exposure = actual_cost + committed_cost
    else:
        current_cost_exposure = None

    # 9. Projected Profit & Margin (Calculated only when recognized revenue
    # and forecast are authoritative)
    if recognized_revenue is not None and forecast_cost is not None:
        projected_profit = recognized_revenue - forecast_cost
        if recognized_revenue > Decimal("0"):
            projected_margin_percent = (
                (projected_profit / recognized_revenue) * Decimal("100")
            ).quantize(Decimal("0.01"))
        else:
            projected_margin_percent = None
    else:
        projected_profit = None
        projected_margin_percent = None

    # 10. Completeness and Missing Sources
    missing = []
    if forecast_cost is None:
        missing.append("forecast")
    missing.append("incentives")  # CPO fee and Sales fee deferred to Phase 9B
    missing_sources = tuple(missing)
    data_complete = False

    return ProjectProfitability(
        commercial_order_value=commercial_order_value,
        commercial_invoice_source_value=commercial_invoice_source_value,
        budget_value=project.budget_total,
        committed_cost=committed_cost,
        actual_cost=actual_cost,
        forecast_cost=forecast_cost,
        projected_profit=projected_profit,
        projected_margin_percent=projected_margin_percent,
        data_complete=data_complete,
        missing_sources=missing_sources,
        recognized_revenue=recognized_revenue,
        budget=budget_reconciliation,
        revenue_metric=revenue_metric,
        commercial_order_metric=commercial_order_metric,
        commercial_invoice_metric=commercial_invoice_metric,
        committed_cost_metric=committed_cost_metric,
        actual_cost_metric=actual_cost_metric,
        forecast_cost_metric=forecast_cost_metric,
        actual_categories=actual_categories,
        committed_categories=committed_categories,
        forecast_categories=forecast_categories,
        forecast_line_ids=forecast_line_ids,
        variance_budget_forecast=variance_budget_forecast,
        variance_budget_actual=variance_budget_actual,
        remaining_to_forecast=remaining_to_forecast,
        current_cost_exposure=current_cost_exposure,
    )
