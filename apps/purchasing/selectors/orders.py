from dataclasses import dataclass
from decimal import Decimal

from apps.organizations.selectors import accessible_legal_entities
from apps.partners.models import PartnerRoleType
from apps.partners.selectors import effective_business_partners
from apps.purchasing.models import PurchaseOrder, PurchaseOrderState


@dataclass(frozen=True)
class PurchaseCommitment:
    identity: str
    purchase_order_id: str
    purchase_order_line_id: str
    legal_entity_id: str
    project_id: str | None
    vendor_id: str
    item_id: str | None
    purchase_category_id: str
    accounting_treatment: str
    quantity: Decimal
    amount: Decimal
    currency: str
    cost_center_id: str | None
    expected_date: object


def purchase_orders(user, *, state="", search=""):
    qs = PurchaseOrder.objects.select_related("legal_entity", "vendor", "project").filter(
        legal_entity__in=accessible_legal_entities(user)
    )
    if state:
        qs = qs.filter(state=state)
    if search:
        qs = qs.filter(document_number__icontains=search)
    return qs.order_by("-document_date", "-created_at")


def purchase_order_detail(user, *, pk):
    return (
        purchase_orders(user)
        .prefetch_related("lines__item", "lines__purchase_category", "lines__cost_center_snapshot")
        .get(pk=pk)
    )


def eligible_vendors(user, *, legal_entity=None, business_date=None):
    qs = effective_business_partners(
        user, business_date=business_date, role_type=PartnerRoleType.VENDOR
    )
    return qs.filter(legal_entity=legal_entity) if legal_entity else qs


def committed_cost_sources(user, *, project=None):
    qs = PurchaseOrder.objects.filter(
        legal_entity__in=accessible_legal_entities(user), state=PurchaseOrderState.CONFIRMED
    ).prefetch_related("lines")
    if project:
        qs = qs.filter(project=project)
    return tuple(
        PurchaseCommitment(
            identity=f"PURCHASE_ORDER_LINE:{line.pk}",
            purchase_order_id=str(order.pk),
            purchase_order_line_id=str(line.pk),
            legal_entity_id=str(order.legal_entity_id),
            project_id=str(order.project_id) if order.project_id else None,
            vendor_id=str(order.vendor_id),
            item_id=str(line.item_id) if line.item_id else None,
            purchase_category_id=str(line.purchase_category_id),
            accounting_treatment=line.accounting_treatment_snapshot,
            quantity=line.quantity,
            amount=line.line_total,
            currency=order.currency,
            cost_center_id=str(line.cost_center_snapshot_id)
            if line.cost_center_snapshot_id
            else None,
            expected_date=order.expected_date,
        )
        for order in qs
        for line in order.lines.all()
    )


def treatment_candidates(user, treatment):
    return tuple(
        item for item in committed_cost_sources(user) if item.accounting_treatment == treatment
    )
