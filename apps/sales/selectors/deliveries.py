from dataclasses import dataclass
from decimal import Decimal

from django.db.models import (
    Case,
    DecimalField,
    F,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from apps.organizations.selectors import accessible_legal_entities
from apps.sales.models import (
    SalesDelivery,
    SalesDeliveryLine,
    SalesDeliveryState,
    SalesInvoice,
    SalesInvoiceDocumentKind,
    SalesInvoiceLine,
    SalesInvoiceState,
    SalesOrderLine,
    SalesOrderState,
)

QUANTITY_FIELD = DecimalField(max_digits=18, decimal_places=6)
ZERO_QUANTITY = Value(Decimal("0"), output_field=QUANTITY_FIELD)


def _posted_delivery_quantity():
    return Coalesce(
        Subquery(
            SalesDeliveryLine.objects.filter(
                source_sales_order_line_id=OuterRef("pk"),
                sales_delivery__state=SalesDeliveryState.POSTED,
            )
            .values("source_sales_order_line_id")
            .annotate(total=Sum("quantity"))
            .values("total")[:1],
            output_field=QUANTITY_FIELD,
        ),
        ZERO_QUANTITY,
    )


def _confirmed_invoice_quantity(source_field):
    return Coalesce(
        Subquery(
            SalesInvoiceLine.objects.filter(
                **{source_field: OuterRef("pk")},
                sales_invoice__state=SalesInvoiceState.CONFIRMED,
                sales_invoice__document_kind=SalesInvoiceDocumentKind.INVOICE,
            )
            .values(source_field)
            .annotate(total=Sum("quantity"))
            .values("total")[:1],
            output_field=QUANTITY_FIELD,
        ),
        ZERO_QUANTITY,
    )


def _with_remaining_delivery(queryset):
    return queryset.annotate(
        delivered_quantity=_posted_delivery_quantity(),
        remaining_delivery_quantity=F("quantity") - _posted_delivery_quantity(),
    ).annotate(
        fulfillment_status=Case(
            When(delivered_quantity=0, then=Value("NOT_DELIVERED")),
            When(delivered_quantity__gte=F("quantity"), then=Value("FULLY_DELIVERED")),
            default=Value("PARTIALLY_DELIVERED"),
        )
    )


def delivery_lines_with_remaining(*, user, customer=None, legal_entity=None):
    queryset = SalesOrderLine.objects.select_related(
        "sales_order", "sales_order__customer", "sales_order__legal_entity", "item"
    ).filter(
        sales_order__legal_entity__in=accessible_legal_entities(user),
        sales_order__state=SalesOrderState.CONFIRMED,
    )
    if customer is not None:
        queryset = queryset.filter(sales_order__customer=customer)
    if legal_entity is not None:
        queryset = queryset.filter(sales_order__legal_entity=legal_entity)
    return (
        _with_remaining_delivery(queryset)
        .filter(remaining_delivery_quantity__gt=0)
        .order_by("sales_order__document_date", "sales_order__document_number", "line_number")
    )


def sales_deliveries(user, *, search="", state="", legal_entity=None):
    queryset = SalesDelivery.objects.select_related(
        "legal_entity", "customer", "created_by", "posted_by", "cancelled_by"
    ).filter(legal_entity__in=accessible_legal_entities(user))
    if legal_entity is not None:
        queryset = queryset.filter(legal_entity=legal_entity)
    if state:
        queryset = queryset.filter(state=state)
    if search:
        queryset = queryset.filter(
            Q(document_number__icontains=search)
            | Q(customer_code_snapshot__icontains=search)
            | Q(customer_name_snapshot__icontains=search)
            | Q(expedition_reference__icontains=search)
        )
    return queryset.order_by("-delivery_date", "-created_at")


def sales_delivery_detail(user, *, pk):
    line_queryset = SalesDeliveryLine.objects.select_related(
        "item", "source_sales_order_line", "source_sales_order_line__sales_order"
    ).order_by("line_number")
    return (
        sales_deliveries(user)
        .prefetch_related(Prefetch("lines", queryset=line_queryset))
        .get(pk=pk)
    )


@dataclass(frozen=True)
class WarehouseGoodsIssueCandidate:
    identity: str
    source_type: str
    source_delivery_id: str
    source_delivery_line_id: str
    sales_order_id: str
    sales_order_line_id: str
    legal_entity_id: str
    customer_id: str
    item_id: str
    quantity: Decimal
    uom_code: str
    delivery_date: object
    destination: str
    is_correction: bool = False


def _candidate(line: SalesDeliveryLine, *, correction=False):
    return WarehouseGoodsIssueCandidate(
        identity=(
            f"SALES_DELIVERY_REVERSAL:{line.pk}" if correction else f"SALES_DELIVERY_LINE:{line.pk}"
        ),
        source_type="SALES_DELIVERY_REVERSAL" if correction else "SALES_DELIVERY",
        source_delivery_id=str(line.sales_delivery_id),
        source_delivery_line_id=str(line.pk),
        sales_order_id=str(line.source_sales_order_line.sales_order_id),
        sales_order_line_id=str(line.source_sales_order_line_id),
        legal_entity_id=str(line.sales_delivery.legal_entity_id),
        customer_id=str(line.sales_delivery.customer_id),
        item_id=str(line.item_id),
        quantity=line.quantity,
        uom_code=line.uom_code_snapshot,
        delivery_date=line.sales_delivery.delivery_date,
        destination=line.sales_delivery.destination_snapshot,
        is_correction=correction,
    )


def warehouse_goods_issue_candidates(user, *, delivery):
    """Bounded Warehouse handoff: one posted delivery, no warehouse mutation."""

    scoped = sales_deliveries(user).filter(pk=delivery.pk, state=SalesDeliveryState.POSTED)
    lines = SalesDeliveryLine.objects.select_related(
        "sales_delivery", "source_sales_order_line"
    ).filter(sales_delivery__in=scoped)
    return tuple(_candidate(line) for line in lines)


def warehouse_goods_issue_correction_candidates(user, *, delivery):
    """Future Warehouse reversal contract for a cancelled delivery that had been posted."""

    scoped = sales_deliveries(user).filter(
        pk=delivery.pk,
        state=SalesDeliveryState.CANCELLED,
        posted_at__isnull=False,
    )
    lines = SalesDeliveryLine.objects.select_related(
        "sales_delivery", "source_sales_order_line"
    ).filter(sales_delivery__in=scoped)
    return tuple(_candidate(line, correction=True) for line in lines)


def posted_delivery_lines_for_invoice(user, *, customer=None, legal_entity=None):
    queryset = SalesDeliveryLine.objects.select_related(
        "sales_delivery",
        "source_sales_order_line",
        "source_sales_order_line__sales_order",
        "item",
    ).filter(
        sales_delivery__legal_entity__in=accessible_legal_entities(user),
        sales_delivery__state=SalesDeliveryState.POSTED,
    )
    if customer is not None:
        queryset = queryset.filter(sales_delivery__customer=customer)
    if legal_entity is not None:
        queryset = queryset.filter(sales_delivery__legal_entity=legal_entity)
    return (
        queryset.annotate(
            invoiced_quantity=_confirmed_invoice_quantity("source_sales_delivery_line_id"),
            remaining_invoice_quantity=F("quantity")
            - _confirmed_invoice_quantity("source_sales_delivery_line_id"),
        )
        .filter(remaining_invoice_quantity__gt=0)
        .order_by("sales_delivery__delivery_date", "sales_delivery__document_number", "line_number")
    )


def sales_order_lines_for_invoice_exception(user, *, customer=None, legal_entity=None):
    queryset = SalesOrderLine.objects.select_related(
        "sales_order", "sales_order__customer", "sales_order__legal_entity", "item"
    ).filter(
        sales_order__legal_entity__in=accessible_legal_entities(user),
        sales_order__state=SalesOrderState.CONFIRMED,
    )
    if customer is not None:
        queryset = queryset.filter(sales_order__customer=customer)
    if legal_entity is not None:
        queryset = queryset.filter(sales_order__legal_entity=legal_entity)
    return (
        queryset.annotate(
            invoiced_quantity=_confirmed_invoice_quantity("source_sales_order_line_id"),
            remaining_invoice_quantity=F("quantity")
            - _confirmed_invoice_quantity("source_sales_order_line_id"),
        )
        .filter(remaining_invoice_quantity__gt=0)
        .order_by("sales_order__document_date", "sales_order__document_number", "line_number")
    )


def sales_invoices(user, *, search="", state="", legal_entity=None, document_kind=""):
    queryset = SalesInvoice.objects.select_related(
        "legal_entity", "customer", "created_by", "confirmed_by", "cancelled_by"
    ).filter(legal_entity__in=accessible_legal_entities(user))
    if legal_entity is not None:
        queryset = queryset.filter(legal_entity=legal_entity)
    if state:
        queryset = queryset.filter(state=state)
    if document_kind:
        queryset = queryset.filter(document_kind=document_kind)
    if search:
        queryset = queryset.filter(
            Q(document_number__icontains=search)
            | Q(customer_code_snapshot__icontains=search)
            | Q(customer_name_snapshot__icontains=search)
        )
    return queryset.order_by("-invoice_date", "-created_at")


def sales_invoice_detail(user, *, pk):
    line_queryset = SalesInvoiceLine.objects.select_related(
        "item",
        "source_sales_order_line",
        "source_sales_order_line__sales_order",
        "source_sales_delivery_line",
        "source_sales_delivery_line__sales_delivery",
    ).order_by("line_number")
    return (
        sales_invoices(user).prefetch_related(Prefetch("lines", queryset=line_queryset)).get(pk=pk)
    )


def finance_invoice_candidates(user, *, invoice=None):
    """Read-only candidate contract for a future Finance owner; no AR or journal exists here."""

    queryset = sales_invoices(user).filter(
        state=SalesInvoiceState.CONFIRMED,
        document_kind=SalesInvoiceDocumentKind.INVOICE,
    )
    if invoice is not None:
        queryset = queryset.filter(pk=invoice.pk)
    line_queryset = SalesInvoiceLine.objects.select_related(
        "source_sales_order_line", "source_sales_delivery_line"
    ).order_by("line_number")
    return queryset.prefetch_related(Prefetch("lines", queryset=line_queryset))


def confirmed_sales_order_lines_with_fulfillment(user, *, legal_entity=None, requested_before=None):
    queryset = SalesOrderLine.objects.select_related(
        "sales_order", "sales_order__customer", "sales_order__legal_entity", "item"
    ).filter(
        sales_order__legal_entity__in=accessible_legal_entities(user),
        sales_order__state=SalesOrderState.CONFIRMED,
    )
    if legal_entity is not None:
        queryset = queryset.filter(sales_order__legal_entity=legal_entity)
    if requested_before is not None:
        queryset = queryset.filter(sales_order__requested_delivery_date__lte=requested_before)
    return (
        _with_remaining_delivery(queryset)
        .annotate(remaining_downstream_quantity=F("remaining_delivery_quantity"))
        .order_by(
            "sales_order__requested_delivery_date", "sales_order__document_date", "line_number"
        )
    )
