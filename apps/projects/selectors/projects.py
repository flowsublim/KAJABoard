from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Max, Sum
from django.utils import timezone

from apps.core.contracts.finance import CustomerFinanceExposure, customer_finance_exposure
from apps.organizations.selectors import accessible_legal_entities
from apps.partners.models import PartnerRoleType
from apps.partners.selectors import effective_business_partners
from apps.projects.models import Project, ProjectState
from apps.sales.models import (
    SalesDeliveryLine,
    SalesDeliveryState,
    SalesInvoiceDocumentKind,
    SalesInvoiceLine,
    SalesInvoiceState,
    SalesOrder,
    SalesOrderState,
)
from apps.sales.selectors.deliveries import confirmed_sales_order_lines_with_fulfillment


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


@dataclass(frozen=True)
class ProjectDemandCandidate:
    identity: str
    project_id: str
    sales_order_id: str
    sales_order_line_id: str
    legal_entity_id: str
    customer_id: str
    item_id: str
    quantity: Decimal
    remaining_delivery_quantity: Decimal
    requested_delivery_date: object


def projects(user, *, search="", state=""):
    queryset = Project.objects.select_related("legal_entity", "customer", "owner").filter(
        legal_entity__in=accessible_legal_entities(user)
    )
    if state:
        queryset = queryset.filter(state=state)
    if search:
        from django.db.models import Q

        queryset = queryset.filter(
            Q(code__icontains=search)
            | Q(name__icontains=search)
            | Q(customer__display_name__icontains=search)
        )
    return queryset.order_by("-start_date", "-created_at")


def project_detail(user, *, pk):
    return (
        projects(user)
        .prefetch_related(
            "budget_lines",
            "sales_order_links__sales_order__lines",
        )
        .get(pk=pk)
    )


def project_profitability(project) -> ProjectProfitability:
    """Commercial/budget view only; unavailable source values are deliberately None."""
    linked_orders = SalesOrder.objects.filter(
        project_link__project=project,
        state__in=(SalesOrderState.CONFIRMED, SalesOrderState.ON_HOLD, SalesOrderState.CLOSED),
    )
    commercial_order_value = linked_orders.aggregate(value=Sum("grand_total"))["value"] or Decimal(
        "0"
    )
    commercial_invoice_source_value = SalesInvoiceLine.objects.filter(
        source_sales_order_line__sales_order__project_link__project=project,
        sales_invoice__state=SalesInvoiceState.CONFIRMED,
        sales_invoice__document_kind=SalesInvoiceDocumentKind.INVOICE,
    ).values("sales_invoice_id").distinct().aggregate(value=Sum("sales_invoice__grand_total"))[
        "value"
    ] or Decimal("0")
    return ProjectProfitability(
        commercial_order_value=commercial_order_value,
        commercial_invoice_source_value=commercial_invoice_source_value,
        budget_value=project.budget_total,
        committed_cost=None,
        actual_cost=None,
        forecast_cost=None,
        projected_profit=None,
        projected_margin_percent=None,
        data_complete=False,
        missing_sources=("purchasing", "production", "warehouse", "finance", "incentives"),
    )


def project_progress(project) -> dict[str, object]:
    order_count = SalesOrder.objects.filter(
        project_link__project=project, state=SalesOrderState.CONFIRMED
    ).count()
    delivery_count = SalesDeliveryLine.objects.filter(
        source_sales_order_line__sales_order__project_link__project=project,
        sales_delivery__state=SalesDeliveryState.POSTED,
    ).count()
    invoice_count = SalesInvoiceLine.objects.filter(
        source_sales_order_line__sales_order__project_link__project=project,
        sales_invoice__state=SalesInvoiceState.CONFIRMED,
        sales_invoice__document_kind=SalesInvoiceDocumentKind.INVOICE,
    ).count()
    return {
        "sales_confirmed": {"available": True, "count": order_count},
        "delivery": {"available": True, "count": delivery_count},
        "invoicing_source": {"available": True, "count": invoice_count},
        "procurement": {"available": False},
        "production": {"available": False},
        "warehouse_receipt": {"available": False},
        "collection": {"available": False},
    }


def project_b2b_demand_candidates(user, *, project):
    if project.state != ProjectState.ACTIVE:
        return ()
    lines = confirmed_sales_order_lines_with_fulfillment(user).filter(
        sales_order__project_link__project=project
    )
    return tuple(
        ProjectDemandCandidate(
            identity=f"PROJECT_DEMAND:{project.pk}:{line.pk}",
            project_id=str(project.pk),
            sales_order_id=str(line.sales_order_id),
            sales_order_line_id=str(line.pk),
            legal_entity_id=str(project.legal_entity_id),
            customer_id=str(project.customer_id),
            item_id=str(line.item_id),
            quantity=line.quantity,
            remaining_delivery_quantity=line.remaining_delivery_quantity,
            requested_delivery_date=line.sales_order.requested_delivery_date,
        )
        for line in lines
    )


def customer_360(user, *, customer, as_of_date=None) -> dict[str, object]:
    as_of_date = as_of_date or timezone.localdate()
    if (
        not effective_business_partners(
            user, business_date=as_of_date, role_type=PartnerRoleType.CUSTOMER
        )
        .filter(pk=customer.pk)
        .exists()
    ):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    orders = SalesOrder.objects.filter(
        customer=customer, legal_entity__in=accessible_legal_entities(user)
    ).exclude(state=SalesOrderState.CANCELLED)
    commercial = orders.aggregate(
        value=Sum("grand_total"), count=Count("pk"), last_order=Max("document_date")
    )
    count = commercial["count"] or 0
    value = commercial["value"] or Decimal("0")
    top_items = list(
        orders.values("lines__item_code_snapshot", "lines__item_name_snapshot")
        .annotate(quantity=Sum("lines__quantity"))
        .order_by("-quantity")[:5]
    )
    exposure = customer_finance_exposure(customer, as_of_date=as_of_date)
    return {
        "customer": customer,
        "as_of_date": as_of_date,
        "commercial_value": value,
        "order_count": count,
        "average_order_value": (value / count if count else Decimal("0")),
        "last_order": commercial["last_order"],
        "top_items": top_items,
        "open_orders": orders.filter(
            state__in=(SalesOrderState.CONFIRMED, SalesOrderState.ON_HOLD)
        )[:10],
        "projects": projects(user).filter(customer=customer)[:10],
        "finance_exposure": exposure,
        "related_deliveries": SalesDeliveryLine.objects.filter(
            source_sales_order_line__sales_order__customer=customer,
            sales_delivery__state=SalesDeliveryState.POSTED,
        ).select_related("sales_delivery")[:10],
        "invoice_lines": SalesInvoiceLine.objects.filter(
            sales_invoice__customer=customer
        ).select_related("sales_invoice")[:10],
    }


def statement_of_account(user, *, customer, as_of_date=None) -> CustomerFinanceExposure:
    customer_360(user, customer=customer, as_of_date=as_of_date)
    return customer_finance_exposure(customer, as_of_date=as_of_date)
