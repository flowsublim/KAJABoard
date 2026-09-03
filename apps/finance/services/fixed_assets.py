"""Finance-owned fixed asset register and straight-line depreciation services."""

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.finance.models import (
    DepreciationScheduleEntry,
    DepreciationScheduleState,
    FixedAsset,
    FixedAssetState,
)
from apps.finance.services.posting import post_journal, reverse_journal


def asset_acquisition_readiness(source):
    """PO commitments cannot capitalize an asset before an approved acquisition source exists."""
    if not source or not source.get("approved"):
        return {"status": "PENDING_SOURCE", "reason": "APPROVED_ASSET_ACQUISITION_REQUIRED"}
    return {"status": "READY"}


def _whole(value, field):
    amount = Decimal(str(value))
    if amount != amount.to_integral_value() or amount < 0:
        raise ValidationError({field: "Amount must be whole Rupiah."})
    return amount


@transaction.atomic
def capitalize_fixed_asset(
    *,
    asset_class,
    name,
    acquisition_date,
    capitalization_date,
    acquisition_cost,
    residual_value=0,
    useful_life_months=None,
    source=None,
    actor=None,
    description="",
):
    readiness = asset_acquisition_readiness(source)
    if readiness["status"] != "READY":
        return readiness
    cost, residual = (
        _whole(acquisition_cost, "acquisition_cost"),
        _whole(residual_value, "residual_value"),
    )
    if cost <= 0 or residual >= cost:
        raise ValidationError("Asset cost must exceed non-negative residual value.")
    if (
        acquisition_date is None
        or capitalization_date is None
        or capitalization_date < acquisition_date
    ):
        raise ValidationError("Valid acquisition and capitalization dates are required.")
    life = useful_life_months or asset_class.default_useful_life_months
    if life <= 0:
        raise ValidationError("Useful life must be positive.")
    source_key = source["source_key"]
    existing = (
        FixedAsset.objects.select_for_update()
        .filter(legal_entity=asset_class.legal_entity, source_key=source_key)
        .first()
    )
    if existing:
        return existing
    journal = post_journal(
        legal_entity=asset_class.legal_entity,
        source_key=f"FIXED_ASSET|{source_key}",
        source_module="FINANCE",
        source_document_type="FixedAssetAcquisition",
        source_document_id=source.get("source_document_id", source_key),
        event_code="PURCH_ASSET_PURCHASE",
        accounting_date=capitalization_date,
        lines=[
            {
                "line_role": "FIXED_ASSET",
                "dc": "DEBIT",
                "amount": cost,
                "context": {"PURCHASE_CATEGORY": asset_class.mapping_key},
            },
            {
                "line_role": "ACQUISITION_CLEARING",
                "dc": "CREDIT",
                "amount": cost,
                "context": {"PURCHASE_CATEGORY": asset_class.mapping_key},
            },
        ],
        actor=actor,
        source_reference=source,
        description="Fixed asset capitalization",
    )
    return FixedAsset.objects.create(
        legal_entity=asset_class.legal_entity,
        asset_number=f"FA-{source_key}"[:80],
        asset_class=asset_class,
        name=name,
        description=description,
        acquisition_date=acquisition_date,
        capitalization_date=capitalization_date,
        acquisition_cost=cost,
        residual_value=residual,
        useful_life_months=life,
        depreciation_method=asset_class.default_depreciation_method,
        source_module=source.get("source_module", "FINANCE"),
        source_document_type=source.get("source_document_type", "ApprovedAssetAcquisition"),
        source_document_id=source.get("source_document_id", source_key),
        source_key=source_key,
        source_reference=source,
        capitalization_journal=journal,
        posted_by=actor,
        posted_at=timezone.now(),
    )


def _month(date_value, offset):
    index = date_value.month - 1 + offset
    year, month = date_value.year + index // 12, index % 12 + 1
    return date(year, month, monthrange(year, month)[1])


