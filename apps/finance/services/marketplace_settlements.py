"""Finance-owned marketplace settlement and marketplace-balance posting."""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.finance.models import (
    MarketplaceAdjustmentPosting,
    MarketplaceAdjustmentState,
    MarketplaceBalanceDirection,
    MarketplaceBalanceEntry,
    MarketplaceReturnPosting,
    MarketplaceSettlementPosting,
    MarketplaceSettlementState,
    ReceivableEntry,
)
from apps.finance.services.mappings import FinanceMappingError, resolve_account_mapping
from apps.finance.services.posting import post_journal, reverse_journal
from apps.omnichannel.models import OmniReconciliationStatus, OmniSettlement

SETTLEMENT_EVENT_CODE = "OMNI_SETTLEMENT"
_SUPPORTED_FEE_ROLES = {
    "admin": "ADMIN_FEE",
    "admin_fee": "ADMIN_FEE",
    "service": "SERVICE_FEE",
    "service_fee": "SERVICE_FEE",
    "affiliate": "AFFILIATE_FEE",
    "affiliate_fee": "AFFILIATE_FEE",
    "shipping": "SHIPPING_FEE",
    "shipping_fee": "SHIPPING_FEE",
    "sample_program": "SAMPLE_PROGRAM_FEE",
    "sample_program_fee": "SAMPLE_PROGRAM_FEE",
    "ads": "ADS_FEE",
    "ads_fee": "ADS_FEE",
}


def _outcome(status, reason, *, settlement=None):
    result = {"status": status, "reason": reason}
    if settlement is not None:
        result["source_id"] = str(settlement.pk)
        result["source_key"] = settlement.source_identity_key
    return result


def _whole_rupiah(value, *, field, allow_zero=False):
    if value is None:
        raise ValueError(f"{field.upper()}_REQUIRED")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field.upper()}_INVALID") from exc
    if amount != amount.to_integral_value() or amount < 0 or (not allow_zero and amount == 0):
        raise ValueError(f"{field.upper()}_WHOLE_POSITIVE_REQUIRED")
    return amount


def _store_context(store):
    dimension = store.finance_dimension or store.revenue_mapping_key
    if not dimension:
        return None
    return {"STORE": dimension}


def _fee_lines(settlement, candidate):
    """Return source-detail-preserving fee journal lines, never a generic fallback."""
    components = candidate["fee_components"] or {}
    parsed = []
    for raw_type, raw_amount in components.items():
        normalized_type = str(raw_type).strip().lower().replace(" ", "_").replace("-", "_")
        role = _SUPPORTED_FEE_ROLES.get(normalized_type)
        if role is None:
            raise ValueError("UNSUPPORTED_FEE_COMPONENT")
        amount = _whole_rupiah(raw_amount, field=f"fee_{normalized_type}", allow_zero=True)
        if amount:
            parsed.append((role, amount, normalized_type))
    declared_fee = _whole_rupiah(candidate["fee_amount"], field="fee_amount", allow_zero=True)
    total = sum((amount for _, amount, _ in parsed), Decimal("0"))
    if declared_fee != total:
        raise ValueError("FEE_COMPONENTS_DO_NOT_RECONCILE")
    return parsed, total


def _mapping_ready(
    *, legal_entity, accounting_date, context, lines, event_code=SETTLEMENT_EVENT_CODE
):
    try:
        for line in lines:
            resolve_account_mapping(
                legal_entity=legal_entity,
                module_code="OMNI",
                event_code=event_code,
                line_role=line["line_role"],
                dc=line["dc"],
                business_date=accounting_date,
                context=context,
            )
    except FinanceMappingError as exc:
        return str(exc)
    return None


def _settlement_return_match(*, settlement, receivable, refund_amount):
    """Require one prior, unused, exact return before refund evidence may settle."""
    candidates = MarketplaceReturnPosting.objects.select_for_update().filter(
        legal_entity=settlement.legal_entity,
        store=settlement.store,
        receivable=receivable,
        amount=refund_amount,
        state="POSTED",
    )
    used_return_ids = {
        row.source_reference.get("refund_return_posting_id")
        for row in MarketplaceSettlementPosting.objects.filter(legal_entity=settlement.legal_entity)
        if row.source_reference.get("refund_return_posting_id")
    }
    matches = [
        row
        for row in candidates
        if row.source_reference.get("order_id") == str(settlement.matched_revenue.order_id)
        and str(row.pk) not in used_return_ids
    ]
    return matches[0] if len(matches) == 1 else None


