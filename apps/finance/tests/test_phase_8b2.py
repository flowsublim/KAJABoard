from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.channels.models import Store
from apps.finance.models import (
    AccountType,
    DCDirection,
    JournalEntry,
    LiquidityAccountType,
    LiquidityDirection,
    LiquidityEntry,
    MappingDimensionType,
    NormalBalance,
    Payment,
    PaymentDirection,
    PaymentState,
)
from apps.finance.selectors import cash_ledger, payments
from apps.finance.services import create_coa_account, create_coa_mapping, create_liquidity_account
from apps.finance.services.pos_finance import (
    post_pos_cash_variance_finance,
    post_pos_refund_finance,
    post_pos_sale_finance,
    reverse_pos_sale_finance,
)
from apps.omnichannel.models import (
    PosCashSession,
    PosCashSessionState,
    PosFinanceSource,
    PosFinanceSourceState,
    PosReturn,
    PosReturnState,
    PosSale,
    PosSaleReversal,
    PosSaleState,
    PosTender,
    PosTenderMethod,
)
from apps.organizations.models import LegalEntity, OrganizationMembership, Warehouse
from apps.warehouse.models import StockMovement

pytestmark = pytest.mark.django_db

BUSINESS_DATE = date(2026, 9, 3)


@pytest.fixture
def foundation():
    entity = LegalEntity.objects.create(code="8B2", name="Finance Phase 8B2")
    user = get_user_model().objects.create_user("phase8b2@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    store = Store.objects.create(
        legal_entity=entity,
        code="STORE-8B2",
        name="POS Store 8B2",
        channel="POS",
        finance_dimension="STORE-8B2",
        effective_from=date(2026, 1, 1),
    )
    warehouse = Warehouse.objects.create(
        legal_entity=entity,
        code="WH-8B2",
        name="Warehouse 8B2",
        effective_from=date(2026, 1, 1),
    )
    cash = create_liquidity_account(
        legal_entity=entity,
        code="CASH-8B2",
        name="Cash Drawer 8B2",
        account_type=LiquidityAccountType.CASH,
        mapping_key="CASH-8B2",
        effective_from=date(2026, 1, 1),
    )
    bank = create_liquidity_account(
        legal_entity=entity,
        code="BANK-8B2",
        name="QRIS Bank 8B2",
        account_type=LiquidityAccountType.BANK,
        mapping_key="BANK-8B2",
        bank_name="Bank KAJA",
        bank_account_number="001-8B2",
        account_holder_name="PT KAJA",
        effective_from=date(2026, 1, 1),
    )
    return {
        "entity": entity,
        "user": user,
        "store": store,
        "warehouse": warehouse,
        "cash": cash,
        "bank": bank,
    }


def add_mappings(foundation, *, event_code, roles):
    for index, (role, dc, account_type) in enumerate(roles, 1):
        account = create_coa_account(
            legal_entity=foundation["entity"],
            account_code=f"8B2-{event_code[:10]}-{index}",
            account_name=f"{event_code} {role}",
            account_type=account_type,
            normal_balance=(
                NormalBalance.DEBIT if dc == DCDirection.DEBIT else NormalBalance.CREDIT
            ),
            effective_from=date(2026, 1, 1),
        )
        create_coa_mapping(
            legal_entity=foundation["entity"],
            module_code="OMNI",
            event_code=event_code,
            dimension_type=MappingDimensionType.DEFAULT,
            dimension_value="DEFAULT",
            line_role=role,
            dc=dc,
            account=account,
            effective_from=date(2026, 1, 1),
        )


