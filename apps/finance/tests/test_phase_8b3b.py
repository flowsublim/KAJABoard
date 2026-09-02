from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.channels.models import Store
from apps.finance.models import (
    AccountType,
    DCDirection,
    LiquidityAccountType,
    MappingDimensionType,
    MarketplaceBalanceDirection,
    MarketplaceReturnTreatment,
    NormalBalance,
)
from apps.finance.selectors import (
    marketplace_adjustments,
    marketplace_balance,
    marketplace_payouts,
    marketplace_returns,
)
from apps.finance.services import (
    create_coa_account,
    create_coa_mapping,
    create_liquidity_account,
    post_marketplace_payout,
    post_marketplace_return,
    post_marketplace_settlement,
    reverse_marketplace_payout,
    reverse_marketplace_return,
)
from apps.finance.tests.test_phase_8b3a import add_mappings, source_settlement
from apps.omnichannel.models import (
    OmniAdjustmentSource,
    OmniPayoutSource,
    OmniReconciliationStatus,
    OmniReturnImportBatch,
    OmniReturnLinkageStatus,
    OmniReturnSource,
)
from apps.organizations.models import LegalEntity, OrganizationMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def foundation():
    entity = LegalEntity.objects.create(code="8B3B", name="Finance Phase 8B3B")
    user = get_user_model().objects.create_user("phase8b3b@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    store = Store.objects.create(
        legal_entity=entity,
        code="STORE-8B3B",
        name="Marketplace Store 8B3B",
        channel="SHOPEE",
        finance_dimension="STORE-8B3B",
        effective_from=date(2026, 1, 1),
    )
    return {"entity": entity, "user": user, "store": store}


def add_event_mapping(
    foundation,
    *,
    event_code,
    role,
    dc,
    dimension_type=MappingDimensionType.STORE,
    dimension_value=None,
):
    account = create_coa_account(
        legal_entity=foundation["entity"],
        account_code=f"{event_code}-{role}-{dc}"[:40],
        account_name=f"{event_code} {role}",
        account_type=AccountType.EXPENSE if dc == DCDirection.DEBIT else AccountType.ASSET,
        normal_balance=NormalBalance.DEBIT if dc == DCDirection.DEBIT else NormalBalance.CREDIT,
        effective_from=date(2026, 1, 1),
    )
    create_coa_mapping(
        legal_entity=foundation["entity"],
        module_code="OMNI",
        event_code=event_code,
        dimension_type=dimension_type,
        dimension_value=dimension_value or foundation["store"].finance_dimension,
        line_role=role,
        dc=dc,
        account=account,
        effective_from=date(2026, 1, 1),
    )


def return_source(foundation, settlement, *, amount="10000", suffix="return", matched=True):
    batch = OmniReturnImportBatch.objects.create(
        legal_entity=foundation["entity"], source_filename=f"{suffix}.csv", file_hash=suffix
    )
    return OmniReturnSource.objects.create(
        batch=batch,
        legal_entity=foundation["entity"],
        store=foundation["store"],
        marketplace="SHOPEE",
        external_order_number=settlement.external_order_number,
        external_sku="SKU",
        quantity=Decimal("1"),
        refund_amount=Decimal(amount),
        currency="IDR",
        arrived_at=timezone.now(),
        original_order=settlement.matched_revenue.order,
        linkage_status=OmniReturnLinkageStatus.MATCHED
        if matched
        else OmniReturnLinkageStatus.UNMATCHED_ORDER,
        source_row_key=suffix,
        source_identity_key=f"OMNI_RETURN|{suffix}",
    )


def return_mappings(foundation):
    add_event_mapping(
        foundation, event_code="OMNI_RETURN", role="SALES_RETURN", dc=DCDirection.DEBIT
    )
    add_event_mapping(
        foundation, event_code="OMNI_RETURN", role="MARKETPLACE_RECEIVABLE", dc=DCDirection.CREDIT
    )
    add_event_mapping(
        foundation, event_code="OMNI_RETURN", role="MARKETPLACE_BALANCE", dc=DCDirection.CREDIT
    )


def payout_mappings(foundation, bank):
    add_event_mapping(
        foundation,
        event_code="OMNI_PAYOUT",
        role="LIQUIDITY",
        dc=DCDirection.DEBIT,
        dimension_type=MappingDimensionType.LIQUIDITY_ACCOUNT,
        dimension_value=bank.mapping_key,
    )
    add_event_mapping(
        foundation, event_code="OMNI_PAYOUT", role="MARKETPLACE_BALANCE", dc=DCDirection.CREDIT
    )


def test_return_open_ar_and_reversal_are_idempotent_without_stock(foundation):
    settlement, receivable = source_settlement(foundation, fees={})
    return_mappings(foundation)
    source = return_source(foundation, settlement)
    posting = post_marketplace_return(source, actor=foundation["user"])
    replay = post_marketplace_return(source, actor=foundation["user"])
    receivable.refresh_from_db()
    reversal = reverse_marketplace_return(posting, actor=foundation["user"])
    receivable.refresh_from_db()

    assert replay.pk == posting.pk
    assert posting.treatment == MarketplaceReturnTreatment.RECEIVABLE_CREDIT
    assert list(posting.journal.lines.values_list("line_role", flat=True)) == [
        "SALES_RETURN",
        "MARKETPLACE_RECEIVABLE",
    ]
    assert receivable.open_amount == Decimal("100000")
    assert reversal.journal.reversal_of_id == posting.journal_id
    assert not posting.marketplace_balance_entry_id


