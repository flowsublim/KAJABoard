from apps.finance.models import AccountingPeriod
from apps.finance.services.periods import period_control_status


def accounting_periods(*, legal_entity):
    return AccountingPeriod.objects.filter(legal_entity=legal_entity).order_by("start_date")


__all__ = ["accounting_periods", "period_control_status"]
