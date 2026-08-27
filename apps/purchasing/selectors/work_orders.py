from apps.organizations.selectors import accessible_legal_entities
from apps.purchasing.models import WorkOrder, WorkOrderState, WorkOrderType


def work_orders(user, *, state="", work_order_type=""):
    queryset = WorkOrder.objects.select_related(
        "legal_entity", "vendor", "sales_order", "project"
    ).filter(legal_entity__in=accessible_legal_entities(user))
    if state:
        queryset = queryset.filter(state=state)
    if work_order_type:
        queryset = queryset.filter(work_order_type=work_order_type)
    return queryset.order_by("-document_date", "-created_at")


def work_order_detail(user, *, pk):
    return (
        work_orders(user)
        .prefetch_related("outputs__material_allocations__material_item")
        .get(pk=pk)
    )


def approved_internal_work_orders(user):
    return work_orders(
        user, state=WorkOrderState.APPROVED, work_order_type=WorkOrderType.INTERNAL
    ).prefetch_related("outputs__material_allocations")


def approved_subcontract_work_orders(user):
    return work_orders(
        user, state=WorkOrderState.APPROVED, work_order_type=WorkOrderType.SUBCONTRACT
    ).prefetch_related("outputs__material_allocations")