def test_settled_return_uses_marketplace_balance_and_blockers(foundation):
    add_mappings(foundation, fee_roles=())
    settlement, _ = source_settlement(foundation, balance="100000", fees={})
    post_marketplace_settlement(settlement, actor=foundation["user"])
    return_mappings(foundation)
    source = return_source(foundation, settlement, amount="20000")
    posting = post_marketplace_return(source, actor=foundation["user"])

    assert posting.treatment == MarketplaceReturnTreatment.MARKETPLACE_BALANCE_CREDIT
    assert posting.marketplace_balance_entry.direction == MarketplaceBalanceDirection.OUT
    assert marketplace_balance(
        legal_entity=foundation["entity"], store=foundation["store"]
    ) == Decimal("80000")

    mixed_settlement, mixed_ar = source_settlement(foundation, fees={}, suffix="mixed")
    mixed_ar.open_amount = Decimal("5000")
    mixed_ar.save(update_fields=("open_amount", "updated_at"))
    mixed = post_marketplace_return(
        return_source(foundation, mixed_settlement, suffix="mixed", amount="10000"),
        actor=foundation["user"],
    )
    assert mixed["reason"] == "MIXED_REFUND_FUNDING_UNRESOLVED"


def test_settlement_refund_unlocks_only_after_exact_dedicated_return(foundation):
    add_mappings(foundation, fee_roles=())
    settlement, receivable = source_settlement(
        foundation, balance="90000", fees={}, refund=Decimal("10000")
    )
    return_mappings(foundation)
    refund = post_marketplace_return(
        return_source(foundation, settlement, amount="10000"), actor=foundation["user"]
    )
    posting = post_marketplace_settlement(settlement, actor=foundation["user"])
    receivable.refresh_from_db()

    assert posting.source_reference["refund_return_posting_id"] == str(refund.pk)
    assert "SALES_RETURN" not in posting.journal.lines.values_list("line_role", flat=True)
    assert receivable.open_amount == 0


def test_linked_adjustment_is_consumed_in_the_settlement_once(foundation):
    add_mappings(foundation, fee_roles=())
    add_event_mapping(
        foundation,
        event_code="OMNI_SETTLEMENT",
        role="MARKETPLACE_ADJUSTMENT",
        dc=DCDirection.DEBIT,
    )
    settlement, _ = source_settlement(
        foundation, balance="90000", fees={}, adjustment=Decimal("10000")
    )
    adjustment = OmniAdjustmentSource.objects.create(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        settlement=settlement,
        adjustment_type="PENALTY",
        amount=Decimal("10000"),
        transaction_date=settlement.settlement_date,
        source_row_key="ADJ-1",
        source_identity_key="OMNI_ADJUSTMENT|1",
    )
    posting = post_marketplace_settlement(settlement, actor=foundation["user"])
    replay = post_marketplace_settlement(settlement, actor=foundation["user"])

    assert replay.pk == posting.pk
    assert posting.journal.total_debit == posting.journal.total_credit == Decimal("100000")
    assert "MARKETPLACE_ADJUSTMENT" in posting.journal.lines.values_list("line_role", flat=True)
    assert marketplace_adjustments(legal_entity=foundation["entity"])[
        0
    ].source_adjustment_id == str(adjustment.pk)


def test_payout_bank_only_with_posted_references_and_reversal(foundation):
    add_mappings(foundation, fee_roles=())
    settlement, receivable = source_settlement(foundation, balance="100000", fees={})
    post_marketplace_settlement(settlement, actor=foundation["user"])
    bank = create_liquidity_account(
        legal_entity=foundation["entity"],
        code="BANK-8B3B",
        name="Bank",
        account_type=LiquidityAccountType.BANK,
        mapping_key="BANK-8B3B",
        bank_name="KAJA Bank",
        effective_from=date(2026, 1, 1),
    )
    payout_mappings(foundation, bank)
    payout = OmniPayoutSource.objects.create(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        marketplace="SHOPEE",
        payout_reference="PAYOUT-1",
        payout_date=date(2026, 9, 3),
        amount=Decimal("100000"),
        currency="IDR",
        settlement_references=[settlement.settlement_reference],
        source_row_key="PAYOUT-1",
        source_identity_key="OMNI_PAYOUT|1",
        reconciliation_status=OmniReconciliationStatus.PAYOUT_MATCH,
    )
    posting = post_marketplace_payout(payout, liquidity_account=bank, actor=foundation["user"])
    replay = post_marketplace_payout(payout, liquidity_account=bank, actor=foundation["user"])
    reversal = reverse_marketplace_payout(posting, actor=foundation["user"])
    receivable.refresh_from_db()

    assert replay.pk == posting.pk
    assert receivable.open_amount == 0
    assert posting.marketplace_balance_entry.direction == MarketplaceBalanceDirection.OUT
    assert posting.liquidity_entry.direction == "IN"
    assert reversal.marketplace_balance_entry.direction == MarketplaceBalanceDirection.IN
    assert reversal.liquidity_entry.direction == "OUT"
    assert marketplace_payouts(legal_entity=foundation["entity"]).count() == 2


def test_selectors_are_read_only_and_store_scoped(foundation):
    settlement, _ = source_settlement(foundation, fees={})
    return_mappings(foundation)
    post_marketplace_return(return_source(foundation, settlement), actor=foundation["user"])
    before = marketplace_returns(legal_entity=foundation["entity"]).count()

    assert (
        marketplace_returns(legal_entity=foundation["entity"], store=foundation["store"]).count()
        == before
    )
    assert marketplace_adjustments(legal_entity=foundation["entity"]).count() == 0
    assert marketplace_payouts(legal_entity=foundation["entity"]).count() == 0
