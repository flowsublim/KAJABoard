from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.services.audit import record_audit_event
from apps.incentives.models import (
    IncentiveAccrual,
    IncentiveAccrualReversal,
    IncentiveAccrualState,
)
from apps.incentives.selectors.evaluation import evaluate_incentive


@transaction.atomic
def accrue_incentive(
    *,
    legal_entity,
    incentive_type: str,
    trigger_type: str,
    business_date,
    source_module: str,
    source_type: str,
    source_document_id: str,
    source_line_id: str = "",
    source_reference: str = "",
    basis_quantity: Decimal | None = None,
    basis_amount: Decimal | None = None,
    beneficiary: Any,
    actor,
    item=None,
    project=None,
    idempotency_key: str | None = None,
) -> IncentiveAccrual:
    """
    Creates an immutable IncentiveAccrual record idempotently.
    """
    source_key = (
        idempotency_key
        or f"{incentive_type}|{source_module}|{source_type}|{source_document_id}|{source_line_id}"
    )

    if basis_quantity is not None:
        basis_quantity = Decimal(str(basis_quantity))

    # Extract beneficiary attributes
    ben_id = (
        getattr(beneficiary, "beneficiary_id", None)
        or getattr(beneficiary, "id", None)
        or (
            beneficiary.get("beneficiary_id") or beneficiary.get("id")
            if isinstance(beneficiary, dict)
            else None
        )
    )

    existing = IncentiveAccrual.objects.filter(source_key=source_key).first()
    if existing:
        # Verify payload consistency
        mismatches = []
        if existing.legal_entity_id != legal_entity.pk:
            mismatches.append("legal_entity")
        if existing.incentive_type != incentive_type:
            mismatches.append("incentive_type")
        if existing.beneficiary_id != str(ben_id):
            mismatches.append("beneficiary_id")
        if existing.item_id != (item.pk if item else None):
            mismatches.append("item")
        if existing.project_id != (project.pk if project else None):
            mismatches.append("project")
        if basis_quantity is not None and existing.basis_quantity != basis_quantity:
            mismatches.append("basis_quantity")
        if basis_amount is not None and existing.basis_amount != basis_amount:
            mismatches.append("basis_amount")

        if mismatches:
            raise ValidationError(
                f"Payload mismatch for existing incentive accrual source_key '{source_key}': "
                f"{', '.join(mismatches)}."
            )
        return existing

    if item and item.legal_entity_id != legal_entity.pk:
        raise ValidationError("Item legal entity must match accrual legal entity.")
    if project and project.legal_entity_id != legal_entity.pk:
        raise ValidationError("Project legal entity must match accrual legal entity.")

    # Evaluation
    result = evaluate_incentive(
        legal_entity=legal_entity,
        incentive_type=incentive_type,
        trigger_type=trigger_type,
        business_date=business_date,
        basis_quantity=basis_quantity,
        basis_amount=basis_amount,
        beneficiary=beneficiary,
        item=item,
        project=project,
    )

    if result.status != "READY":
        raise ValidationError(f"Cannot accrue incentive: {result.reason} ({result.status})")

    accrual = IncentiveAccrual(
        legal_entity=legal_entity,
        incentive_type=incentive_type,
        source_key=source_key,
        source_module=source_module,
        source_type=source_type,
        source_document_id=str(source_document_id),
        source_line_id=str(source_line_id),
        source_reference=str(source_reference),
        accrual_date=business_date,
        project=project,
        item=item,
        rule=result.rule,
        rule_code_snapshot=result.rule.code,
        trigger_snapshot=result.rule.trigger_type,
        calculation_method_snapshot=result.rule.calculation_method,
        rate_snapshot=result.rate_value,
        currency_snapshot=result.currency,
        basis_quantity=result.basis_quantity,
        basis_amount=result.basis_amount,
        beneficiary_type=result.beneficiary_type,
        beneficiary_id=result.beneficiary_id,
        beneficiary_code_snapshot=result.beneficiary_code_snapshot,
        beneficiary_name_snapshot=result.beneficiary_name_snapshot,
        amount=result.calculated_amount,
        state=IncentiveAccrualState.ACCRUED,
        created_by=actor,
    )
    accrual.full_clean()
    accrual.save()

    record_audit_event(
        actor=actor,
        action="INCENTIVE_ACCRUED",
        target_type="IncentiveAccrual",
        target_id=str(accrual.pk),
        source=source_module,
        idempotency_key=source_key,
        after_state=accrual.state,
        metadata={
            "incentive_type": accrual.incentive_type,
            "rule_code": accrual.rule_code_snapshot,
            "amount": str(accrual.amount),
            "currency": accrual.currency_snapshot,
            "beneficiary_id": accrual.beneficiary_id,
            "beneficiary_name": accrual.beneficiary_name_snapshot,
        },
    )

    return accrual


