"""Authoritative CPO Finished Goods Fee accrual and reversal services.

Consumes authoritative WarehouseReceiptLine source facts.
Strictly zero Finance journals, payments, or Warehouse stock mutations.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.incentives.models import (
    BeneficiaryKind,
    IncentiveAccrual,
    IncentiveAccrualState,
    IncentiveTriggerType,
    IncentiveType,
)
from apps.incentives.selectors.cpo import get_cpo_candidate_for_receipt_line
from apps.incentives.services.accruals import accrue_incentive, reverse_incentive_accrual
from apps.warehouse.models import WarehouseReceipt, WarehouseReceiptLine


@transaction.atomic
def accrue_cpo_fee_for_receipt_line(
    receipt_line: WarehouseReceiptLine,
    *,
    actor,
) -> IncentiveAccrual:
    """Creates or idempotently returns an IncentiveAccrual for a single POSTED WarehouseReceiptLine.

    Requires an authoritative finished goods receipt and explicit production handover beneficiary.
    Amount is strictly whole-Rupiah based on line.accepted_quantity.
    Zero Finance posting or stock mutation.
    """
    cand = get_cpo_candidate_for_receipt_line(receipt_line)

    if cand.existing_accrual:
        return cand.existing_accrual

    if cand.status != "READY":
        raise ValidationError(
            f"Cannot accrue CPO fee for receipt line {receipt_line.pk}: "
            f"{cand.reason} ({cand.status})"
        )

    accrual = accrue_incentive(
        legal_entity=cand.legal_entity,
        incentive_type=IncentiveType.CPO_FEE,
        trigger_type=IncentiveTriggerType.FINISHED_GOODS_ACCEPTED,
        business_date=cand.receipt_date,
        source_module="warehouse",
        source_type="WAREHOUSE_RECEIPT_LINE",
        source_document_id=cand.receipt_id,
        source_line_id=cand.receipt_line_id,
        source_reference=f"Receipt {cand.receipt_id} Line {cand.receipt_line_id}",
        basis_quantity=cand.accepted_quantity,
        beneficiary={
            "beneficiary_type": cand.beneficiary_type or BeneficiaryKind.EMPLOYEE,
            "beneficiary_id": cand.beneficiary_id,
            "beneficiary_code": cand.beneficiary_code,
            "beneficiary_name": cand.beneficiary_name,
        },
        item=cand.item,
        project=cand.project,
        idempotency_key=cand.source_key,
        actor=actor,
    )
    return accrual


@transaction.atomic
def accrue_cpo_fees_for_receipt(
    receipt: WarehouseReceipt,
    *,
    actor,
) -> list[IncentiveAccrual]:
    """Accrues CPO fees for all lines of a POSTED WarehouseReceipt."""
    accruals = []
    lines = receipt.lines.all().order_by("sequence")
    for line in lines:
        accruals.append(accrue_cpo_fee_for_receipt_line(line, actor=actor))
    return accruals


@transaction.atomic
def reverse_cpo_fee_for_receipt_line(
    receipt_line: WarehouseReceiptLine,
    *,
    actor,
    reason: str = "Warehouse receipt reversed",
) -> IncentiveAccrual | None:
    """Idempotently reverses any existing CPO IncentiveAccrual for the given receipt line.

    Preserves original accrual record; creates IncentiveAccrualReversal.
    Duplicate calls are idempotent and return the reversed accrual without error
    or duplicate reversal records.
    """
    source_key = f"CPO_FEE|warehouse|WAREHOUSE_RECEIPT_LINE|{receipt_line.pk}"
    accrual = IncentiveAccrual.objects.select_for_update().filter(source_key=source_key).first()
    if not accrual:
        return None

    if accrual.state == IncentiveAccrualState.REVERSED:
        return accrual

    return reverse_incentive_accrual(accrual, actor=actor, reason=reason)


@transaction.atomic
def reverse_cpo_fees_for_receipt(
    receipt: WarehouseReceipt,
    *,
    actor,
    reason: str = "Warehouse receipt reversed",
) -> list[IncentiveAccrual]:
    """Reverses all CPO fee accruals associated with lines of the given receipt."""
    reversed_accruals = []
    lines = receipt.lines.all().order_by("sequence")
    for line in lines:
        acc = reverse_cpo_fee_for_receipt_line(line, actor=actor, reason=reason)
        if acc:
            reversed_accruals.append(acc)
    return reversed_accruals
