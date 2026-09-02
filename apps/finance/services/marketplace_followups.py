"""Finance follow-up postings for marketplace returns and payouts.

The adjustment convention is deliberately normalized: a positive source amount is a
marketplace deduction/cost (debit); a negative source amount is a marketplace credit.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.finance.models import (
    LiquidityAccountType,
    LiquidityDirection,
    LiquidityEntry,
    MarketplaceBalanceDirection,
    MarketplaceBalanceEntry,
    MarketplaceFollowupState,
    MarketplacePayoutPosting,
    MarketplaceReturnPosting,
    MarketplaceReturnTreatment,
    MarketplaceSettlementPosting,
    ReceivableEntry,
)
from apps.finance.services.liquidity import liquidity_mapping_context
from apps.finance.services.marketplace_settlements import (
    _mapping_ready,
    _store_context,
    _whole_rupiah,
)
from apps.finance.services.payments import _validate_liquidity_account
from apps.finance.services.posting import post_journal, reverse_journal


def _outcome(status, reason, source):
    return {
        "status": status,
        "reason": reason,
        "source_id": str(source.pk),
        "source_key": source.source_identity_key,
    }


def _balance_entries_for_update(*, legal_entity, store, currency):
    return list(
        MarketplaceBalanceEntry.objects.select_for_update()
        .filter(legal_entity=legal_entity, store=store, currency=currency)
        .order_by("transaction_date", "posted_at", "pk")
    )


def _balance_available(*, legal_entity, store, currency):
    return sum(
        (
            entry.amount if entry.direction == MarketplaceBalanceDirection.IN else -entry.amount
            for entry in _balance_entries_for_update(
                legal_entity=legal_entity, store=store, currency=currency
            )
        ),
        Decimal("0"),
    )


@transaction.atomic
def post_marketplace_return(source, *, actor):
    """Post a linked financial return without creating stock or modifying Omni source data."""
    from apps.omnichannel.models import OmniReturnLinkageStatus, OmniReturnSource
    from apps.omnichannel.services.phase7b import return_finance_candidate

    source = (
        OmniReturnSource.objects.select_for_update()
        .select_related("legal_entity", "store", "original_order")
        .get(pk=source.pk)
    )
    existing = (
        MarketplaceReturnPosting.objects.select_for_update()
        .filter(legal_entity=source.legal_entity, source_return_identity=source.source_identity_key)
        .first()
    )
    if existing:
        return existing
    candidate = return_finance_candidate(source)
    if source.linkage_status != OmniReturnLinkageStatus.MATCHED:
        return _outcome("PENDING_SOURCE", "RETURN_SOURCE_UNMATCHED", source)
    if not source.source_identity_key or source.store_id is None:
        return _outcome("PENDING_SOURCE", "RETURN_STORE_OR_IDENTITY_REQUIRED", source)
    if not candidate["revenue_event_id"] or not candidate["transaction_date"]:
        return _outcome("PENDING_SOURCE", "RETURN_REVENUE_OR_DATE_REQUIRED", source)
    if not source.currency:
        return _outcome("PENDING_SOURCE", "RETURN_CURRENCY_REQUIRED", source)
    context = _store_context(source.store)
    if context is None:
        return _outcome("BLOCKED_MAPPING", "STORE_MAPPING_DIMENSION_REQUIRED", source)
    try:
        amount = _whole_rupiah(candidate["amount"], field="refund_amount")
    except ValueError as exc:
        return _outcome("PENDING_SOURCE", str(exc), source)
    receivable = (
        ReceivableEntry.objects.select_for_update()
        .select_related("journal")
        .filter(
            legal_entity=source.legal_entity,
            journal__source_key=f"OMNI_COMPLETION|{candidate['revenue_event_id']}",
        )
        .first()
    )
    if receivable is None or receivable.store_id != source.store_id:
        return _outcome("PENDING_SOURCE", "RETURN_RECEIVABLE_LINEAGE_REQUIRED", source)
    if receivable.currency != source.currency:
        return _outcome("PENDING_SOURCE", "RETURN_CURRENCY_MISMATCH", source)
    if receivable.open_amount >= amount:
        treatment = MarketplaceReturnTreatment.RECEIVABLE_CREDIT
        credit_role = "MARKETPLACE_RECEIVABLE"
    elif receivable.open_amount == 0:
        if (
            _balance_available(
                legal_entity=source.legal_entity, store=source.store, currency=source.currency
            )
            < amount
        ):
            return _outcome("PENDING_SOURCE", "MARKETPLACE_BALANCE_INSUFFICIENT", source)
        treatment = MarketplaceReturnTreatment.MARKETPLACE_BALANCE_CREDIT
        credit_role = "MARKETPLACE_BALANCE"
    else:
        return _outcome("PENDING_SOURCE", "MIXED_REFUND_FUNDING_UNRESOLVED", source)
    lines = [
        {"line_role": "SALES_RETURN", "dc": "DEBIT", "amount": amount},
        {"line_role": credit_role, "dc": "CREDIT", "amount": amount},
    ]
    mapping_error = _mapping_ready(
        legal_entity=source.legal_entity,
        accounting_date=candidate["transaction_date"],
        context=context,
        lines=lines,
        event_code="OMNI_RETURN",
    )
    if mapping_error:
        return _outcome("BLOCKED_MAPPING", mapping_error, source)
    reference = {
        "omni_return_id": str(source.pk),
        "order_id": candidate["order_id"],
        "revenue_event_id": candidate["revenue_event_id"],
        "source_lineage": candidate["source_lineage"],
    }
    journal = post_journal(
        legal_entity=source.legal_entity,
        source_key=f"OMNI_RETURN|{source.source_identity_key}",
        source_module="OMNI",
        source_document_type="OmniReturnSource",
        source_document_id=source.pk,
        event_code="OMNI_RETURN",
        accounting_date=candidate["transaction_date"],
        lines=[{**line, "context": context} for line in lines],
        actor=actor,
        source_reference=reference,
        description="Marketplace return/refund",
    )
    balance_entry = None
    if treatment == MarketplaceReturnTreatment.MARKETPLACE_BALANCE_CREDIT:
        balance_entry = MarketplaceBalanceEntry.objects.create(
            legal_entity=source.legal_entity,
            store=source.store,
            journal=journal,
            transaction_date=candidate["transaction_date"],
            direction=MarketplaceBalanceDirection.OUT,
            amount=amount,
            currency=source.currency,
            source_module="OMNI",
            source_document_type="OmniReturnSource",
            source_document_id=str(source.pk),
            source_key=f"MARKETPLACE_BALANCE_RETURN|{source.source_identity_key}",
            source_reference=reference,
            posted_by=actor,
            posted_at=timezone.now(),
        )
    posting = MarketplaceReturnPosting.objects.create(
        legal_entity=source.legal_entity,
        store=source.store,
        source_return_id=str(source.pk),
        source_return_identity=source.source_identity_key,
        transaction_date=candidate["transaction_date"],
        amount=amount,
        currency=source.currency,
        receivable=receivable,
        revenue_journal=receivable.journal,
        journal=journal,
        marketplace_balance_entry=balance_entry,
        treatment=treatment,
        source_reference=reference,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    if treatment == MarketplaceReturnTreatment.RECEIVABLE_CREDIT:
        receivable.open_amount -= amount
        receivable.save(update_fields=("open_amount", "updated_at"))
    return posting


@transaction.atomic
def reverse_marketplace_return(posting, *, actor):
    posting = (
        MarketplaceReturnPosting.objects.select_for_update()
        .select_related("journal", "receivable", "marketplace_balance_entry", "store")
        .get(pk=posting.pk)
    )
    if hasattr(posting, "reversal"):
        return posting.reversal
    receivable = ReceivableEntry.objects.select_for_update().get(pk=posting.receivable_id)
    journal = reverse_journal(
        posting.journal, actor=actor, source_key=f"OMNI_RETURN_REVERSAL|{posting.pk}"
    )
    reference = {"reversal_of_marketplace_return_posting_id": str(posting.pk)}
    balance_entry = None
    if posting.treatment == MarketplaceReturnTreatment.MARKETPLACE_BALANCE_CREDIT:
        balance_entry = MarketplaceBalanceEntry.objects.create(
            legal_entity=posting.legal_entity,
            store=posting.store,
            journal=journal,
            transaction_date=posting.transaction_date,
            direction=MarketplaceBalanceDirection.IN,
            amount=posting.amount,
            currency=posting.currency,
            source_module="FINANCE",
            source_document_type="MarketplaceReturnReversal",
            source_document_id=str(posting.pk),
            source_key=f"MARKETPLACE_BALANCE_RETURN_REVERSAL|{posting.pk}",
            source_reference=reference,
            reversal_of=posting.marketplace_balance_entry,
            posted_by=actor,
            posted_at=timezone.now(),
        )
    reversal = MarketplaceReturnPosting.objects.create(
        legal_entity=posting.legal_entity,
        store=posting.store,
        source_return_id=posting.source_return_id,
        source_return_identity=f"OMNI_RETURN_REVERSAL|{posting.pk}",
        transaction_date=posting.transaction_date,
        amount=posting.amount,
        currency=posting.currency,
        receivable=receivable,
        revenue_journal=posting.revenue_journal,
        journal=journal,
        marketplace_balance_entry=balance_entry,
        treatment=posting.treatment,
        source_reference=reference,
        reversal_of=posting,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    if posting.treatment == MarketplaceReturnTreatment.RECEIVABLE_CREDIT:
        receivable.open_amount += posting.amount
        receivable.save(update_fields=("open_amount", "updated_at"))
    posting.state = MarketplaceFollowupState.REVERSED
    posting.save(update_fields=("state", "updated_at"))
    return reversal


@transaction.atomic
def post_marketplace_payout(payout_source, *, liquidity_account, actor):
    from apps.omnichannel.models import OmniPayoutSource, OmniReconciliationStatus, OmniSettlement

    source = (
        OmniPayoutSource.objects.select_for_update()
        .select_related("legal_entity", "store")
        .get(pk=payout_source.pk)
    )
    existing = (
        MarketplacePayoutPosting.objects.select_for_update()
        .filter(legal_entity=source.legal_entity, source_payout_identity=source.source_identity_key)
        .first()
    )
    if existing:
        return existing
    if not source.store_id or not source.source_identity_key or not source.payout_date:
        return _outcome("PENDING_SOURCE", "PAYOUT_SOURCE_INCOMPLETE", source)
    if source.reconciliation_status != OmniReconciliationStatus.PAYOUT_MATCH:
        return _outcome("PENDING_SOURCE", "PAYOUT_REFERENCES_UNRESOLVED", source)
    if not source.settlement_references or not source.currency:
        return _outcome("PENDING_SOURCE", "PAYOUT_REFERENCES_OR_CURRENCY_REQUIRED", source)
    try:
        amount = _whole_rupiah(source.amount, field="payout_amount")
    except ValueError as exc:
        return _outcome("PENDING_SOURCE", str(exc), source)
    account = _validate_liquidity_account(
        liquidity_account, legal_entity=source.legal_entity, payment_date=source.payout_date
    )
    if account.account_type != LiquidityAccountType.BANK:
        return _outcome("PENDING_SOURCE", "PAYOUT_BANK_LIQUIDITY_REQUIRED", source)
    if account.currency != source.currency:
        return _outcome("PENDING_SOURCE", "PAYOUT_CURRENCY_MISMATCH", source)
    settlements = list(
        OmniSettlement.objects.filter(
            legal_entity=source.legal_entity,
            store=source.store,
            settlement_reference__in=source.settlement_references,
        )
    )
    if len({row.settlement_reference for row in settlements}) != len(
        set(source.settlement_references)
    ):
        return _outcome("PENDING_SOURCE", "PAYOUT_SETTLEMENT_REFERENCES_UNRESOLVED", source)
    settlement_postings = list(
        MarketplaceSettlementPosting.objects.select_for_update().filter(
            legal_entity=source.legal_entity,
            store=source.store,
            state="POSTED",
            source_settlement_identity__in=[row.source_identity_key for row in settlements],
        )
    )
    if len(settlement_postings) != len(settlements):
        return _outcome("PENDING_SOURCE", "PAYOUT_SETTLEMENT_POSTINGS_REQUIRED", source)
    if (
        _balance_available(
            legal_entity=source.legal_entity, store=source.store, currency=source.currency
        )
        < amount
    ):
        return _outcome("PENDING_SOURCE", "MARKETPLACE_BALANCE_INSUFFICIENT", source)
    context = {**(_store_context(source.store) or {}), **liquidity_mapping_context(account)}
    if not _store_context(source.store):
        return _outcome("BLOCKED_MAPPING", "STORE_MAPPING_DIMENSION_REQUIRED", source)
    lines = [
        {"line_role": "LIQUIDITY", "dc": "DEBIT", "amount": amount},
        {"line_role": "MARKETPLACE_BALANCE", "dc": "CREDIT", "amount": amount},
    ]
    mapping_error = _mapping_ready(
        legal_entity=source.legal_entity,
        accounting_date=source.payout_date,
        context=context,
        lines=lines,
        event_code="OMNI_PAYOUT",
    )
    if mapping_error:
        return _outcome("BLOCKED_MAPPING", mapping_error, source)
    reference = {
        "omni_payout_id": str(source.pk),
        "settlement_references": source.settlement_references,
    }
    journal = post_journal(
        legal_entity=source.legal_entity,
        source_key=f"OMNI_PAYOUT|{source.source_identity_key}",
        source_module="OMNI",
        source_document_type="OmniPayoutSource",
        source_document_id=source.pk,
        event_code="OMNI_PAYOUT",
        accounting_date=source.payout_date,
        lines=[{**line, "context": context} for line in lines],
        actor=actor,
        source_reference=reference,
        description="Marketplace payout",
    )
    balance_entry = MarketplaceBalanceEntry.objects.create(
        legal_entity=source.legal_entity,
        store=source.store,
        journal=journal,
        transaction_date=source.payout_date,
        direction=MarketplaceBalanceDirection.OUT,
        amount=amount,
        currency=source.currency,
        source_module="OMNI",
        source_document_type="OmniPayoutSource",
        source_document_id=str(source.pk),
        source_key=f"MARKETPLACE_BALANCE_PAYOUT|{source.source_identity_key}",
        source_reference=reference,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    liquidity_entry = LiquidityEntry.objects.create(
        legal_entity=source.legal_entity,
        liquidity_account=account,
        journal=journal,
        transaction_date=source.payout_date,
        direction=LiquidityDirection.IN,
        amount=amount,
        currency=source.currency,
        source_module="OMNI",
        source_document_type="OmniPayoutSource",
        source_document_id=str(source.pk),
        source_key=f"LIQUIDITY_PAYOUT|{source.source_identity_key}",
        source_reference=reference,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    return MarketplacePayoutPosting.objects.create(
        legal_entity=source.legal_entity,
        store=source.store,
        source_payout_id=str(source.pk),
        source_payout_identity=source.source_identity_key,
        payout_reference=source.payout_reference,
        payout_date=source.payout_date,
        amount=amount,
        currency=source.currency,
        liquidity_account=account,
        journal=journal,
        marketplace_balance_entry=balance_entry,
        liquidity_entry=liquidity_entry,
        source_reference=reference,
        posted_by=actor,
        posted_at=timezone.now(),
    )


@transaction.atomic
def reverse_marketplace_payout(posting, *, actor):
    posting = (
        MarketplacePayoutPosting.objects.select_for_update()
        .select_related(
            "journal", "liquidity_account", "marketplace_balance_entry", "liquidity_entry", "store"
        )
        .get(pk=posting.pk)
    )
    if hasattr(posting, "reversal"):
        return posting.reversal
    journal = reverse_journal(
        posting.journal, actor=actor, source_key=f"OMNI_PAYOUT_REVERSAL|{posting.pk}"
    )
    reference = {"reversal_of_marketplace_payout_posting_id": str(posting.pk)}
    balance_entry = MarketplaceBalanceEntry.objects.create(
        legal_entity=posting.legal_entity,
        store=posting.store,
        journal=journal,
        transaction_date=posting.payout_date,
        direction=MarketplaceBalanceDirection.IN,
        amount=posting.amount,
        currency=posting.currency,
        source_module="FINANCE",
        source_document_type="MarketplacePayoutReversal",
        source_document_id=str(posting.pk),
        source_key=f"MARKETPLACE_BALANCE_PAYOUT_REVERSAL|{posting.pk}",
        source_reference=reference,
        reversal_of=posting.marketplace_balance_entry,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    liquidity_entry = LiquidityEntry.objects.create(
        legal_entity=posting.legal_entity,
        liquidity_account=posting.liquidity_account,
        journal=journal,
        transaction_date=posting.payout_date,
        direction=LiquidityDirection.OUT,
        amount=posting.amount,
        currency=posting.currency,
        source_module="FINANCE",
        source_document_type="MarketplacePayoutReversal",
        source_document_id=str(posting.pk),
        source_key=f"LIQUIDITY_PAYOUT_REVERSAL|{posting.pk}",
        source_reference=reference,
        reversal_of=posting.liquidity_entry,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    reversal = MarketplacePayoutPosting.objects.create(
        legal_entity=posting.legal_entity,
        store=posting.store,
        source_payout_id=posting.source_payout_id,
        source_payout_identity=f"OMNI_PAYOUT_REVERSAL|{posting.pk}",
        payout_reference=posting.payout_reference,
        payout_date=posting.payout_date,
        amount=posting.amount,
        currency=posting.currency,
        liquidity_account=posting.liquidity_account,
        journal=journal,
        marketplace_balance_entry=balance_entry,
        liquidity_entry=liquidity_entry,
        source_reference=reference,
        reversal_of=posting,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    posting.state = MarketplaceFollowupState.REVERSED
    posting.save(update_fields=("state", "updated_at"))
    return reversal
