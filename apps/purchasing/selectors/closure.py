from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Max, Sum

from apps.finance.services import FinanceMappingError, resolve_account_mapping
from apps.organizations.selectors import accessible_legal_entities
from apps.purchasing.models import (
    AccountingTreatment,
    PurchaseOrder,
    PurchaseOrderState,
    SubcontractCostType,
    SubcontractReceiptState,
    WorkOrderState,
    WorkOrderType,
)


@dataclass(frozen=True)
class ProcurementFinanceSource:
    source_key: str
    source_type: str
    source_line_id: str
    readiness: str
    reason: str
    mapping: object | None
    active: bool
    amount: Decimal


def _mapping(*, entity, date, treatment, cost_center=None, project=None):
    context = {"PURCHASE_CATEGORY": treatment}
    if cost_center:
        context["COST_CENTER"] = str(cost_center)
    if project:
        context["PROJECT"] = str(project)
    try:
        return resolve_account_mapping(
            legal_entity=entity,
            module_code="PURCHASING",
            event_code="PROCUREMENT_PAYABLE",
            line_role="PAYABLE",
            business_date=date,
            context=context,
        )
    except FinanceMappingError:
        return None


def procurement_finance_sources(user):
    sources = []
    receipts = PurchaseOrder.objects.none()
    from apps.purchasing.models import SubcontractReceipt

    receipts = (
        SubcontractReceipt.objects.filter(
            legal_entity__in=accessible_legal_entities(user), state=SubcontractReceiptState.ACCEPTED
        )
        .select_related("legal_entity", "work_order__project")
        .prefetch_related("cost_lines")
    )
    for receipt in receipts:
        for line in receipt.cost_lines.all():
            mapping = _mapping(
                entity=receipt.legal_entity,
                date=receipt.receipt_date,
                treatment=AccountingTreatment.MAKLUN,
                project=receipt.work_order.project_id,
            )
            sources.append(
                ProcurementFinanceSource(
                    source_key=f"PURCH_PAYABLE|{line.pk}",
                    source_type="SUBCONTRACT_SERVICE",
                    source_line_id=str(line.pk),
                    readiness="READY" if mapping else "BLOCKED_MAPPING",
                    reason="Accepted subcontract service cost"
                    if mapping
                    else "Finance mapping is not configured",
                    mapping=mapping,
                    active=True,
                    amount=line.amount,
                )
            )
    return tuple(sources)


def production_overhead_sources(user):
    lines = PurchaseOrder.objects.filter(
        legal_entity__in=accessible_legal_entities(user), state=PurchaseOrderState.CONFIRMED
    ).prefetch_related("lines__cost_center_snapshot")
    result = []
    for order in lines:
        for line in order.lines.all():
            eligible = (
                line.accounting_treatment_snapshot
                in {AccountingTreatment.EXPENSE, AccountingTreatment.SERVICE}
                and line.snapshot_production
                and line.cost_center_snapshot
                and line.cost_center_snapshot.is_production_overhead_eligible
            )
            if eligible:
                result.append(
                    {
                        "source_key": f"PURCH_OVERHEAD|{line.pk}",
                        "purchase_order_id": str(order.pk),
                        "line_id": str(line.pk),
                        "amount": line.line_total,
                        "treatment": line.accounting_treatment_snapshot,
                        "cost_center_id": str(line.cost_center_snapshot_id),
                        "active": True,
                        "readiness": "ELIGIBLE_COMMITMENT",
                        "actual_hpp_status": "NOT_POSTED",
                    }
                )
    return tuple(result)


def production_overhead_eligibility_candidates(user):
    """Confirmed PO eligibility only; never an actual posted HPP source."""
    return production_overhead_sources(user)


def vendor_analytics(user):
    entities = accessible_legal_entities(user)
    from apps.partners.models import BusinessPartner
    from apps.purchasing.models import SubcontractReceipt

    vendors = BusinessPartner.objects.filter(legal_entity__in=entities).annotate(
        po_count=Count(
            "purchase_orders",
            filter=__import__("django.db.models", fromlist=["Q"]).Q(
                purchase_orders__state=PurchaseOrderState.CONFIRMED
            ),
            distinct=True,
        ),
        po_value=Sum(
            "purchase_orders__lines__line_total",
            filter=__import__("django.db.models", fromlist=["Q"]).Q(
                purchase_orders__state=PurchaseOrderState.CONFIRMED
            ),
        ),
        latest_po=Max("purchase_orders__document_date"),
    )
    output = []
    for vendor in vendors:
        work_orders = vendor.work_orders.filter(
            state=WorkOrderState.APPROVED, work_order_type=WorkOrderType.SUBCONTRACT
        )
        target = work_orders.aggregate(value=Sum("outputs__target_quantity"))["value"] or Decimal(
            "0"
        )
        accepted = SubcontractReceipt.objects.filter(
            vendor=vendor, state=SubcontractReceiptState.ACCEPTED
        ).aggregate(value=Sum("output_lines__accepted_quantity"))["value"] or Decimal("0")
        costs = SubcontractReceipt.objects.filter(
            vendor=vendor, state=SubcontractReceiptState.ACCEPTED
        )
        output.append(
            {
                "vendor": vendor,
                "confirmed_po_count": vendor.po_count,
                "confirmed_po_value": vendor.po_value or Decimal("0"),
                "subcontract_spk_count": work_orders.count(),
                "target_output_quantity": target,
                "accepted_output_quantity": accepted,
                "subcontract_fulfillment_percent": accepted / target * Decimal("100")
                if target
                else None,
                "specific_service_cost": costs.filter(
                    cost_lines__cost_type=SubcontractCostType.SPECIFIC_SERVICE
                ).aggregate(value=Sum("cost_lines__amount"))["value"]
                or Decimal("0"),
                "shared_service_cost": costs.filter(
                    cost_lines__cost_type=SubcontractCostType.SHARED_SERVICE
                ).aggregate(value=Sum("cost_lines__amount"))["value"]
                or Decimal("0"),
                "latest_activity": vendor.latest_po,
            }
        )
    return tuple(output)


def vendor_analytics_detail(user, *, vendor_id):
    from apps.partners.models import BusinessPartner
    from apps.purchasing.models import SubcontractMaterialDispatch, SubcontractReceipt

    vendor = BusinessPartner.objects.filter(legal_entity__in=accessible_legal_entities(user)).get(
        pk=vendor_id
    )
    summary = next(row for row in vendor_analytics(user) if row["vendor"].pk == vendor.pk)
    orders = (
        PurchaseOrder.objects.filter(vendor=vendor)
        .select_related("project")
        .prefetch_related("lines")
        .order_by("-document_date")[:25]
    )
    work_orders = (
        vendor.work_orders.filter(work_order_type=WorkOrderType.SUBCONTRACT)
        .select_related("project", "sales_order")
        .prefetch_related("outputs", "subcontract_receipts__output_lines")
        .order_by("-document_date")[:25]
    )
    dispatches = (
        SubcontractMaterialDispatch.objects.filter(vendor=vendor)
        .select_related("work_order")
        .prefetch_related("lines")
        .order_by("-dispatch_date")[:25]
    )
    receipts = (
        SubcontractReceipt.objects.filter(vendor=vendor)
        .select_related("work_order")
        .prefetch_related("output_lines", "cost_lines")
        .order_by("-receipt_date")[:25]
    )
    return {
        "vendor": vendor,
        "summary": summary,
        "orders": orders,
        "work_orders": work_orders,
        "dispatches": dispatches,
        "receipts": receipts,
    }
