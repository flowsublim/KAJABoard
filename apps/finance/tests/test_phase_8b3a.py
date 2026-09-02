from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.channels.models import Store
from apps.finance.models import (
    AccountType,
    DCDirection,
    JournalEntry,
    MappingDimensionType,
    MarketplaceBalanceDirection,
    MarketplaceBalanceEntry,
    MarketplaceSettlementPosting,
    NormalBalance,
    ReceivableEntry,
)
from apps.finance.selectors import (
    marketplace_balance,
    marketplace_balance_entries,
    marketplace_settlements,
)
from apps.finance.services import (
    create_coa_account,
    create_coa_mapping,
    post_marketplace_settlement,
    reverse_marketplace_settlement,
)
from apps.omnichannel.models import (
    OmniImportBatch,
    OmniOperationalStatus,
    OmniReconciliationStatus,
    OmniRevenueEvent,
    OmniRevenueState,
    OmniSettlement,
    OmniSettlementImportBatch,
)
from apps.organizations.models import LegalEntity, OrganizationMembership

pytestmark = pytest.mark.django_db

SETTLEMENT_DATE = date(2026, 9, 2)


@pytest.fixture
def foundation():
    entity = LegalEntity.objects.create(code="8B3A", name="Finance Phase 8B3A")
    user = get_user_model().objects.create_user("phase8b3a@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    store = Store.objects.create(
        legal_entity=entity,
        code="STORE-8B3A",
        name="Marketplace Store 8B3A",
        channel="SHOPEE",
        finance_dimension="STORE-8B3A",
        effective_from=date(2026, 1, 1),
    )
    return {"entity": entity, "user": user, "store": store}


def _account(foundation, code, dc):
    return create_coa_account(
        legal_entity=foundation["entity"],
        account_code=code,
        account_name=code,
        account_type=AccountType.ASSET if dc == DCDirection.DEBIT else AccountType.LIABILITY,
        normal_balance=NormalBalance.DEBIT if dc == DCDirection.DEBIT else NormalBalance.CREDIT,
        effective_from=date(2026, 1, 1),
    )


def add_mappings(
    foundation, fee_roles=("ADMIN_FEE", "SERVICE_FEE", "AFFILIATE_FEE", "SHIPPING_FEE")
):
    roles = [
        ("MARKETPLACE_BALANCE", DCDirection.DEBIT),
        *[(role, DCDirection.DEBIT) for role in fee_roles],
        ("MARKETPLACE_RECEIVABLE", DCDirection.CREDIT),
    ]
    for index, (role, dc) in enumerate(roles, 1):
        create_coa_mapping(
            legal_entity=foundation["entity"],
            module_code="OMNI",
            event_code="OMNI_SETTLEMENT",
            dimension_type=MappingDimensionType.STORE,
            dimension_value=foundation["store"].finance_dimension,
            line_role=role,
            dc=dc,
            account=_account(foundation, f"8B3A-{index}-{role}", dc),
            effective_from=date(2026, 1, 1),
        )