def add_context_mapping(
    foundation, *, event_code, role, dc, account_type, dimension_type, dimension_value
):
    account = create_coa_account(
        legal_entity=foundation["entity"],
        account_code=f"8B2-{event_code[:7]}-{role[:5]}-{dimension_value}",
        account_name=f"{event_code} {role} {dimension_value}",
        account_type=account_type,
        normal_balance=(NormalBalance.DEBIT if dc == DCDirection.DEBIT else NormalBalance.CREDIT),
        effective_from=date(2026, 1, 1),
    )
    create_coa_mapping(
        legal_entity=foundation["entity"],
        module_code="OMNI",
        event_code=event_code,
        dimension_type=dimension_type,
        dimension_value=dimension_value,
        line_role=role,
        dc=dc,
        account=account,
        effective_from=date(2026, 1, 1),
    )


def create_sale(foundation, *, method=PosTenderMethod.CASH, amount=Decimal("100000")):
    sale = PosSale.objects.create(
        legal_entity=foundation["entity"],
        document_number=f"POS-8B2-{PosSale.objects.count() + 1}",
        store=foundation["store"],
        warehouse=foundation["warehouse"],
        transaction_at=timezone.now(),
        transaction_date=BUSINESS_DATE,
        state=PosSaleState.POSTED,
        subtotal_amount=amount,
        grand_total_amount=amount,
        source_key=f"POS-SALE-8B2-{PosSale.objects.count() + 1}",
        posted_by=foundation["user"],
        posted_at=timezone.now(),
    )
    tender = PosTender.objects.create(
        sale=sale,
        method=method,
        amount=amount,
        currency="IDR",
        transaction_at=timezone.now(),
        source_key=f"POS-TENDER-8B2-{sale.pk}",
    )
    revenue = PosFinanceSource.objects.create(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        sale=sale,
        event_code="POS_SALE_REVENUE",
        transaction_date=BUSINESS_DATE,
        amount=amount,
        currency="IDR",
        source_key=f"POS-REV-8B2-{sale.pk}",
        state=PosFinanceSourceState.ACTIVE,
    )
    tender_source = PosFinanceSource.objects.create(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        sale=sale,
        event_code="POS_TENDER",
        transaction_date=BUSINESS_DATE,
        amount=amount,
        currency="IDR",
        source_key=f"POS-TENDER-SRC-8B2-{sale.pk}",
        state=PosFinanceSourceState.ACTIVE,
    )
    return sale, tender, revenue, tender_source


def sale_mappings(foundation):
    add_mappings(
        foundation,
        event_code="POS_SALE_REVENUE",
        roles=(
            ("LIQUIDITY", DCDirection.DEBIT, AccountType.ASSET),
            ("REVENUE", DCDirection.CREDIT, AccountType.REVENUE),
        ),
    )
    for account, method in (
        (foundation["cash"], PosTenderMethod.CASH),
        (foundation["bank"], PosTenderMethod.QRIS),
    ):
        add_context_mapping(
            foundation,
            event_code="POS_SALE_REVENUE",
            role="LIQUIDITY",
            dc=DCDirection.DEBIT,
            account_type=AccountType.ASSET,
            dimension_type=MappingDimensionType.LIQUIDITY_ACCOUNT,
            dimension_value=account.mapping_key,
        )
        add_context_mapping(
            foundation,
            event_code="POS_SALE_REVENUE",
            role="REVENUE",
            dc=DCDirection.CREDIT,
            account_type=AccountType.REVENUE,
            dimension_type=MappingDimensionType.PAYMENT_METHOD,
            dimension_value=method,
        )


def cash_session(foundation, *, state=PosCashSessionState.OPEN):
    values = {
        "legal_entity": foundation["entity"],
        "store": foundation["store"],
        "opened_by": foundation["user"],
        "opened_at": timezone.now(),
        "opening_cash_amount": Decimal("0"),
        "state": state,
        "source_key": f"POS-CASH-8B2-{PosCashSession.objects.count() + 1}",
    }
    if state == PosCashSessionState.CLOSED:
        values.update(
            closed_by=foundation["user"],
            closed_at=timezone.now(),
            expected_cash_amount=Decimal("100000"),
            counted_cash_amount=Decimal("100000"),
            variance_amount=Decimal("0"),
        )
    return PosCashSession.objects.create(**values)


