"""Activated accounting-period controls for Finance posting services."""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.services.audit import record_audit_event
from apps.finance.models import AccountingPeriod, AccountingPeriodState


def period_control_status(*, legal_entity, accounting_date=None):
    periods = AccountingPeriod.objects.filter(legal_entity=legal_entity)
    result = {"activated": periods.exists(), "status": "NOT_CONFIGURED", "period": None}
    if not result["activated"]:
        return result
    if accounting_date is None:
        return {**result, "status": "CONFIGURED"}
    period = periods.filter(start_date__lte=accounting_date, end_date__gte=accounting_date).first()
    if period is None:
        return {**result, "status": "PERIOD_NOT_CONFIGURED"}
    return {**result, "status": period.state, "period": period}


def assert_posting_period_open(*, legal_entity, accounting_date):
    """Compatibility policy: enforcement starts only after an entity has a period."""
    status = period_control_status(legal_entity=legal_entity, accounting_date=accounting_date)
    if not status["activated"]:
        return None
    if status["status"] == AccountingPeriodState.OPEN:
        return status["period"]
    if status["status"] == AccountingPeriodState.CLOSED:
        raise ValidationError("PERIOD_CLOSED: Finance posting is blocked for this date.")
    raise ValidationError("PERIOD_NOT_CONFIGURED: No accounting period covers this date.")


@transaction.atomic
def create_accounting_period(
    *, legal_entity, fiscal_year, period_number, start_date, end_date, actor=None, notes=""
):
    overlap = AccountingPeriod.objects.select_for_update().filter(
        legal_entity=legal_entity, start_date__lte=end_date, end_date__gte=start_date
    )
    if overlap.exists():
        raise ValidationError("Accounting periods may not overlap for a legal entity.")
    period = AccountingPeriod.objects.create(
        legal_entity=legal_entity,
        fiscal_year=fiscal_year,
        period_number=period_number,
        start_date=start_date,
        end_date=end_date,
        changed_by=actor,
        notes=notes,
    )
    record_audit_event(
        action="finance.accountingperiod.created",
        target_type=period._meta.label_lower,
        target_id=period.pk,
        actor=actor,
        source="finance.service",
        reason=notes,
    )
    return period


@transaction.atomic
def close_accounting_period(period, *, actor, reason):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to close an accounting period."})
    period = AccountingPeriod.objects.select_for_update().get(pk=period.pk)
    if period.state == AccountingPeriodState.CLOSED:
        return period
    period.state = AccountingPeriodState.CLOSED
    period.changed_by = actor
    period.notes = reason
    period.save(update_fields=("state", "changed_by", "notes", "updated_at"))
    record_audit_event(
        action="finance.accountingperiod.closed",
        target_type=period._meta.label_lower,
        target_id=period.pk,
        actor=actor,
        source="finance.service",
        reason=reason,
    )
    return period
