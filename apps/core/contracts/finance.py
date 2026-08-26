from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone


@dataclass(frozen=True)
class CustomerFinanceExposure:
    """Future Finance-owned AR exposure projection; never defaults balances to zero."""

    customer_id: object
    legal_entity_id: object
    as_of_date: date
    source_available: bool
    source_name: str
    outstanding: Decimal | None = None
    overdue: Decimal | None = None
    payment_received: Decimal | None = None
    dso_days: Decimal | None = None
    calculated_at: datetime | None = None


def customer_finance_exposure(customer, *, as_of_date=None) -> CustomerFinanceExposure:
    """Default contract until Finance implements an authoritative AR provider."""

    return CustomerFinanceExposure(
        customer_id=customer.pk,
        legal_entity_id=customer.legal_entity_id,
        as_of_date=as_of_date or timezone.localdate(),
        source_available=False,
        source_name="finance_ar_not_implemented",
        calculated_at=timezone.now(),
    )