def create_refund_source(foundation, *, amount=Decimal("25000"), cash=True):
    sale, *_ = create_sale(foundation)
    session = cash_session(foundation) if cash else None
    pos_return = PosReturn.objects.create(
        legal_entity=foundation["entity"],
        document_number=f"RET-8B2-{PosReturn.objects.count() + 1}",
        original_sale=sale,
        store=foundation["store"],
        warehouse=foundation["warehouse"],
        return_at=timezone.now(),
        return_date=BUSINESS_DATE,
        state=PosReturnState.RECORDED,
        refund_amount=amount,
        cash_session=session,
        source_key=f"POS-RETURN-8B2-{sale.pk}",
        created_by=foundation["user"],
    )
    return PosFinanceSource.objects.create(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        sale=sale,
        pos_return=pos_return,
        cash_session=session,
        event_code="POS_REFUND",
        transaction_date=BUSINESS_DATE,
        amount=amount,
        currency="IDR",
        source_key=f"POS-REFUND-8B2-{pos_return.pk}",
        state=PosFinanceSourceState.ACTIVE,
    )


def test_pos_cash_sale_posts_receipt_once_with_source_lineage(foundation):
    sale_mappings(foundation)
    sale, tender, revenue, tender_source = create_sale(foundation)
    movement_count = StockMovement.objects.count()

    payment = post_pos_sale_finance(
        sale, liquidity_account=foundation["cash"], actor=foundation["user"]
    )
    replay = post_pos_sale_finance(
        sale, liquidity_account=foundation["cash"], actor=foundation["user"]
    )

    assert replay.pk == payment.pk
    assert payment.direction == PaymentDirection.RECEIPT
    assert payment.payment_date == BUSINESS_DATE
    assert payment.liquidity_entry.direction == LiquidityDirection.IN
    assert list(payment.journal.lines.values_list("line_role", flat=True)) == [
        "LIQUIDITY",
        "REVENUE",
    ]
    assert payment.source_reference["pos_tender_id"] == str(tender.pk)
    assert payment.source_reference["pos_finance_source_ids"] == [
        str(revenue.pk),
        str(tender_source.pk),
    ]
    assert payment.source_reference["tender_method"] == PosTenderMethod.CASH
    assert (
        payment.journal.lines.get(line_role="LIQUIDITY").mapping_snapshot["selected_dimension_type"]
        == MappingDimensionType.LIQUIDITY_ACCOUNT
    )
    assert (
        payment.journal.lines.get(line_role="REVENUE").mapping_snapshot["selected_dimension_type"]
        == MappingDimensionType.PAYMENT_METHOD
    )
    assert payment.journal.lines.filter(line_role__in=("COGS", "INVENTORY")).count() == 0
    assert (
        Payment.objects.count()
        == LiquidityEntry.objects.count()
        == JournalEntry.objects.count()
        == 1
    )
    assert StockMovement.objects.count() == movement_count


def test_pos_tender_requires_explicit_compatible_account_and_complete_mappings(foundation):
    sale, *_ = create_sale(foundation)
    before = (Payment.objects.count(), JournalEntry.objects.count(), LiquidityEntry.objects.count())
    with pytest.raises(ValidationError, match="CASH"):
        post_pos_sale_finance(sale, liquidity_account=foundation["bank"], actor=foundation["user"])
    assert (
        Payment.objects.count(),
        JournalEntry.objects.count(),
        LiquidityEntry.objects.count(),
    ) == before

    other_entity = LegalEntity.objects.create(code="8B2X", name="Other Entity")
    wrong_cash = create_liquidity_account(
        legal_entity=other_entity,
        code="CASH-OTHER",
        name="Other Cash",
        account_type=LiquidityAccountType.CASH,
        mapping_key="CASH-OTHER",
        effective_from=date(2026, 1, 1),
    )
    with pytest.raises(ValidationError, match="legal entity"):
        post_pos_sale_finance(sale, liquidity_account=wrong_cash, actor=foundation["user"])
    assert (
        Payment.objects.count(),
        JournalEntry.objects.count(),
        LiquidityEntry.objects.count(),
    ) == before

    with pytest.raises(ValidationError, match="BLOCKED_MAPPING"):
        post_pos_sale_finance(sale, liquidity_account=foundation["cash"], actor=foundation["user"])
    assert (
        Payment.objects.count(),
        JournalEntry.objects.count(),
        LiquidityEntry.objects.count(),
    ) == before


