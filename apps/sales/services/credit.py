from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CreditCheckContext:
    """Read-only Phase 3A hook; Finance exposure is intentionally not fabricated here."""

    credit_limit: Decimal
    finance_exposure_available: bool = False
    outstanding_exposure: Decimal | None = None


def customer_credit_check_context(customer) -> CreditCheckContext:
    return CreditCheckContext(credit_limit=customer.credit_limit)
