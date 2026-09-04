"""Finance-owned incentive payable posting, reversal, and payment synchronization services."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.services.audit import record_audit_event
from apps.finance.models import (
    IncentivePayablePosting,
    IncentivePostingState,
    JournalLine,
    PayableEntry,
)
from apps.finance.services.periods import assert_posting_period_open
from apps.finance.services.posting import post_journal, reverse_journal
from apps.incentives.models import (
    IncentiveAccrual,
    IncentiveAccrualState,
    IncentiveType,
)


@transaction.atomic
def post_incentive_payable(
    accrual: IncentiveAccrual,
    *,
    actor,
    accounting_date=None,
) -> IncentivePayablePosting:
    """Finance-posts an APPROVED IncentiveAccrual into a balanced JournalEntry and PayableEntry.

    Strictly atomic:
    - Resolves semantic mapping: Dr CPO_FEE_COST, Cr INCENTIVE_PAYABLE
    - Blocks if missing/ambiguous mapping or closed accounting period
    - Leaves PayableEntry.partner NULL for Employee beneficiaries
    - Transitions IncentiveAccrual: APPROVED -> PAYABLE
    - Deterministic and idempotent
    """
    locked_accrual = (
        IncentiveAccrual.objects.select_for_update()
        .select_related("legal_entity", "project")
        .get(pk=accrual.pk)
    )

    if locked_accrual.incentive_type != IncentiveType.CPO_FEE:
        raise ValidationError("Only CPO_FEE incentive accruals can be posted in this phase.")

    if locked_accrual.state == IncentiveAccrualState.REVERSED or hasattr(
        locked_accrual, "reversal"
    ):
        raise ValidationError("Cannot Finance-post a reversed incentive accrual.")

    amount = locked_accrual.amount
    if amount <= Decimal("0") or amount != amount.to_integral_value():
        raise ValidationError("Incentive accrual amount must be a positive whole Rupiah.")

    source_key = f"INCENTIVE_PAYABLE|{locked_accrual.pk}"
    existing = (
        IncentivePayablePosting.objects.select_for_update().filter(source_key=source_key).first()
    )
    if existing:
        if (
            existing.amount != amount
            or existing.legal_entity_id != locked_accrual.legal_entity_id
            or existing.state == IncentivePostingState.REVERSED
        ):
            raise ValidationError(
                "Mismatched or reversed data for existing incentive payable posting."
            )
        return existing

    if locked_accrual.state != IncentiveAccrualState.APPROVED:
        raise ValidationError(
            f"Cannot Finance-post incentive accrual in state '{locked_accrual.state}'. "
            "Must be in APPROVED state."
        )

    acct_date = accounting_date or locked_accrual.accrual_date
    assert_posting_period_open(legal_entity=locked_accrual.legal_entity, accounting_date=acct_date)

    entity = locked_accrual.legal_entity
    context = {}

    journal = post_journal(
        legal_entity=entity,
        source_key=f"INCENTIVE_PAYABLE_JOURNAL|{locked_accrual.pk}",
        source_module="FINANCE",
        source_document_type="IncentivePayablePosting",
        source_document_id=str(locked_accrual.pk),
        event_code="INCENTIVE_CPO_FEE_PAYABLE",
        accounting_date=acct_date,
        actor=actor,
        source_reference={
            "incentive_accrual_id": str(locked_accrual.pk),
            "source_reference": locked_accrual.source_reference,
            "accrual_date": locked_accrual.accrual_date.isoformat(),
        },
        description=f"Incentive payable posting for {locked_accrual.rule_code_snapshot}",
        lines=(
            {
                "line_role": "CPO_FEE_COST",
                "dc": "DEBIT",
                "amount": amount,
                "context": context,
            },
            {
                "line_role": "INCENTIVE_PAYABLE",
                "dc": "CREDIT",
                "amount": amount,
                "context": context,
            },
        ),
    )

    payable = PayableEntry.objects.create(
        journal=journal,
        legal_entity=entity,
        accounting_date=acct_date,
        original_amount=amount,
        open_amount=amount,
        currency=locked_accrual.currency_snapshot or "IDR",
        partner=None,
    )

    posting = IncentivePayablePosting.objects.create(
        legal_entity=entity,
        incentive_accrual=locked_accrual,
        incentive_type_snapshot=locked_accrual.incentive_type,
        source_key=source_key,
        accounting_date=acct_date,
        amount=amount,
        currency=locked_accrual.currency_snapshot or "IDR",
        beneficiary_type=locked_accrual.beneficiary_type,
        beneficiary_id=locked_accrual.beneficiary_id,
        beneficiary_code_snapshot=locked_accrual.beneficiary_code_snapshot,
        beneficiary_name_snapshot=locked_accrual.beneficiary_name_snapshot,
        source_reference=locked_accrual.source_reference,
        project_reference=str(locked_accrual.project.pk) if locked_accrual.project else "",
        journal=journal,
        payable_entry=payable,
        state=IncentivePostingState.POSTED,
        posted_by=actor,
        posted_at=timezone.now(),
        metadata={
            "rule_code": locked_accrual.rule_code_snapshot,
            "basis_quantity": str(locked_accrual.basis_quantity),
        },
    )

    from apps.incentives.services.accruals import mark_accrual_payable_from_finance

    mark_accrual_payable_from_finance(locked_accrual, posting=posting, actor=actor)

    record_audit_event(
        actor=actor,
        action="FINANCE_INCENTIVE_PAYABLE_POSTED",
        target_type="IncentivePayablePosting",
        target_id=str(posting.pk),
        source="finance.services.incentive_payables",
        idempotency_key=source_key,
        after_state=posting.state,
        metadata={
            "journal_id": str(journal.pk),
            "payable_id": str(payable.pk),
            "amount": str(amount),
        },
    )

    return posting


@transaction.atomic
def reverse_incentive_payable_posting(
    posting: IncentivePayablePosting,
    *,
    actor,
    accounting_date=None,
):
    """Reverses an unpaid IncentivePayablePosting.

    Case A: payable is completely unpaid (open_amount == original_amount).
            Finance reverses original journal, closes payable open_amount to 0,
            and marks IncentivePayablePosting as REVERSED.
    Case B: payable is partially paid or fully paid (open_amount < original_amount).
            Blocks explicitly with ValidationError (PAYABLE_ALREADY_SETTLED).
    """
    posting = (
        IncentivePayablePosting.objects.select_for_update()
        .select_related("journal", "payable_entry", "legal_entity")
        .get(pk=posting.pk)
    )

    if posting.state == IncentivePostingState.REVERSED:
        return getattr(posting.journal, "reversal", None)

    payable = PayableEntry.objects.select_for_update().get(pk=posting.payable_entry_id)
    if payable.open_amount != payable.original_amount:
        raise ValidationError(
            "PAYABLE_ALREADY_SETTLED: Paid or partially paid incentive payable "
            "cannot be reversed. Finance correction required."
        )

    acct_date = accounting_date or posting.accounting_date
    assert_posting_period_open(legal_entity=posting.legal_entity, accounting_date=acct_date)

    reversal = reverse_journal(
        posting.journal,
        actor=actor,
        source_key=f"INCENTIVE_PAYABLE_REVERSAL|{posting.pk}",
        accounting_date=acct_date,
    )

    payable.open_amount = Decimal("0")
    payable.save(update_fields=("open_amount", "updated_at"))

    posting.state = IncentivePostingState.REVERSED
    posting.save(update_fields=("state", "updated_at"))

    record_audit_event(
        actor=actor,
        action="FINANCE_INCENTIVE_PAYABLE_REVERSED",
        target_type="IncentivePayablePosting",
        target_id=str(posting.pk),
        source="finance.services.incentive_payables",
        idempotency_key=f"INCENTIVE_PAYABLE_REVERSAL|{posting.pk}",
        after_state=posting.state,
        metadata={
            "reversal_journal_id": str(reversal.pk) if reversal else "",
            "amount": str(posting.amount),
        },
    )

    return reversal


def incentive_payable_control_snapshot(payable: PayableEntry):
    """Returns the original INCENTIVE_PAYABLE control account mapping snapshot
    from the accrual journal.
    """
    return JournalLine.objects.get(
        journal=payable.journal, line_role="INCENTIVE_PAYABLE"
    ).mapping_snapshot


@transaction.atomic
def sync_incentive_accrual_payment_state(
    posting: IncentivePayablePosting,
    *,
    actor=None,
) -> IncentiveAccrual:
    """Synchronizes IncentiveAccrual state (PAYABLE vs PAID) based on PayableEntry.open_amount.

    - open_amount == 0: PAID
    - open_amount > 0 and previously PAID: reverts to PAYABLE
    - open_amount > 0 and PAYABLE: remains PAYABLE
    - If underlying accrual is REVERSED, state is preserved.
    """
    payable = PayableEntry.objects.select_for_update().get(pk=posting.payable_entry_id)
    accrual = IncentiveAccrual.objects.select_for_update().get(pk=posting.incentive_accrual_id)

    if accrual.state == IncentiveAccrualState.REVERSED:
        return accrual

    from apps.incentives.services.accruals import (
        mark_accrual_paid_from_finance,
        reopen_accrual_payable_from_finance,
    )

    if payable.open_amount == Decimal("0"):
        if accrual.state != IncentiveAccrualState.PAID:
            return mark_accrual_paid_from_finance(accrual, posting=posting, actor=actor)
    else:
        if accrual.state == IncentiveAccrualState.PAID:
            return reopen_accrual_payable_from_finance(accrual, posting=posting, actor=actor)

    return accrual


@transaction.atomic
def post_incentive_payment(
    *,
    legal_entity,
    liquidity_account,
    payable: PayableEntry,
    payment_date,
    source_key: str,
    actor,
    amount: Decimal | None = None,
    source_reference: dict | None = None,
):
    """Semantic wrapper around Finance payment engine for Incentive Payable settlement.

    Uses:
    - source_document_type = "IncentivePayment"
    - source_module = "FINANCE"
    - description = "Incentive payment"
    - partner = None (preserves partner=NULL for Employee beneficiaries)
    - Allocates to payable and synchronizes IncentiveAccrual state
    - Reuses existing Payment ledger without duplication
    """
    if not hasattr(payable, "incentive_posting"):
        raise ValidationError("PayableEntry is not linked to an IncentivePayablePosting.")

    locked_payable = PayableEntry.objects.select_for_update().get(pk=payable.pk)
    if locked_payable.open_amount <= Decimal("0"):
        raise ValidationError("PayableEntry is already fully settled.")

    pay_amount = amount or locked_payable.open_amount
    if pay_amount <= Decimal("0") or pay_amount > locked_payable.open_amount:
        raise ValidationError(
            f"Invalid payment amount {pay_amount}. Open amount is {locked_payable.open_amount}."
        )

    ref = {
        "incentive_posting_id": str(locked_payable.incentive_posting.pk),
        **(source_reference or {}),
    }

    from apps.finance.services.payments import post_vendor_payment

    return post_vendor_payment(
        legal_entity=legal_entity,
        liquidity_account=liquidity_account,
        allocations=({"payable": locked_payable, "amount": pay_amount},),
        payment_date=payment_date,
        source_key=source_key,
        actor=actor,
        currency=locked_payable.currency,
        source_module="FINANCE",
        source_document_type="IncentivePayment",
        source_document_id=source_key,
        source_reference=ref,
        partner=None,
        description="Incentive payment",
    )
