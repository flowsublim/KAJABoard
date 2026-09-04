from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from apps.incentives.models import (
    BeneficiaryKind,
    IncentiveCalculationMethod,
    IncentiveRule,
)
from apps.incentives.selectors.rules import resolve_incentive_rule


@dataclass(frozen=True)
class IncentiveEvaluationResult:
    status: str
    rule: IncentiveRule | None = None
    rate_value: Decimal | None = None
    calculation_method: str | None = None
    currency: str = "IDR"
    basis_quantity: Decimal | None = None
    basis_amount: Decimal | None = None
    calculated_amount: Decimal | None = None
    beneficiary_type: str | None = None
    beneficiary_id: str | None = None
    beneficiary_code_snapshot: str = ""
    beneficiary_name_snapshot: str = ""
    reason: str = ""


def evaluate_incentive(
    *,
    legal_entity,
    incentive_type,
    trigger_type,
    business_date,
    basis_quantity: Decimal | None = None,
    basis_amount: Decimal | None = None,
    beneficiary: Any = None,
    item=None,
    project=None,
) -> IncentiveEvaluationResult:
    """
    Pure read-only calculation and contract evaluation.
    Produces zero database mutations.
    """
    # 1. Beneficiary contract validation
    if not beneficiary:
        return IncentiveEvaluationResult(
            status="PENDING_BENEFICIARY",
            reason="Beneficiary contract is required.",
        )

    # Beneficiary may be dict or object with kind/id/code/name
    ben_type = (
        getattr(beneficiary, "beneficiary_type", None)
        or (beneficiary.get("beneficiary_type") if isinstance(beneficiary, dict) else None)
        or BeneficiaryKind.EMPLOYEE
    )
    ben_id = (
        getattr(beneficiary, "beneficiary_id", None)
        or getattr(beneficiary, "id", None)
        or (
            beneficiary.get("beneficiary_id") or beneficiary.get("id")
            if isinstance(beneficiary, dict)
            else None
        )
    )
    ben_code = (
        getattr(beneficiary, "beneficiary_code", None)
        or getattr(beneficiary, "code", "")
        or (
            beneficiary.get("beneficiary_code") or beneficiary.get("code", "")
            if isinstance(beneficiary, dict)
            else ""
        )
    )
    ben_name = (
        getattr(beneficiary, "beneficiary_name", None)
        or getattr(beneficiary, "name", "")
        or getattr(beneficiary, "display_name", "")
        or (
            beneficiary.get("beneficiary_name")
            or beneficiary.get("name")
            or beneficiary.get("display_name", "")
            if isinstance(beneficiary, dict)
            else ""
        )
    )

    if not ben_id:
        return IncentiveEvaluationResult(
            status="PENDING_BENEFICIARY",
            reason="Beneficiary identity is required.",
        )

    # Validate legal entity consistency
    if item and item.legal_entity_id != legal_entity.pk:
        return IncentiveEvaluationResult(
            status="INVALID_CONTEXT",
            reason="Item legal entity must match evaluation legal entity.",
        )
    if project and project.legal_entity_id != legal_entity.pk:
        return IncentiveEvaluationResult(
            status="INVALID_CONTEXT",
            reason="Project legal entity must match evaluation legal entity.",
        )

    # 2. Rule resolution
    rule_status, rule = resolve_incentive_rule(
        legal_entity=legal_entity,
        incentive_type=incentive_type,
        trigger_type=trigger_type,
        target_date=business_date,
        item=item,
    )

    if rule_status == "AMBIGUOUS_RULE":
        return IncentiveEvaluationResult(
            status="AMBIGUOUS_RULE",
            beneficiary_type=str(ben_type),
            beneficiary_id=str(ben_id),
            beneficiary_code_snapshot=str(ben_code),
            beneficiary_name_snapshot=str(ben_name),
            reason="Multiple active overlapping rules found for context and date.",
        )

    if rule_status == "PENDING_RULE" or rule is None:
        return IncentiveEvaluationResult(
            status="PENDING_RULE",
            beneficiary_type=str(ben_type),
            beneficiary_id=str(ben_id),
            beneficiary_code_snapshot=str(ben_code),
            beneficiary_name_snapshot=str(ben_name),
            reason="No active effective incentive rule found for context and date.",
        )

    # 3. Calculation method evaluation
    if rule.calculation_method == IncentiveCalculationMethod.PER_UNIT:
        if basis_quantity is None:
            return IncentiveEvaluationResult(
                status="INVALID_BASIS",
                rule=rule,
                reason="basis_quantity is required for PER_UNIT calculation.",
            )
        if basis_quantity < Decimal("0"):
            return IncentiveEvaluationResult(
                status="INVALID_BASIS",
                rule=rule,
                reason="basis_quantity cannot be negative.",
            )

        raw_amount = basis_quantity * rule.rate_value
        if raw_amount % Decimal("1") != Decimal("0"):
            return IncentiveEvaluationResult(
                status="NON_WHOLE_RUPIAH_RESULT",
                rule=rule,
                rate_value=rule.rate_value,
                calculation_method=rule.calculation_method,
                basis_quantity=basis_quantity,
                reason=f"Calculated amount ({raw_amount}) is fractional Rupiah.",
            )

        calculated_amount = raw_amount.quantize(Decimal("1"))

    elif rule.calculation_method == IncentiveCalculationMethod.FIXED:
        raw_amount = rule.rate_value
        if raw_amount % Decimal("1") != Decimal("0"):
            return IncentiveEvaluationResult(
                status="NON_WHOLE_RUPIAH_RESULT",
                rule=rule,
                rate_value=rule.rate_value,
                calculation_method=rule.calculation_method,
                reason=f"Fixed rate ({raw_amount}) is fractional Rupiah.",
            )

        calculated_amount = raw_amount.quantize(Decimal("1"))

    else:
        return IncentiveEvaluationResult(
            status="UNSUPPORTED_METHOD",
            rule=rule,
            rate_value=rule.rate_value,
            calculation_method=rule.calculation_method,
            reason=f"Calculation method {rule.calculation_method} is not supported in Phase 9B1.",
        )

    return IncentiveEvaluationResult(
        status="READY",
        rule=rule,
        rate_value=rule.rate_value,
        calculation_method=rule.calculation_method,
        currency=rule.currency,
        basis_quantity=basis_quantity,
        basis_amount=basis_amount,
        calculated_amount=calculated_amount,
        beneficiary_type=str(ben_type),
        beneficiary_id=str(ben_id),
        beneficiary_code_snapshot=str(ben_code),
        beneficiary_name_snapshot=str(ben_name),
        reason="",
    )