def test_pos_qris_receipt_uses_explicit_bank_and_preserves_method_context(foundation):
    sale_mappings(foundation)
    sale, *_ = create_sale(foundation, method=PosTenderMethod.QRIS)

    payment = post_pos_sale_finance(
        sale, liquidity_account=foundation["bank"], actor=foundation["user"]
    )

    assert payment.liquidity_account == foundation["bank"]
    assert payment.source_reference["tender_method"] == PosTenderMethod.QRIS
    assert (
        payment.journal.lines.get(line_role="LIQUIDITY").mapping_snapshot[
            "selected_dimension_value"
        ]
        == foundation["bank"].mapping_key
    )
    assert (
        payment.journal.lines.get(line_role="REVENUE").mapping_snapshot["selected_dimension_value"]
        == PosTenderMethod.QRIS
    )


def test_pos_refund_posts_disbursement_without_ap_or_stock_restoration(foundation):
    add_mappings(
        foundation,
        event_code="POS_REFUND",
        roles=(
            ("SALES_RETURN", DCDirection.DEBIT, AccountType.REVENUE),
            ("LIQUIDITY", DCDirection.CREDIT, AccountType.ASSET),
        ),
    )
    refund = create_refund_source(foundation)
    movement_count = StockMovement.objects.count()

    payment = post_pos_refund_finance(
        refund, liquidity_account=foundation["cash"], actor=foundation["user"]
    )

    assert payment.direction == PaymentDirection.DISBURSEMENT
    assert payment.liquidity_entry.direction == LiquidityDirection.OUT
    assert list(payment.journal.lines.values_list("line_role", flat=True)) == [
        "SALES_RETURN",
        "LIQUIDITY",
    ]
    assert payment.allocations.count() == 0
    assert StockMovement.objects.count() == movement_count

    pending = create_refund_source(foundation, amount=None, cash=False)
    with pytest.raises(ValidationError, match="PENDING_SOURCE"):
        post_pos_refund_finance(
            pending, liquidity_account=foundation["cash"], actor=foundation["user"]
        )
    assert Payment.objects.count() == 1


def test_pos_sale_finance_reversal_is_compensating_and_idempotent(foundation):
    sale_mappings(foundation)
    sale, *_ = create_sale(foundation)
    original = post_pos_sale_finance(
        sale, liquidity_account=foundation["cash"], actor=foundation["user"]
    )
    sale.state = PosSaleState.REVERSED
    sale.save(update_fields=("state", "updated_at"))
    PosSaleReversal.objects.create(
        original_sale=sale,
        reversal_date=BUSINESS_DATE,
        reason="Customer correction",
        source_key=f"POS-REVERSAL-8B2-{sale.pk}",
        idempotency_key=f"POS-REVERSAL-IDEMP-8B2-{sale.pk}",
        created_by=foundation["user"],
    )
    PosFinanceSource.objects.create(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        sale=sale,
        event_code="POS_REVERSAL",
        transaction_date=BUSINESS_DATE,
        amount=Decimal("100000"),
        source_key=f"POS-REVERSAL-SRC-8B2-{sale.pk}",
        state=PosFinanceSourceState.ACTIVE,
    )
    movement_count = StockMovement.objects.count()

    reversal = reverse_pos_sale_finance(sale, actor=foundation["user"])
    replay = reverse_pos_sale_finance(sale, actor=foundation["user"])
    original.refresh_from_db()

    assert replay.pk == reversal.pk
    assert original.state == PaymentState.REVERSED
    assert reversal.reversal_of == original
    assert reversal.liquidity_entry.direction == LiquidityDirection.OUT
    assert original.journal.state == "REVERSED"
    assert (
        JournalEntry.objects.count()
        == Payment.objects.count()
        == LiquidityEntry.objects.count()
        == 2
    )
    assert StockMovement.objects.count() == movement_count