@transaction.atomic
def generate_depreciation_schedule(asset):
    asset = FixedAsset.objects.select_for_update().get(pk=asset.pk)
    basis = asset.depreciable_amount
    base, remainder = divmod(int(basis), asset.useful_life_months)
    for offset in range(asset.useful_life_months):
        amount = Decimal(base + (remainder if offset == asset.useful_life_months - 1 else 0))
        if not amount:
            continue
        period = _month(asset.capitalization_date, offset + 1)
        DepreciationScheduleEntry.objects.get_or_create(
            fixed_asset=asset,
            period_date=period,
            defaults={
                "scheduled_amount": amount,
                "source_key": f"DEPRECIATION|{asset.pk}|{period.isoformat()}",
            },
        )
    return asset.schedule_entries.order_by("period_date")


@transaction.atomic
def post_depreciation(entry, *, actor):
    entry = (
        DepreciationScheduleEntry.objects.select_for_update()
        .select_related("fixed_asset__asset_class")
        .get(pk=entry.pk)
    )
    if entry.state == DepreciationScheduleState.POSTED:
        return entry
    asset = FixedAsset.objects.select_for_update().get(pk=entry.fixed_asset_id)
    if asset.state in {FixedAssetState.DISPOSED, FixedAssetState.REVERSED}:
        return {"status": "PENDING_SOURCE", "reason": "ASSET_NOT_DEPRECIABLE"}
    if entry.period_date <= asset.capitalization_date:
        return {"status": "PENDING_SOURCE", "reason": "PRE_CAPITALIZATION_PERIOD"}
    journal = post_journal(
        legal_entity=asset.legal_entity,
        source_key=entry.source_key,
        source_module="FINANCE",
        source_document_type="Depreciation",
        source_document_id=str(entry.pk),
        event_code="FIXED_ASSET_DEPRECIATION",
        accounting_date=entry.period_date,
        lines=[
            {
                "line_role": "DEPRECIATION_EXPENSE",
                "dc": "DEBIT",
                "amount": entry.scheduled_amount,
                "context": {"PURCHASE_CATEGORY": asset.asset_class.mapping_key},
            },
            {
                "line_role": "ACCUMULATED_DEPRECIATION",
                "dc": "CREDIT",
                "amount": entry.scheduled_amount,
                "context": {"PURCHASE_CATEGORY": asset.asset_class.mapping_key},
            },
        ],
        actor=actor,
        source_reference={"fixed_asset_id": str(asset.pk)},
        description="Asset depreciation",
    )
    entry.journal, entry.state = journal, DepreciationScheduleState.POSTED
    entry.save(update_fields=("journal", "state", "updated_at"))
    if (
        sum(
            (
                row.scheduled_amount
                for row in asset.schedule_entries.filter(state=DepreciationScheduleState.POSTED)
            ),
            Decimal("0"),
        )
        >= asset.depreciable_amount
    ):
        asset.state = FixedAssetState.FULLY_DEPRECIATED
        asset.save(update_fields=("state", "updated_at"))
    return entry


@transaction.atomic
def reverse_depreciation(entry, *, actor):
    entry = (
        DepreciationScheduleEntry.objects.select_for_update()
        .select_related("journal", "fixed_asset")
        .get(pk=entry.pk)
    )
    if entry.state == DepreciationScheduleState.REVERSED:
        return entry.journal.reversal
    if entry.state != DepreciationScheduleState.POSTED:
        raise ValidationError("Only posted depreciation may be reversed.")
    reversal = reverse_journal(
        entry.journal, actor=actor, source_key=f"{entry.source_key}|REVERSAL"
    )
    entry.state = DepreciationScheduleState.REVERSED
    entry.save(update_fields=("state", "updated_at"))
    entry.fixed_asset.state = FixedAssetState.ACTIVE
    entry.fixed_asset.save(update_fields=("state", "updated_at"))
    return reversal
