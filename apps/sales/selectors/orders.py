from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.catalog.selectors import effective_items
from apps.organizations.selectors import accessible_legal_entities
from apps.partners.models import PartnerRoleType
from apps.partners.selectors import effective_business_partners
from apps.sales.models import SalesOrder, SalesOrderLine


def sales_orders(user, *, search="", state="", legal_entity=None):
    queryset = SalesOrder.objects.select_related(
        "legal_entity",
        "customer",
        "business_unit",
        "created_by",
        "confirmed_by",
    ).filter(legal_entity__in=accessible_legal_entities(user))
    if legal_entity is not None:
        queryset = queryset.filter(legal_entity=legal_entity)
    if state:
        queryset = queryset.filter(state=state)
    if search:
        queryset = queryset.filter(
            Q(document_number__icontains=search)
            | Q(customer_po_reference__icontains=search)
            | Q(customer_code_snapshot__icontains=search)
            | Q(customer_name_snapshot__icontains=search)
        )
    return queryset.order_by("-document_date", "-created_at")


def sales_order_detail(user, *, pk):
    line_queryset = SalesOrderLine.objects.select_related("item", "item__uom").order_by(
        "line_number"
    )
    return sales_orders(user).prefetch_related(Prefetch("lines", queryset=line_queryset)).get(pk=pk)


def eligible_customers(user, *, legal_entity=None, business_date=None):
    queryset = effective_business_partners(
        user,
        business_date=business_date or timezone.localdate(),
        role_type=PartnerRoleType.CUSTOMER,
    )
    if legal_entity is not None:
        queryset = queryset.filter(legal_entity=legal_entity)
    return queryset


def eligible_sales_items(user, *, legal_entity=None, business_date=None):
    queryset = effective_items(user, business_date=business_date or timezone.localdate()).filter(
        sales_eligible=True
    )
    if legal_entity is not None:
        queryset = queryset.filter(legal_entity=legal_entity)
    return queryset


def confirmed_sales_order_lines(user, *, legal_entity=None, requested_before=None):
    """Read-only handoff contract with derived delivery fulfillment in Phase 3B."""

    from apps.sales.selectors.deliveries import confirmed_sales_order_lines_with_fulfillment

    return confirmed_sales_order_lines_with_fulfillment(
        user, legal_entity=legal_entity, requested_before=requested_before
    )
