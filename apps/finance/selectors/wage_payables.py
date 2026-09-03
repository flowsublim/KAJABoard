from decimal import Decimal

from apps.finance.models import JournalLine, JournalState, WagePayableAccrual, WagePayableState


def wage_payables(*, legal_entity):
    return WagePayableAccrual.objects.filter(legal_entity=legal_entity).select_related(
        "payable_entry", "journal"
    )


def wage_payable_detail(accrual):
    return {
        "accrual": accrual,
        "payable": accrual.payable_entry,
        "open_amount": accrual.payable_entry.open_amount,
    }


def wage_payable_reconciliation(*, legal_entity):
    active = wage_payables(legal_entity=legal_entity).filter(state=WagePayableState.POSTED)
    detail = sum((row.payable_entry.open_amount for row in active), Decimal("0"))
    lines = JournalLine.objects.filter(
        journal__legal_entity=legal_entity, line_role="WAGE_PAYABLE"
    ).filter(journal__state__in=(JournalState.POSTED, JournalState.REVERSED))
    control = sum((line.credit - line.debit for line in lines), Decimal("0"))
    has_source = (
        active.exists()
        or WagePayableAccrual.objects.filter(
            legal_entity=legal_entity, state=WagePayableState.REVERSED
        ).exists()
    )
    return {
        "status": "MATCH"
        if has_source and control == detail
        else "DIFFERENCE"
        if has_source
        else "PENDING_SOURCE",
        "control": control,
        "detail": detail,
    }