@transaction.atomic
def approve_incentive_accrual(
    accrual: IncentiveAccrual,
    *,
    actor,
) -> IncentiveAccrual:
    """
    Transitions an ACCRUED incentive to APPROVED state.
    Does NOT automatically create Finance accounting.
    """
    if accrual.state != IncentiveAccrualState.ACCRUED:
        raise ValidationError(
            f"Cannot approve incentive accrual in state '{accrual.state}'. "
            "Only ACCRUED can be approved."
        )

    before_state = accrual.state
    accrual.state = IncentiveAccrualState.APPROVED
    accrual.save(update_fields=("state", "updated_at"))

    record_audit_event(
        actor=actor,
        action="INCENTIVE_APPROVED",
        target_type="IncentiveAccrual",
        target_id=str(accrual.pk),
        before_state=before_state,
        after_state=accrual.state,
        metadata={
            "source_key": accrual.source_key,
            "amount": str(accrual.amount),
        },
    )
    return accrual


@transaction.atomic
def reverse_incentive_accrual(
    accrual: IncentiveAccrual,
    *,
    actor,
    reason: str,
) -> IncentiveAccrual:
    """
    Controlled reversal of an ACCRUED or APPROVED incentive accrual.
    Creates an IncentiveAccrualReversal record and sets state to REVERSED.
    Original economic snapshots remain immutable.
    """
    if not reason or not reason.strip():
        raise ValidationError("Reason is required for reversing an incentive accrual.")

    if accrual.state == IncentiveAccrualState.REVERSED or hasattr(accrual, "reversal"):
        raise ValidationError("Incentive accrual is already reversed.")

    if accrual.state not in (
        IncentiveAccrualState.ACCRUED,
        IncentiveAccrualState.APPROVED,
        IncentiveAccrualState.PAYABLE,
        IncentiveAccrualState.PAID,
    ):
        raise ValidationError(f"Cannot reverse incentive accrual in state '{accrual.state}'.")

    before_state = accrual.state
    clean_reason = reason.strip()

    IncentiveAccrualReversal.objects.create(
        accrual=accrual,
        reason=clean_reason,
        reversed_by=actor,
        reversed_at=timezone.now(),
    )

    accrual.state = IncentiveAccrualState.REVERSED
    accrual.save(update_fields=("state", "updated_at"))

    record_audit_event(
        actor=actor,
        action="INCENTIVE_REVERSED",
        target_type="IncentiveAccrual",
        target_id=str(accrual.pk),
        before_state=before_state,
        after_state=accrual.state,
        reason=clean_reason,
        metadata={
            "source_key": accrual.source_key,
            "amount": str(accrual.amount),
        },
    )
    return accrual


@transaction.atomic
def mark_accrual_payable_from_finance(
    accrual: IncentiveAccrual,
    *,
    posting,
    actor,
) -> IncentiveAccrual:
    """Transitions IncentiveAccrual APPROVED -> PAYABLE upon verified Finance posting evidence.

    Incentives domain owns the lifecycle state transition.
    """
    if posting.incentive_accrual_id != accrual.pk:
        raise ValidationError("Finance posting does not match this incentive accrual.")

    locked_accrual = IncentiveAccrual.objects.select_for_update().get(pk=accrual.pk)
    if locked_accrual.state == IncentiveAccrualState.REVERSED:
        raise ValidationError("Cannot transition reversed incentive accrual to PAYABLE.")

    if locked_accrual.state == IncentiveAccrualState.PAYABLE:
        return locked_accrual

    if locked_accrual.state != IncentiveAccrualState.APPROVED:
        raise ValidationError(
            f"Cannot mark accrual as PAYABLE from state '{locked_accrual.state}'. "
            "Must be in APPROVED state."
        )

    before_state = locked_accrual.state
    locked_accrual.state = IncentiveAccrualState.PAYABLE
    locked_accrual.save(update_fields=("state", "updated_at"))

    record_audit_event(
        actor=actor,
        action="INCENTIVE_STATE_PAYABLE",
        target_type="IncentiveAccrual",
        target_id=str(locked_accrual.pk),
        source="incentives.services.accruals",
        before_state=before_state,
        after_state=locked_accrual.state,
        idempotency_key=posting.source_key,
        metadata={
            "finance_posting_id": str(posting.pk),
            "amount": str(locked_accrual.amount),
        },
    )
    return locked_accrual


