from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.contracts.finance import customer_finance_exposure
from apps.core.services.audit import record_audit_event
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.sales.models import CreditControlStatus, SalesOrderCreditControl, SalesOrderState


@dataclass(frozen=True)
class CreditCheckContext:
    """Read-only credit context with explicitly non-authoritative unavailable Finance values."""

    credit_limit: Decimal
    finance_exposure_available: bool = False
    outstanding_exposure: Decimal | None = None
    overdue_exposure: Decimal | None = None
    available_credit: Decimal | None = None
    source_name: str = "finance_ar_not_implemented"


@dataclass(frozen=True)
class CreditDecision:
    status: str
    should_hold: bool
    context: CreditCheckContext
    order_exposure: Decimal


def customer_credit_check_context(customer, *, as_of_date=None) -> CreditCheckContext:
    exposure = customer_finance_exposure(customer, as_of_date=as_of_date)
    if not exposure.source_available or exposure.outstanding is None:
        return CreditCheckContext(
            credit_limit=customer.credit_limit,
            source_name=exposure.source_name,
        )
    available_credit = None
    if customer.credit_limit > 0:
        available_credit = customer.credit_limit - exposure.outstanding
    return CreditCheckContext(
        credit_limit=customer.credit_limit,
        finance_exposure_available=True,
        outstanding_exposure=exposure.outstanding,
        overdue_exposure=exposure.overdue,
        available_credit=available_credit,
        source_name=exposure.source_name,
    )


def evaluate_sales_order_credit(order) -> CreditDecision:
    context = customer_credit_check_context(order.customer, as_of_date=order.document_date)
    order_exposure = Decimal(order.grand_total)
    if not context.finance_exposure_available:
        return CreditDecision(
            status=CreditControlStatus.NOT_AVAILABLE,
            should_hold=False,
            context=context,
            order_exposure=order_exposure,
        )
    if context.credit_limit <= 0:
        return CreditDecision(
            status=CreditControlStatus.NOT_CONFIGURED,
            should_hold=False,
            context=context,
            order_exposure=order_exposure,
        )
    should_hold = (
        context.outstanding_exposure or Decimal("0")
    ) + order_exposure > context.credit_limit
    return CreditDecision(
        status=CreditControlStatus.HELD if should_hold else CreditControlStatus.PASSED,
        should_hold=should_hold,
        context=context,
        order_exposure=order_exposure,
    )


def _audit(control, *, action, actor=None, reason="", before=None):
    after = model_snapshot(control)
    record_audit_event(
        action=action,
        target_type=control._meta.label_lower,
        target_id=control.pk,
        actor=actor,
        source="sales.credit_service",
        reason=reason,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after) if before else sorted(after),
    )


def record_sales_order_credit_control(order, *, actor=None) -> SalesOrderCreditControl:
    """Persist the confirmation-time Finance contract response without creating AR."""

    decision = evaluate_sales_order_credit(order)
    context = decision.context
    control, _ = SalesOrderCreditControl.objects.update_or_create(
        sales_order=order,
        defaults={
            "customer": order.customer,
            "legal_entity": order.legal_entity,
            "status": decision.status,
            "credit_limit_snapshot": context.credit_limit,
            "outstanding_snapshot": context.outstanding_exposure,
            "order_exposure_snapshot": decision.order_exposure,
            "source_available": context.finance_exposure_available,
            "source_name": context.source_name,
            "evaluated_at": timezone.now(),
            "evaluated_by": actor,
        },
    )
    _audit(control, action="sales.salesordercreditcontrol.evaluated", actor=actor)
    return control


@transaction.atomic
def override_sales_order_credit_hold(order, *, actor=None, reason=""):
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Credit override reason is required."})
    locked_order = order.__class__.objects.select_for_update().get(pk=order.pk)
    if locked_order.state != SalesOrderState.ON_HOLD:
        raise ValidationError("Only ON_HOLD Sales Orders can receive a credit override.")
    control = SalesOrderCreditControl.objects.select_for_update().get(sales_order=locked_order)
    if control.status != CreditControlStatus.HELD:
        raise ValidationError("This Sales Order is not held by an authoritative credit evaluation.")
    before = model_snapshot(control)
    control.status = CreditControlStatus.OVERRIDDEN
    control.override_reason = str(reason).strip()
    control.overridden_by = actor
    control.overridden_at = timezone.now()
    control.save()
    _audit(
        control,
        action="sales.salesordercreditcontrol.overridden",
        actor=actor,
        reason=reason,
        before=before,
    )
    locked_order.state = SalesOrderState.CONFIRMED
    locked_order.save(update_fields=("state", "updated_at"))
    return locked_order