def source_settlement(
    foundation, *, balance="90000", fees=None, refund=None, adjustment=None, suffix="1"
):
    fees = (
        fees
        if fees is not None
        else {"admin": "5000", "service": "3000", "affiliate": "1000", "shipping": "1000"}
    )
    order_batch = OmniImportBatch.objects.create(
        legal_entity=foundation["entity"],
        source_filename=f"order-{suffix}.csv",
        file_hash=f"order-{suffix}",
        status="IMPORTED",
    )
    from apps.omnichannel.models import OmniOrder

    order = OmniOrder.objects.create(
        legal_entity=foundation["entity"],
        source_batch=order_batch,
        marketplace="SHOPEE",
        external_store_name=foundation["store"].name,
        store=foundation["store"],
        external_order_number=f"ORDER-{suffix}",
        source_identity_key=f"ORDER|{suffix}",
        completion_date=date(2026, 9, 1),
        normalized_status=OmniOperationalStatus.COMPLETED,
    )
    event = OmniRevenueEvent.objects.create(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        marketplace="SHOPEE",
        order=order,
        external_order_number=order.external_order_number,
        completion_date=date(2026, 9, 1),
        gross_eligible_amount=Decimal("100000"),
        state=OmniRevenueState.ELIGIBLE,
        event_key=f"OMNI_REV|{suffix}",
    )
    revenue_journal = JournalEntry.objects.create(
        legal_entity=foundation["entity"],
        journal_number=f"REV-{suffix}",
        accounting_date=date(2026, 9, 1),
        event_code="OMNI_ORDER_COMPLETED",
        source_module="OMNI",
        source_document_type="OmniRevenueEvent",
        source_document_id=str(event.pk),
        source_key=f"OMNI_COMPLETION|{event.pk}",
        total_debit=Decimal("100000"),
        total_credit=Decimal("100000"),
        posted_at=timezone.now(),
        posted_by=foundation["user"],
    )
    receivable = ReceivableEntry.objects.create(
        journal=revenue_journal,
        legal_entity=foundation["entity"],
        accounting_date=date(2026, 9, 1),
        original_amount=Decimal("100000"),
        open_amount=Decimal("100000"),
        currency="IDR",
        store=foundation["store"],
    )
    batch = OmniSettlementImportBatch.objects.create(
        legal_entity=foundation["entity"],
        source_filename=f"settlement-{suffix}.csv",
        file_hash=f"settlement-{suffix}",
    )
    settlement = OmniSettlement.objects.create(
        batch=batch,
        legal_entity=foundation["entity"],
        store=foundation["store"],
        marketplace="SHOPEE",
        settlement_reference=f"SETTLE-{suffix}",
        external_order_number=order.external_order_number,
        settlement_date=SETTLEMENT_DATE,
        currency="IDR",
        gross_amount=Decimal("100000"),
        settled_amount=Decimal(balance),
        net_amount=Decimal(balance),
        fee_amount=sum((Decimal(value) for value in fees.values()), Decimal("0")),
        fee_components=fees,
        refund_amount=refund,
        adjustment_amount=adjustment,
        source_row_key=f"ROW-{suffix}",
        source_identity_key=f"OMNI_SETTLEMENT|{suffix}",
        reconciliation_status=OmniReconciliationStatus.SETTLEMENT_MATCH,
        matched_revenue=event,
    )
    return settlement, receivable


def test_happy_path_posts_balance_explicit_fees_and_clears_ar(foundation):
    add_mappings(foundation)
    settlement, receivable = source_settlement(foundation)
    posting = post_marketplace_settlement(settlement, actor=foundation["user"])
    receivable.refresh_from_db()
    roles = list(posting.journal.lines.values_list("line_role", flat=True))

    assert posting.journal.total_debit == posting.journal.total_credit == Decimal("100000")
    assert roles == [
        "MARKETPLACE_BALANCE",
        "ADMIN_FEE",
        "SERVICE_FEE",
        "AFFILIATE_FEE",
        "SHIPPING_FEE",
        "MARKETPLACE_RECEIVABLE",
    ]
    assert "REVENUE" not in roles
    assert receivable.open_amount == 0
    assert posting.marketplace_balance_entry.direction == MarketplaceBalanceDirection.IN
    assert posting.store == foundation["store"]
    assert posting.settlement_date == SETTLEMENT_DATE
    assert posting.source_lineage["batch_id"]


def test_partial_split_and_idempotency_do_not_duplicate_revenue(foundation):
    add_mappings(foundation, fee_roles=())
    first, receivable = source_settlement(foundation, balance="50000", fees={}, suffix="partial-1")
    second, _ = source_settlement(foundation, balance="50000", fees={}, suffix="partial-2")
    # Both settlements represent split clearing of the same completed-order AR.
    second_event = second.matched_revenue
    second.matched_revenue = first.matched_revenue
    second.external_order_number = first.external_order_number
    second.save(update_fields=("matched_revenue", "external_order_number"))
    second_receivable_journal = ReceivableEntry.objects.get(
        journal__source_key=f"OMNI_COMPLETION|{second_event.pk}"
    )
    second_receivable_journal.delete()
    post = post_marketplace_settlement(first, actor=foundation["user"])
    replay = post_marketplace_settlement(first, actor=foundation["user"])
    post_marketplace_settlement(second, actor=foundation["user"])
    receivable.refresh_from_db()

    assert replay.pk == post.pk
    assert receivable.open_amount == 0
    assert MarketplaceSettlementPosting.objects.count() == 2
    assert MarketplaceBalanceEntry.objects.count() == 2
    assert JournalEntry.objects.filter(event_code="OMNI_ORDER_COMPLETED").count() == 2


