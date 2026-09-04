"""Read-only finance reconciliation selector for Incentive Accruals and Payable Postings."""

from dataclasses import dataclass
from decimal import Decimal

from apps.finance.models import IncentivePayablePosting, IncentivePostingState
from apps.incentives.models import IncentiveAccrual, IncentiveAccrualState


@dataclass(frozen=True)
class IncentivePayableReconciliationItem:
    accrual_id: str
    business_state: str
    has_finance_posting: bool
    posting_state: str | None
    payable_original_amount: Decimal | None
    payable_open_amount: Decimal | None
    payment_status: str
    source_reversed: bool
    accounting_reversal_required: bool
    accounting_posting_missing: bool
    reconciliation_status: str
    beneficiary_type: str
    beneficiary_id: str
    beneficiary_code: str
    beneficiary_name: str
    project_reference: str
    source_reference: str


def get_incentive_payable_status(
    accrual: IncentiveAccrual,
) -> IncentivePayableReconciliationItem:
    """Evaluates the finance accounting and settlement reconciliation
    status for an IncentiveAccrual.
    """
    posting = getattr(accrual, "finance_posting", None)
    if not posting:
        posting = (
            IncentivePayablePosting.objects.filter(incentive_accrual=accrual)
            .select_related("payable_entry", "journal")
            .first()
        )

    has_posting = posting is not None
    posting_state = posting.state if posting else None

    payable = posting.payable_entry if posting else None
    orig_amount = payable.original_amount if payable else None
    open_amount = payable.open_amount if payable else None

    if not has_posting:
        payment_status = "NOT_POSTED"
    elif open_amount == Decimal("0"):
        payment_status = "PAID"
    elif open_amount < orig_amount:
        payment_status = "PARTIALLY_PAID"
    else:
        payment_status = "UNPAID"

    source_reversed = accrual.state == IncentiveAccrualState.REVERSED or hasattr(
        accrual, "reversal"
    )
    accounting_reversal_required = (
        source_reversed and has_posting and posting_state == IncentivePostingState.POSTED
    )
    accounting_posting_missing = accrual.state == IncentiveAccrualState.APPROVED and not has_posting

    # Reconciliation status
    if source_reversed:
        if has_posting and posting_state == IncentivePostingState.POSTED:
            recon_status = "SOURCE_REVERSED_FINANCE_REVERSAL_PENDING"
        else:
            recon_status = "REVERSED"
    elif not has_posting:
        if accrual.state == IncentiveAccrualState.APPROVED:
            recon_status = "APPROVED_NOT_POSTED"
        else:
            recon_status = "PENDING_APPROVAL"
    else:
        if posting_state == IncentivePostingState.REVERSED:
            recon_status = "REVERSED"
        elif payment_status == "PAID":
            recon_status = "PAID"
        elif payment_status == "PARTIALLY_PAID":
            recon_status = "PARTIALLY_PAID"
        else:
            recon_status = "PAYABLE_OPEN"

    return IncentivePayableReconciliationItem(
        accrual_id=str(accrual.pk),
        business_state=accrual.state,
        has_finance_posting=has_posting,
        posting_state=posting_state,
        payable_original_amount=orig_amount,
        payable_open_amount=open_amount,
        payment_status=payment_status,
        source_reversed=source_reversed,
        accounting_reversal_required=accounting_reversal_required,
        accounting_posting_missing=accounting_posting_missing,
        reconciliation_status=recon_status,
        beneficiary_type=accrual.beneficiary_type,
        beneficiary_id=accrual.beneficiary_id,
        beneficiary_code=accrual.beneficiary_code_snapshot,
        beneficiary_name=accrual.beneficiary_name_snapshot,
        project_reference=str(accrual.project.pk) if accrual.project else "",
        source_reference=accrual.source_reference,
    )