def _settlement_adjustment(*, settlement):
    """One linked Omni adjustment is required for each non-zero settlement adjustment amount."""
    from apps.omnichannel.models import OmniAdjustmentSource

    sources = list(
        OmniAdjustmentSource.objects.select_for_update().filter(
            legal_entity=settlement.legal_entity, store=settlement.store, settlement=settlement
        )
    )
    if len(sources) != 1:
        return None
    source = sources[0]
    if source.amount is None or source.amount != settlement.adjustment_amount:
        return None
    if MarketplaceAdjustmentPosting.objects.filter(
        legal_entity=settlement.legal_entity, source_adjustment_identity=source.source_identity_key
    ).exists():
        return None
    return source


@transaction.atomic
def post_marketplace_settlement(settlement, *, actor):
    """Post one eligible Omni settlement, or return an explicit no-side-effect blocker."""
    from apps.omnichannel.services.phase7b import settlement_finance_candidate

    settlement = (
        OmniSettlement.objects.select_for_update()
        .select_related("legal_entity", "store", "matched_revenue")
        .prefetch_related("fees")
        .get(pk=settlement.pk)
    )
    existing = (
        MarketplaceSettlementPosting.objects.select_for_update()
        .filter(
            legal_entity=settlement.legal_entity,
            source_settlement_identity=settlement.source_identity_key,
        )
        .first()
    )
    if existing:
        return existing
    candidate = settlement_finance_candidate(settlement)
    if not settlement.source_identity_key:
        return _outcome(
            "PENDING_SOURCE", "SETTLEMENT_SOURCE_IDENTITY_REQUIRED", settlement=settlement
        )
    if settlement.store_id is None:
        return _outcome("PENDING_SOURCE", "STORE_REQUIRED", settlement=settlement)
    if settlement.settlement_date is None:
        return _outcome("PENDING_SOURCE", "SETTLEMENT_DATE_REQUIRED", settlement=settlement)
    if settlement.matched_revenue_id is None:
        return _outcome("PENDING_SOURCE", "MATCHED_REVENUE_REQUIRED", settlement=settlement)
    if settlement.reconciliation_status in {
        OmniReconciliationStatus.SOURCE_CHANGED,
        OmniReconciliationStatus.SETTLEMENT_UNMATCHED,
    }:
        return _outcome("PENDING_SOURCE", "SETTLEMENT_UNMATCHED_OR_CHANGED", settlement=settlement)
    if settlement.reconciliation_status not in {
        OmniReconciliationStatus.SETTLEMENT_MATCH,
        OmniReconciliationStatus.SETTLEMENT_PARTIAL,
    }:
        return _outcome("PENDING_SOURCE", "SETTLEMENT_NOT_RECONCILED", settlement=settlement)
    revenue = settlement.matched_revenue
    if (
        revenue.legal_entity_id != settlement.legal_entity_id
        or revenue.store_id != settlement.store_id
    ):
        return _outcome("PENDING_SOURCE", "SETTLEMENT_LINEAGE_MISMATCH", settlement=settlement)
    context = _store_context(settlement.store)
    if context is None:
        return _outcome(
            "BLOCKED_MAPPING", "STORE_MAPPING_DIMENSION_REQUIRED", settlement=settlement
        )
    receivable = (
        ReceivableEntry.objects.select_for_update()
        .select_related("journal", "store")
        .filter(
            legal_entity=settlement.legal_entity,
            journal__source_key=f"OMNI_COMPLETION|{revenue.pk}",
        )
        .first()
    )
    if receivable is None:
        return _outcome("PENDING_SOURCE", "MARKETPLACE_RECEIVABLE_REQUIRED", settlement=settlement)
    if receivable.store_id != settlement.store_id:
        return _outcome("PENDING_SOURCE", "RECEIVABLE_STORE_MISMATCH", settlement=settlement)
    if (
        not settlement.currency
        or settlement.currency != receivable.currency
        or settlement.currency != "IDR"
    ):
        return _outcome(
            "PENDING_SOURCE", "SETTLEMENT_CURRENCY_UNSUPPORTED_OR_MISMATCH", settlement=settlement
        )
    if receivable.open_amount <= 0:
        return _outcome("PENDING_SOURCE", "RECEIVABLE_OPEN_AMOUNT_REQUIRED", settlement=settlement)
    try:
        balance_amount = _whole_rupiah(
            settlement.net_amount
            if settlement.net_amount is not None
            else candidate["settled_amount"],
            field="marketplace_balance_amount",
        )
        fees, fee_amount = _fee_lines(settlement, candidate)
    except ValueError as exc:
        return _outcome("PENDING_SOURCE", str(exc), settlement=settlement)
    refund_amount = Decimal(str(candidate["refund_amount"] or 0))
    if refund_amount:
        try:
            refund_amount = _whole_rupiah(refund_amount, field="refund_amount")
        except ValueError as exc:
            return _outcome("PENDING_SOURCE", str(exc), settlement=settlement)
        refund_posting = _settlement_return_match(
            settlement=settlement, receivable=receivable, refund_amount=refund_amount
        )
        if refund_posting is None:
            return _outcome(
                "PENDING_SOURCE", "REFUND_RECONCILIATION_REQUIRED", settlement=settlement
            )
    else:
        refund_posting = None
    adjustment_amount = Decimal(str(candidate["adjustment_amount"] or 0))
    if adjustment_amount:
        try:
            _whole_rupiah(abs(adjustment_amount), field="adjustment_amount")
        except ValueError as exc:
            return _outcome("PENDING_SOURCE", str(exc), settlement=settlement)
        adjustment = _settlement_adjustment(settlement=settlement)
        if adjustment is None:
            return _outcome(
                "PENDING_SOURCE", "ADJUSTMENT_SETTLEMENT_LINK_REQUIRED", settlement=settlement
            )
    else:
        adjustment = None
    ar_cleared = balance_amount + fee_amount + adjustment_amount
    if ar_cleared <= 0:
        return _outcome("PENDING_SOURCE", "SETTLEMENT_AR_CLEARING_REQUIRED", settlement=settlement)
    if ar_cleared > receivable.open_amount:
        return _outcome("PENDING_SOURCE", "AR_OVER_CLEAR", settlement=settlement)
    lines = [{"line_role": "MARKETPLACE_BALANCE", "dc": "DEBIT", "amount": balance_amount}]
    lines.extend({"line_role": role, "dc": "DEBIT", "amount": amount} for role, amount, _ in fees)
    if adjustment_amount:
        lines.append(
            {
                "line_role": "MARKETPLACE_ADJUSTMENT",
                "dc": "DEBIT" if adjustment_amount > 0 else "CREDIT",
                "amount": abs(adjustment_amount),
            }
        )
    lines.append({"line_role": "MARKETPLACE_RECEIVABLE", "dc": "CREDIT", "amount": ar_cleared})
    mapping_error = _mapping_ready(
        legal_entity=settlement.legal_entity,
        accounting_date=settlement.settlement_date,
        context=context,
        lines=lines,
    )
    if mapping_error:
        return _outcome("BLOCKED_MAPPING", mapping_error, settlement=settlement)
    source_reference = {
        "omni_settlement_id": str(settlement.pk),
        "settlement_reference": settlement.settlement_reference,
        "external_order_number": settlement.external_order_number,
        "marketplace": settlement.marketplace,
        "source_lineage": candidate["source_lineage"],
        "refund_return_posting_id": str(refund_posting.pk) if refund_posting else None,
        "adjustment_source_id": str(adjustment.pk) if adjustment else None,
    }
    journal = post_journal(
        legal_entity=settlement.legal_entity,
        source_key=f"OMNI_SETTLEMENT|{settlement.source_identity_key}",
        source_module="OMNI",
        source_document_type="OmniSettlement",
        source_document_id=settlement.pk,
        event_code=SETTLEMENT_EVENT_CODE,
        accounting_date=settlement.settlement_date,
        lines=[{**line, "context": context} for line in lines],
        actor=actor,
        source_reference=source_reference,
        description="Marketplace settlement",
    )
    balance_entry = MarketplaceBalanceEntry.objects.create(
        legal_entity=settlement.legal_entity,
        store=settlement.store,
        journal=journal,
        transaction_date=settlement.settlement_date,
        direction=MarketplaceBalanceDirection.IN,
        amount=balance_amount,
        currency=settlement.currency,
        source_module="OMNI",
        source_document_type="OmniSettlement",
        source_document_id=str(settlement.pk),
        source_key=f"MARKETPLACE_BALANCE|{settlement.source_identity_key}",
        source_reference=source_reference,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    posting = MarketplaceSettlementPosting.objects.create(
        legal_entity=settlement.legal_entity,
        store=settlement.store,
        source_settlement_id=str(settlement.pk),
        source_settlement_identity=settlement.source_identity_key,
        settlement_date=settlement.settlement_date,
        currency=settlement.currency,
        receivable=receivable,
        journal=journal,
        marketplace_balance_entry=balance_entry,
        ar_cleared_amount=ar_cleared,
        marketplace_balance_amount=balance_amount,
        fee_amount=fee_amount,
        fee_components={source_type: str(amount) for _, amount, source_type in fees},
        source_reference=source_reference,
        source_lineage=candidate["source_lineage"],
        posted_by=actor,
        posted_at=timezone.now(),
    )
    if adjustment:
        MarketplaceAdjustmentPosting.objects.create(
            legal_entity=settlement.legal_entity,
            store=settlement.store,
            source_adjustment_id=str(adjustment.pk),
            source_adjustment_identity=adjustment.source_identity_key,
            transaction_date=adjustment.transaction_date,
            signed_amount=adjustment_amount,
            currency=settlement.currency,
            settlement_posting=posting,
            journal=journal,
            source_reference={
                "omni_settlement_id": str(settlement.pk),
                "adjustment_type": adjustment.adjustment_type,
            },
            posted_by=actor,
            posted_at=timezone.now(),
        )
    receivable.open_amount -= ar_cleared
    receivable.save(update_fields=("open_amount", "updated_at"))
    return posting


@transaction.atomic
def reverse_marketplace_settlement(posting, *, actor):
    posting = (
        MarketplaceSettlementPosting.objects.select_for_update()
        .select_related("journal", "marketplace_balance_entry", "receivable", "store")
        .get(pk=posting.pk)
    )
    if hasattr(posting, "reversal"):
        return posting.reversal
    receivable = ReceivableEntry.objects.select_for_update().get(pk=posting.receivable_id)
    journal = reverse_journal(
        posting.journal,
        actor=actor,
        source_key=f"OMNI_SETTLEMENT_JOURNAL_REVERSAL|{posting.pk}",
    )
    source_reference = {"reversal_of_marketplace_settlement_posting_id": str(posting.pk)}
    balance_entry = MarketplaceBalanceEntry.objects.create(
        legal_entity=posting.legal_entity,
        store=posting.store,
        journal=journal,
        transaction_date=posting.settlement_date,
        direction=MarketplaceBalanceDirection.OUT,
        amount=posting.marketplace_balance_amount,
        currency=posting.currency,
        source_module="FINANCE",
        source_document_type="MarketplaceSettlementReversal",
        source_document_id=str(posting.pk),
        source_key=f"MARKETPLACE_BALANCE_REVERSAL|{posting.pk}",
        source_reference=source_reference,
        reversal_of=posting.marketplace_balance_entry,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    reversal = MarketplaceSettlementPosting.objects.create(
        legal_entity=posting.legal_entity,
        store=posting.store,
        source_settlement_id=posting.source_settlement_id,
        source_settlement_identity=f"OMNI_SETTLEMENT_REVERSAL|{posting.pk}",
        settlement_date=posting.settlement_date,
        currency=posting.currency,
        receivable=receivable,
        journal=journal,
        marketplace_balance_entry=balance_entry,
        ar_cleared_amount=posting.ar_cleared_amount,
        marketplace_balance_amount=posting.marketplace_balance_amount,
        fee_amount=posting.fee_amount,
        fee_components=posting.fee_components,
        source_reference=source_reference,
        source_lineage=posting.source_lineage,
        reversal_of=posting,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    receivable.open_amount += posting.ar_cleared_amount
    receivable.save(update_fields=("open_amount", "updated_at"))
    posting.state = MarketplaceSettlementState.REVERSED
    posting.save(update_fields=("state", "updated_at"))
    posting.adjustment_postings.update(state=MarketplaceAdjustmentState.REVERSED)
    return reversal