def test_missing_fee_mapping_blocks_all_finance_side_effects(foundation):
    add_mappings(foundation, fee_roles=("ADMIN_FEE",))
    settlement, receivable = source_settlement(foundation)
    before = (JournalEntry.objects.count(), MarketplaceBalanceEntry.objects.count())
    result = post_marketplace_settlement(settlement, actor=foundation["user"])
    receivable.refresh_from_db()

    assert result["status"] == "BLOCKED_MAPPING"
    assert (JournalEntry.objects.count(), MarketplaceBalanceEntry.objects.count()) == before
    assert receivable.open_amount == Decimal("100000")


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("refund", "REFUND_RECONCILIATION_REQUIRED"),
        ("adjustment", "ADJUSTMENT_SETTLEMENT_LINK_REQUIRED"),
    ),
)
def test_refund_and_adjustment_are_pending_without_accounting(foundation, field, reason):
    add_mappings(foundation)
    values = {field: Decimal("1000")}
    settlement, receivable = source_settlement(foundation, **values)
    result = post_marketplace_settlement(settlement, actor=foundation["user"])
    receivable.refresh_from_db()

    assert result["status"] == "PENDING_SOURCE"
    assert result["reason"] == reason
    assert MarketplaceSettlementPosting.objects.count() == 0
    assert receivable.open_amount == Decimal("100000")


@pytest.mark.parametrize(
    "change", ("unmatched", "missing_store", "missing_ar", "fractional", "overclear")
)
def test_source_and_amount_blockers_have_no_side_effects(foundation, change):
    add_mappings(foundation, fee_roles=())
    settlement, receivable = source_settlement(foundation, fees={})
    if change == "unmatched":
        settlement.matched_revenue = None
        settlement.save(update_fields=("matched_revenue",))
    elif change == "missing_store":
        settlement.store = None
        settlement.save(update_fields=("store",))
    elif change == "missing_ar":
        receivable.delete()
    elif change == "fractional":
        settlement.net_amount = Decimal("90000.50")
        settlement.save(update_fields=("net_amount",))
    elif change == "overclear":
        settlement.net_amount = Decimal("100001")
        settlement.save(update_fields=("net_amount",))
    result = post_marketplace_settlement(settlement, actor=foundation["user"])

    assert result["status"] == "PENDING_SOURCE"
    assert MarketplaceSettlementPosting.objects.count() == 0
    assert MarketplaceBalanceEntry.objects.count() == 0


def test_reversal_restores_ar_and_creates_compensating_balance_entry(foundation):
    add_mappings(foundation, fee_roles=())
    settlement, receivable = source_settlement(foundation, fees={})
    posting = post_marketplace_settlement(settlement, actor=foundation["user"])
    reversal = reverse_marketplace_settlement(posting, actor=foundation["user"])
    replay = reverse_marketplace_settlement(posting, actor=foundation["user"])
    posting.refresh_from_db()
    receivable.refresh_from_db()

    assert replay.pk == reversal.pk
    assert posting.state == "REVERSED"
    assert reversal.journal.reversal_of_id == posting.journal_id
    assert reversal.marketplace_balance_entry.direction == MarketplaceBalanceDirection.OUT
    assert receivable.open_amount == Decimal("100000")


def test_balance_and_settlement_selectors_are_scoped_and_read_only(foundation):
    add_mappings(foundation, fee_roles=())
    settlement, _ = source_settlement(foundation, fees={})
    posting = post_marketplace_settlement(settlement, actor=foundation["user"])
    before = (JournalEntry.objects.count(), MarketplaceBalanceEntry.objects.count())

    entries = marketplace_balance_entries(
        legal_entity=foundation["entity"], store=foundation["store"]
    )
    rows = marketplace_settlements(legal_entity=foundation["entity"], store=foundation["store"])

    assert marketplace_balance(
        legal_entity=foundation["entity"], store=foundation["store"]
    ) == Decimal("90000")
    assert list(entries) == [posting.marketplace_balance_entry]
    assert list(rows) == [posting]
    assert rows[0].receivable_id == posting.receivable_id
    assert (JournalEntry.objects.count(), MarketplaceBalanceEntry.objects.count()) == before
