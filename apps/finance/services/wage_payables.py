"""Finance-owned wage-payable accruals from explicit Production source contracts."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.finance.models import JournalLine, PayableEntry, WagePayableAccrual, WagePayableState
from apps.finance.services.posting import post_journal, reverse_journal

_EVENT_ROLES = {
    "PROD_DIRECT_LABOR": "PRODUCTION_DIRECT_LABOR",
    "PROD_EXTRA_OPERATOR_COST": "PRODUCTION_EXTRA_OPERATOR_COST",
}


def wage_payable_source_readiness(source):
    """Validate only immutable, explicit payable facts; never infer from descriptions."""
    if not isinstance(source, dict):
        return {"status": "PENDING_SOURCE", "reason": "AUTHORITATIVE_SOURCE_REQUIRED"}
    required = (
        "legal_entity",
        "source_key",
        "source_type",
        "source_id",
        "accrual_date",
        "amount",
        "production_lineage",
        "payable_treatment",
    )
    missing = [field for field in required if not source.get(field)]
    if missing:
        return {"status": "PENDING_SOURCE", "reason": f"MISSING_SOURCE_FACTS:{','.join(missing)}"}
    if source["payable_treatment"] != "WAGE_PAYABLE":
        return {"status": "PENDING_SOURCE", "reason": "PAYABLE_TREATMENT_NOT_AUTHORIZED"}
    event_code = source.get("event_code")
    if event_code not in _EVENT_ROLES or source.get("debit_line_role") != _EVENT_ROLES[event_code]:
        return {"status": "PENDING_SOURCE", "reason": "PRODUCTION_COST_CLASSIFICATION_REQUIRED"}
    amount = Decimal(str(source["amount"]))
    if amount <= 0 or amount != amount.to_integral_value():
        return {"status": "PENDING_SOURCE", "reason": "WHOLE_RUPIAH_AMOUNT_REQUIRED"}
    return {"status": "READY", "amount": amount}


@transaction.atomic
def accrue_wage_payable(*, source, actor):
    readiness = wage_payable_source_readiness(source)
    if readiness["status"] != "READY":
        return readiness
    entity = source["legal_entity"]
    existing = (
        WagePayableAccrual.objects.select_for_update()
        .filter(legal_entity=entity, source_key=source["source_key"])
        .first()
    )
    if existing:
        return existing
    context = source.get("mapping_context", {})
    amount = readiness["amount"]
    journal = post_journal(
        legal_entity=entity,
        source_key=f"WAGE_ACCRUAL|{source['source_key']}",
        source_module="FINANCE",
        source_document_type="WagePayableAccrual",
        source_document_id=str(source["source_id"]),
        event_code=source["event_code"],
        accounting_date=source["accrual_date"],
        actor=actor,
        source_reference=source.get("source_reference", {}),
        description="Production wage payable accrual",
        lines=(
            {
                "line_role": source["debit_line_role"],
                "dc": "DEBIT",
                "amount": amount,
                "context": context,
            },
            {"line_role": "WAGE_PAYABLE", "dc": "CREDIT", "amount": amount, "context": context},
        ),
    )
    payable = PayableEntry.objects.create(
        journal=journal,
        legal_entity=entity,
        accounting_date=source["accrual_date"],
        original_amount=amount,
        open_amount=amount,
        currency=source.get("currency", "IDR"),
    )
    return WagePayableAccrual.objects.create(
        legal_entity=entity,
        source_module=source.get("source_module", "PRODUCTION"),
        source_type=source["source_type"],
        source_id=str(source["source_id"]),
        source_key=source["source_key"],
        source_reference=source.get("source_reference", {}),
        production_lineage=source["production_lineage"],
        beneficiary_reference=source.get("beneficiary_reference", ""),
        accrual_date=source["accrual_date"],
        amount=amount,
        currency=source.get("currency", "IDR"),
        debit_line_role=source["debit_line_role"],
        mapping_context=context,
        journal=journal,
        payable_entry=payable,
        posted_by=actor,
        posted_at=timezone.now(),
    )


@transaction.atomic
def reverse_wage_payable(accrual, *, actor, accounting_date=None):
    accrual = (
        WagePayableAccrual.objects.select_for_update()
        .select_related("journal", "payable_entry")
        .get(pk=accrual.pk)
    )
    if accrual.state == WagePayableState.REVERSED:
        return accrual.journal.reversal
    payable = PayableEntry.objects.select_for_update().get(pk=accrual.payable_entry_id)
    if payable.open_amount != payable.original_amount:
        raise ValidationError(
            "PAYABLE_ALREADY_SETTLED: Paid or partially paid wage payable cannot be reversed."
        )
    reversal = reverse_journal(
        accrual.journal,
        actor=actor,
        source_key=f"WAGE_ACCRUAL_REVERSAL|{accrual.pk}",
        accounting_date=accounting_date,
    )
    payable.open_amount = Decimal("0")
    payable.save(update_fields=("open_amount", "updated_at"))
    accrual.state = WagePayableState.REVERSED
    accrual.save(update_fields=("state", "updated_at"))
    return reversal


def wage_payable_control_snapshot(payable):
    return JournalLine.objects.get(
        journal=payable.journal, line_role="WAGE_PAYABLE"
    ).mapping_snapshot