def test_pos_cash_variance_uses_cash_only_and_skips_zero_value_journal(foundation):
    add_mappings(
        foundation,
        event_code="POS_CASH_VARIANCE",
        roles=(
            ("LIQUIDITY", DCDirection.DEBIT, AccountType.ASSET),
            ("CASH_VARIANCE", DCDirection.CREDIT, AccountType.REVENUE),
            ("CASH_VARIANCE", DCDirection.DEBIT, AccountType.EXPENSE),
            ("LIQUIDITY", DCDirection.CREDIT, AccountType.ASSET),
        ),
    )
    session = cash_session(foundation, state=PosCashSessionState.CLOSED)
    overage = PosFinanceSource.objects.create(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        cash_session=session,
        event_code="POS_CASH_VARIANCE",
        transaction_date=BUSINESS_DATE,
        amount=Decimal("15000"),
        source_key="POS-VARIANCE-OVER-8B2",
        state=PosFinanceSourceState.ACTIVE,
    )
    shortage = PosFinanceSource.objects.create(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        cash_session=session,
        event_code="POS_CASH_VARIANCE",
        transaction_date=BUSINESS_DATE,
        amount=Decimal("-5000"),
        source_key="POS-VARIANCE-SHORT-8B2",
        state=PosFinanceSourceState.ACTIVE,
    )
    zero = PosFinanceSource.objects.create(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        cash_session=session,
        event_code="POS_CASH_VARIANCE",
        transaction_date=BUSINESS_DATE,
        amount=Decimal("0"),
        source_key="POS-VARIANCE-ZERO-8B2",
        state=PosFinanceSourceState.ACTIVE,
    )

    over_entry = post_pos_cash_variance_finance(
        overage, liquidity_account=foundation["cash"], actor=foundation["user"]
    )
    short_entry = post_pos_cash_variance_finance(
        shortage, liquidity_account=foundation["cash"], actor=foundation["user"]
    )
    zero_result = post_pos_cash_variance_finance(
        zero, liquidity_account=foundation["cash"], actor=foundation["user"]
    )

    assert over_entry.direction == LiquidityDirection.IN
    assert short_entry.direction == LiquidityDirection.OUT
    assert zero_result["status"] == "NO_ACCOUNTING_EFFECT"
    assert JournalEntry.objects.count() == 2
    with pytest.raises(ValidationError, match="CASH"):
        post_pos_cash_variance_finance(
            overage, liquidity_account=foundation["bank"], actor=foundation["user"]
        )


def test_pos_payment_selectors_are_read_only_and_retain_source_context(foundation):
    sale_mappings(foundation)
    sale, *_ = create_sale(foundation)
    payment = post_pos_sale_finance(
        sale, liquidity_account=foundation["cash"], actor=foundation["user"]
    )
    before = (Payment.objects.count(), JournalEntry.objects.count(), LiquidityEntry.objects.count())

    selected = list(payments(legal_entity=foundation["entity"]))
    ledger = list(cash_ledger(legal_entity=foundation["entity"]))

    assert selected == [payment]
    assert selected[0].source_module == "OMNI"
    assert selected[0].source_reference["pos_sale_id"] == str(sale.pk)
    assert ledger == [payment.liquidity_entry]
    assert (
        Payment.objects.count(),
        JournalEntry.objects.count(),
        LiquidityEntry.objects.count(),
    ) == before
