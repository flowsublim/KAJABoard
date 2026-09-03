from decimal import Decimal

from apps.finance.models import (
    DepreciationScheduleEntry,
    DepreciationScheduleState,
    FixedAsset,
    JournalLine,
    JournalState,
)
from apps.finance.selectors.ledger import general_ledger


def fixed_assets(*, legal_entity):
    return FixedAsset.objects.filter(legal_entity=legal_entity).select_related(
        "asset_class", "capitalization_journal"
    )


def fixed_asset_detail(asset):
    entries = asset.schedule_entries.select_related("journal").order_by("period_date")
    accumulated = sum(
        (row.scheduled_amount for row in entries if row.state == DepreciationScheduleState.POSTED),
        Decimal("0"),
    )
    return {
        "asset": asset,
        "schedule": entries,
        "accumulated_depreciation": accumulated,
        "net_book_value": asset.acquisition_cost - accumulated,
    }


def depreciation_schedule(*, fixed_asset):
    return fixed_asset.schedule_entries.select_related("journal").order_by("period_date")


def fixed_asset_reconciliation(*, legal_entity):
    """Read-only control facts; register and schedule remain the detail source."""
    assets = fixed_assets(legal_entity=legal_entity)
    lines = general_ledger(legal_entity=legal_entity)
    # The GL selector intentionally omits reversed journals from its ordinary
    # presentation.  A control balance must retain a reversed original when
    # its posted compensating reversal is present, so its historical debit or
    # credit is netted against the reversal rather than discarded.
    reversed_lines = JournalLine.objects.filter(
        journal__legal_entity=legal_entity,
        journal__state=JournalState.REVERSED,
        journal__reversal__state=JournalState.POSTED,
    ).select_related("journal", "account")
    control_lines = [*lines, *reversed_lines]
    acquisition_detail = sum((asset.acquisition_cost for asset in assets), Decimal("0"))
    acquisition_control = sum(
        (line.debit - line.credit for line in control_lines if line.line_role == "FIXED_ASSET"),
        Decimal("0"),
    )
    depreciation_detail = sum(
        (
            row.scheduled_amount
            for asset in assets
            for row in asset.schedule_entries.all()
            if row.state == DepreciationScheduleState.POSTED
        ),
        Decimal("0"),
    )
    accumulated_control = sum(
        (
            line.credit - line.debit
            for line in control_lines
            if line.line_role == "ACCUMULATED_DEPRECIATION"
        ),
        Decimal("0"),
    )

    def fact(control, detail, *, has_effectively_reversed_history=False):
        has_fact = bool(control or detail or has_effectively_reversed_history)
        return {
            "status": "MATCH"
            if control == detail and has_fact
            else "DIFFERENCE"
            if has_fact
            else "PENDING_SOURCE",
            "control": control,
            "detail": detail,
        }

    acquisition = fact(acquisition_control, acquisition_detail)
    accumulated = fact(
        accumulated_control,
        depreciation_detail,
        has_effectively_reversed_history=DepreciationScheduleEntry.objects.filter(
            fixed_asset__legal_entity=legal_entity,
            state=DepreciationScheduleState.REVERSED,
        ).exists(),
    )
    return {
        "acquisition": acquisition,
        "accumulated_depreciation": accumulated,
        "net_book_value": acquisition_detail - depreciation_detail,
    }
