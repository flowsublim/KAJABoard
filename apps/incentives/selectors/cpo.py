"""CPO Finished Goods Fee authoritative candidate selector.

Provides read-only candidate evaluation contracts sourced strictly from
POSTED WarehouseReceiptLine records with explicit production handover lineage.
Zero database side-effects.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal

from apps.catalog.models import Item
from apps.incentives.models import (
    BeneficiaryKind,
    IncentiveAccrual,
    IncentiveAccrualState,
    IncentiveTriggerType,
    IncentiveType,
)
from apps.incentives.selectors.evaluation import IncentiveEvaluationResult, evaluate_incentive
from apps.organizations.models import LegalEntity
from apps.projects.models import Project
from apps.purchasing.models import WorkOrder, WorkOrderOutput
from apps.warehouse.models import WarehouseDocumentState, WarehouseReceipt, WarehouseReceiptLine


@dataclass(frozen=True)
class CPOCandidate:
    legal_entity: LegalEntity
    receipt_id: str
    receipt_line_id: str
    source_key: str
    receipt_date: datetime.date
    accepted_quantity: Decimal
    item: Item
    item_code: str
    item_name: str
    uom_code: str
    work_order: WorkOrder
    output: WorkOrderOutput
    project: Project | None
    beneficiary_id: str | None
    beneficiary_code: str
    beneficiary_name: str
    beneficiary_type: str
    status: str
    rate_value: Decimal | None = None
    calculated_amount: Decimal | None = None
    calculation_method: str | None = None
    currency: str = "IDR"
    evaluation: IncentiveEvaluationResult | None = None
    existing_accrual: IncentiveAccrual | None = None
    reason: str = ""


def get_cpo_candidate_for_receipt_line(line: WarehouseReceiptLine) -> CPOCandidate:
    """Evaluates a single WarehouseReceiptLine for CPO Finished Goods Fee accrual eligibility.

    Read-only selector, produces zero database writes.
    """
    receipt = line.receipt
    legal_entity = receipt.legal_entity
    receipt_id_str = str(receipt.pk)
    line_id_str = str(line.pk)
    source_key = f"CPO_FEE|warehouse|WAREHOUSE_RECEIPT_LINE|{line_id_str}"

    existing_accrual = IncentiveAccrual.objects.filter(source_key=source_key).first()

    item = line.item
    item_code = getattr(item, "code", "")
    item_name = getattr(item, "name", "")
    uom_code = line.uom_code_snapshot or (
        getattr(item.uom, "code", "") if item and item.uom else ""
    )

    work_order = receipt.work_order
    output = line.output
    # Direct FK only; strictly no project inference from customer/order/name
    project = work_order.project if work_order else None

    # 1. Validate receipt source type
    if receipt.source_module != "production" or receipt.source_type != "PRODUCTION_HANDOVER":
        return CPOCandidate(
            legal_entity=legal_entity,
            receipt_id=receipt_id_str,
            receipt_line_id=line_id_str,
            source_key=source_key,
            receipt_date=receipt.receipt_date,
            accepted_quantity=line.accepted_quantity,
            item=item,
            item_code=item_code,
            item_name=item_name,
            uom_code=uom_code,
            work_order=work_order,
            output=output,
            project=project,
            beneficiary_id=None,
            beneficiary_code="",
            beneficiary_name="",
            beneficiary_type=BeneficiaryKind.EMPLOYEE,
            status="INVALID_SOURCE",
            existing_accrual=existing_accrual,
            reason=(
                f"Receipt source module '{receipt.source_module}' and type '{receipt.source_type}' "
                "is not an authoritative finished goods production receipt."
            ),
        )

    # 2. Check receipt state (POSTED vs REVERSED vs DRAFT)
    if receipt.state == WarehouseDocumentState.REVERSED:
        if existing_accrual:
            if existing_accrual.state == IncentiveAccrualState.REVERSED:
                status = "ALREADY_REVERSED"
                reason = "Warehouse receipt and CPO fee accrual are both reversed."
            else:
                status = "PENDING_REVERSAL"
                reason = (
                    "Warehouse receipt was reversed; existing CPO fee accrual requires reversal."
                )
        else:
            status = "SOURCE_REVERSED"
            reason = "Warehouse receipt is reversed. Positive CPO fee accrual is not permitted."

        return CPOCandidate(
            legal_entity=legal_entity,
            receipt_id=receipt_id_str,
            receipt_line_id=line_id_str,
            source_key=source_key,
            receipt_date=receipt.receipt_date,
            accepted_quantity=line.accepted_quantity,
            item=item,
            item_code=item_code,
            item_name=item_name,
            uom_code=uom_code,
            work_order=work_order,
            output=output,
            project=project,
            beneficiary_id=existing_accrual.beneficiary_id if existing_accrual else None,
            beneficiary_code=existing_accrual.beneficiary_code_snapshot if existing_accrual else "",
            beneficiary_name=existing_accrual.beneficiary_name_snapshot if existing_accrual else "",
            beneficiary_type=BeneficiaryKind.EMPLOYEE,
            status=status,
            existing_accrual=existing_accrual,
            reason=reason,
        )

    if receipt.state != WarehouseDocumentState.POSTED:
        return CPOCandidate(
            legal_entity=legal_entity,
            receipt_id=receipt_id_str,
            receipt_line_id=line_id_str,
            source_key=source_key,
            receipt_date=receipt.receipt_date,
            accepted_quantity=line.accepted_quantity,
            item=item,
            item_code=item_code,
            item_name=item_name,
            uom_code=uom_code,
            work_order=work_order,
            output=output,
            project=project,
            beneficiary_id=None,
            beneficiary_code="",
            beneficiary_name="",
            beneficiary_type=BeneficiaryKind.EMPLOYEE,
            status="NOT_POSTED",
            existing_accrual=existing_accrual,
            reason=(
                f"Warehouse receipt state is '{receipt.state}'. "
                "Only POSTED receipts are eligible for CPO fee."
            ),
        )

    # 3. Explicit beneficiary lineage
    handover = receipt.handover
    beneficiary = handover.cpo_beneficiary if handover else None

    if beneficiary is None:
        return CPOCandidate(
            legal_entity=legal_entity,
            receipt_id=receipt_id_str,
            receipt_line_id=line_id_str,
            source_key=source_key,
            receipt_date=receipt.receipt_date,
            accepted_quantity=line.accepted_quantity,
            item=item,
            item_code=item_code,
            item_name=item_name,
            uom_code=uom_code,
            work_order=work_order,
            output=output,
            project=project,
            beneficiary_id=None,
            beneficiary_code="",
            beneficiary_name="",
            beneficiary_type=BeneficiaryKind.EMPLOYEE,
            status="PENDING_BENEFICIARY",
            existing_accrual=existing_accrual,
            reason="Production handover has no explicit CPO beneficiary assigned.",
        )

    if beneficiary.legal_entity_id != legal_entity.pk:
        return CPOCandidate(
            legal_entity=legal_entity,
            receipt_id=receipt_id_str,
            receipt_line_id=line_id_str,
            source_key=source_key,
            receipt_date=receipt.receipt_date,
            accepted_quantity=line.accepted_quantity,
            item=item,
            item_code=item_code,
            item_name=item_name,
            uom_code=uom_code,
            work_order=work_order,
            output=output,
            project=project,
            beneficiary_id=str(beneficiary.pk),
            beneficiary_code=beneficiary.employee_code,
            beneficiary_name=beneficiary.display_name,
            beneficiary_type=BeneficiaryKind.EMPLOYEE,
            status="INVALID_BENEFICIARY",
            existing_accrual=existing_accrual,
            reason="Beneficiary employee legal entity does not match receipt legal entity.",
        )

    if not beneficiary.is_active:
        return CPOCandidate(
            legal_entity=legal_entity,
            receipt_id=receipt_id_str,
            receipt_line_id=line_id_str,
            source_key=source_key,
            receipt_date=receipt.receipt_date,
            accepted_quantity=line.accepted_quantity,
            item=item,
            item_code=item_code,
            item_name=item_name,
            uom_code=uom_code,
            work_order=work_order,
            output=output,
            project=project,
            beneficiary_id=str(beneficiary.pk),
            beneficiary_code=beneficiary.employee_code,
            beneficiary_name=beneficiary.display_name,
            beneficiary_type=BeneficiaryKind.EMPLOYEE,
            status="INACTIVE_BENEFICIARY",
            existing_accrual=existing_accrual,
            reason="Beneficiary employee is inactive.",
        )

    # 4. Evaluate incentive rule & calculation
    eval_result = evaluate_incentive(
        legal_entity=legal_entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=receipt.receipt_date,
        basis_quantity=line.accepted_quantity,
        beneficiary={
            "beneficiary_type": BeneficiaryKind.EMPLOYEE,
            "beneficiary_id": str(beneficiary.pk),
            "beneficiary_code": beneficiary.employee_code,
            "beneficiary_name": beneficiary.display_name,
        },
        item=item,
        project=project,
    )

    return CPOCandidate(
        legal_entity=legal_entity,
        receipt_id=receipt_id_str,
        receipt_line_id=line_id_str,
        source_key=source_key,
        receipt_date=receipt.receipt_date,
        accepted_quantity=line.accepted_quantity,
        item=item,
        item_code=item_code,
        item_name=item_name,
        uom_code=uom_code,
        work_order=work_order,
        output=output,
        project=project,
        beneficiary_id=str(beneficiary.pk),
        beneficiary_code=beneficiary.employee_code,
        beneficiary_name=beneficiary.display_name,
        beneficiary_type=BeneficiaryKind.EMPLOYEE,
        status=eval_result.status,
        rate_value=eval_result.rate_value,
        calculated_amount=eval_result.calculated_amount,
        calculation_method=eval_result.calculation_method,
        currency=eval_result.currency,
        evaluation=eval_result,
        existing_accrual=existing_accrual,
        reason=eval_result.reason,
    )


def get_cpo_candidates_for_receipt(receipt: WarehouseReceipt) -> list[CPOCandidate]:
    """Returns CPO evaluation candidates for all lines of a WarehouseReceipt."""
    lines = receipt.lines.select_related("item", "item__uom", "output").order_by("sequence")
    return [get_cpo_candidate_for_receipt_line(line) for line in lines]


def get_eligible_cpo_candidates(*, legal_entity: LegalEntity | None = None) -> list[CPOCandidate]:
    """Returns CPO candidates for all POSTED production warehouse receipt lines."""
    qs = (
        WarehouseReceiptLine.objects.filter(
            receipt__source_module="production",
            receipt__source_type="PRODUCTION_HANDOVER",
            receipt__state=WarehouseDocumentState.POSTED,
        )
        .select_related(
            "receipt",
            "receipt__legal_entity",
            "receipt__work_order",
            "receipt__work_order__project",
            "receipt__handover",
            "receipt__handover__cpo_beneficiary",
            "item",
            "item__uom",
            "output",
        )
        .order_by("-receipt__receipt_date", "receipt__id", "sequence")
    )
    if legal_entity:
        qs = qs.filter(receipt__legal_entity=legal_entity)

    candidates = []
    for line in qs:
        cand = get_cpo_candidate_for_receipt_line(line)
        if cand.status == "READY":
            candidates.append(cand)
    return candidates