@transaction.atomic
def mark_accrual_paid_from_finance(
    accrual: IncentiveAccrual,
    *,
    posting,
    actor,
) -> IncentiveAccrual:
    """Transitions IncentiveAccrual PAYABLE -> PAID upon verified full settlement evidence.

    Incentives domain owns the lifecycle state transition.
    """
    if posting.incentive_accrual_id != accrual.pk:
        raise ValidationError("Finance posting does not match this incentive accrual.")

    locked_accrual = IncentiveAccrual.objects.select_for_update().get(pk=accrual.pk)
    if locked_accrual.state == IncentiveAccrualState.REVERSED:
        return locked_accrual

    if locked_accrual.state == IncentiveAccrualState.PAID:
        return locked_accrual

    if locked_accrual.state != IncentiveAccrualState.PAYABLE:
        raise ValidationError(
            f"Cannot mark accrual as PAID from state '{locked_accrual.state}'. "
            "Must be in PAYABLE state."
        )

    from apps.finance.models import PayableEntry

    payable = PayableEntry.objects.select_for_update().get(pk=posting.payable_entry_id)
    if payable.open_amount != Decimal("0"):
        raise ValidationError(
            f"Cannot mark accrual as PAID: payable still has open amount {payable.open_amount}."
        )

    before_state = locked_accrual.state
    locked_accrual.state = IncentiveAccrualState.PAID
    locked_accrual.save(update_fields=("state", "updated_at"))

    record_audit_event(
        actor=actor,
        action="INCENTIVE_STATE_PAID",
        target_type="IncentiveAccrual",
        target_id=str(locked_accrual.pk),
        source="incentives.services.accruals",
        before_state=before_state,
        after_state=locked_accrual.state,
        metadata={
            "finance_posting_id": str(posting.pk),
            "amount": str(locked_accrual.amount),
        },
        reason="Incentive payable fully settled (open_amount == 0)",
    )
    return locked_accrual


@transaction.atomic
def reopen_accrual_payable_from_finance(
    accrual: IncentiveAccrual,
    *,
    posting,
    actor,
) -> IncentiveAccrual:
    """Transitions IncentiveAccrual PAID -> PAYABLE upon verified payment reversal evidence.

    Incentives domain owns the lifecycle state transition.
    """
    if posting.incentive_accrual_id != accrual.pk:
        raise ValidationError("Finance posting does not match this incentive accrual.")

    locked_accrual = IncentiveAccrual.objects.select_for_update().get(pk=accrual.pk)
    if locked_accrual.state == IncentiveAccrualState.REVERSED:
        return locked_accrual

    if locked_accrual.state == IncentiveAccrualState.PAYABLE:
        return locked_accrual

    if locked_accrual.state != IncentiveAccrualState.PAID:
        raise ValidationError(
            f"Cannot reopen accrual to PAYABLE from state '{locked_accrual.state}'. "
            "Must be in PAID state."
        )

    from apps.finance.models import PayableEntry

    payable = PayableEntry.objects.select_for_update().get(pk=posting.payable_entry_id)
    if payable.open_amount <= Decimal("0"):
        raise ValidationError(
            f"Cannot reopen accrual to PAYABLE: payable has no open amount ({payable.open_amount})."
        )

    before_state = locked_accrual.state
    locked_accrual.state = IncentiveAccrualState.PAYABLE
    locked_accrual.save(update_fields=("state", "updated_at"))

    record_audit_event(
        actor=actor,
        action="INCENTIVE_STATE_REOPENED",
        target_type="IncentiveAccrual",
        target_id=str(locked_accrual.pk),
        source="incentives.services.accruals",
        before_state=before_state,
        after_state=locked_accrual.state,
        metadata={
            "finance_posting_id": str(posting.pk),
            "amount": str(locked_accrual.amount),
        },
        reason="Payment reversed; incentive payable reopened (open_amount > 0)",
    )
    return locked_accrual
