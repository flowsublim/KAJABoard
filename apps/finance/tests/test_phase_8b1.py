from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import UniqueConstraint
from django.utils import timezone

from apps.channels.models import Store
from apps.core.models import SequenceResetMode
from apps.core.services.numbering import allocate_document_number, create_document_sequence
from apps.finance.models import (
    AccountType,
    DCDirection,
    JournalEntry,
    LiquidityAccountType,
    LiquidityDirection,
    LiquidityEntry,
    MappingDimensionType,
    NormalBalance,
    PayableEntry,
    Payment,
    PaymentDirection,
    PaymentState,
    ReceivableEntry,
)
from apps.finance.selectors import bank_ledger, cash_ledger, liquidity_balance, payments
from apps.finance.services import (
    create_coa_account,
    create_coa_mapping,
    create_liquidity_account,
    liquidity_mapping_context,
    post_customer_receipt,
    post_vendor_payment,
    reverse_payment,
)
from apps.organizations.models import LegalEntity, OrganizationMembership
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.purchasing.models import PurchaseOrder, PurchaseOrderState

pytestmark = pytest.mark.django_db

PAYMENT_DATE = date(2026, 9, 2)


@pytest.fixture
def foundation():
    entity = LegalEntity.objects.create(code="8B1", name="Finance Phase 8B1")
    user = get_user_model().objects.create_user("phase8b1@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    customer = BusinessPartner.objects.create(
        legal_entity=entity, code="CUST-8B1", display_name="Customer 8B1"
    )
    PartnerRole.objects.create(
        partner=customer,
        role_type=PartnerRoleType.CUSTOMER,
        effective_from=date(2026, 1, 1),
    )
    vendor = BusinessPartner.objects.create(
        legal_entity=entity, code="VEND-8B1", display_name="Vendor 8B1"
    )
    PartnerRole.objects.create(
        partner=vendor,
        role_type=PartnerRoleType.VENDOR,
        effective_from=date(2026, 1, 1),
    )
    store = Store.objects.create(
        legal_entity=entity,
        code="STORE-8B1",
        name="Marketplace Store 8B1",
        channel="SHOPEE",
        finance_dimension="STORE-8B1",
        effective_from=date(2026, 1, 1),
    )
    cash = create_liquidity_account(
        legal_entity=entity,
        code="CASH-8B1",
        name="Cash Drawer 8B1",
        account_type=LiquidityAccountType.CASH,
        mapping_key="CASH-8B1",
        effective_from=date(2026, 1, 1),
    )
    bank = create_liquidity_account(
        legal_entity=entity,
        code="BANK-8B1",
        name="Bank 8B1",
        account_type=LiquidityAccountType.BANK,
        mapping_key="BANK-8B1",
        bank_name="Bank KAJA",
        bank_account_number="1234567890",
        account_holder_name="PT KAJA",
        effective_from=date(2026, 1, 1),
    )
    return {
        "entity": entity,
        "user": user,
        "customer": customer,
        "vendor": vendor,
        "store": store,
        "cash": cash,
        "bank": bank,
    }


def add_mappings(foundation, *, event_code, roles, liquidity_account):
    for index, (role, dc, dimension_type, dimension_value) in enumerate(roles, 1):
        account = create_coa_account(
            legal_entity=foundation["entity"],
            account_code=f"{event_code[:8]}-{index}",
            account_name=f"{event_code} {role}",
            account_type=(AccountType.ASSET if dc == DCDirection.DEBIT else AccountType.LIABILITY),
            normal_balance=(
                NormalBalance.DEBIT if dc == DCDirection.DEBIT else NormalBalance.CREDIT
            ),
            effective_from=date(2026, 1, 1),
        )
        create_coa_mapping(
            legal_entity=foundation["entity"],
            module_code="FINANCE",
            event_code=event_code,
            dimension_type=dimension_type,
            dimension_value=dimension_value,
            line_role=role,
            dc=dc,
            account=account,
            effective_from=date(2026, 1, 1),
        )


def payment_mappings(foundation, *, event_code, direction, liquidity_account):
    liquidity_dc = (
        DCDirection.DEBIT if direction == PaymentDirection.RECEIPT else DCDirection.CREDIT
    )
    target_role = "RECEIVABLE" if direction == PaymentDirection.RECEIPT else "PAYABLE"
    target_dc = DCDirection.CREDIT if direction == PaymentDirection.RECEIPT else DCDirection.DEBIT
    add_mappings(
        foundation,
        event_code=event_code,
        liquidity_account=liquidity_account,
        roles=(
            (
                "LIQUIDITY",
                liquidity_dc,
                MappingDimensionType.LIQUIDITY_ACCOUNT,
                liquidity_account.mapping_key,
            ),
            (target_role, target_dc, MappingDimensionType.DEFAULT, "DEFAULT"),
        ),
    )


def source_journal(foundation, *, source_key):
    return JournalEntry.objects.create(
        legal_entity=foundation["entity"],
        journal_number=f"SRC-{source_key}",
        accounting_date=date(2026, 9, 1),
        event_code="SOURCE",
        source_module="TEST",
        source_document_type="Source",
        source_document_id=source_key,
        source_key=source_key,
        total_debit=Decimal("0"),
        total_credit=Decimal("0"),
        posted_at=timezone.now(),
        posted_by=foundation["user"],
    )


def receivable(foundation, *, amount, source_key, currency="IDR", store=None):
    return ReceivableEntry.objects.create(
        journal=source_journal(foundation, source_key=source_key),
        legal_entity=foundation["entity"],
        accounting_date=date(2026, 9, 1),
        original_amount=amount,
        open_amount=amount,
        currency=currency,
        partner=foundation["customer"],
        store=store,
    )


def payable(foundation, *, amount, source_key, currency="IDR"):
    return PayableEntry.objects.create(
        journal=source_journal(foundation, source_key=source_key),
        legal_entity=foundation["entity"],
        accounting_date=date(2026, 9, 1),
        original_amount=amount,
        open_amount=amount,
        currency=currency,
        partner=foundation["vendor"],
    )


def test_liquidity_account_types_effectivity_and_mapping_context(foundation):
    assert foundation["cash"].account_type == LiquidityAccountType.CASH
    assert foundation["bank"].account_type == LiquidityAccountType.BANK
    assert liquidity_mapping_context(foundation["cash"]) == {"LIQUIDITY_ACCOUNT": "CASH-8B1"}
    with pytest.raises(ValidationError, match="Bank metadata"):
        create_liquidity_account(
            legal_entity=foundation["entity"],
            code="BAD-CASH",
            name="Invalid cash",
            account_type=LiquidityAccountType.CASH,
            mapping_key="BAD-CASH",
            bank_name="Not allowed",
            effective_from=date(2026, 1, 1),
        )


def test_customer_receipt_posts_and_allocates_multiple_ar_idempotently(foundation):
    payment_mappings(
        foundation,
        event_code="CUSTOMER_PAYMENT",
        direction=PaymentDirection.RECEIPT,
        liquidity_account=foundation["cash"],
    )
    first = receivable(foundation, amount=Decimal("100000"), source_key="AR-1")
    second = receivable(foundation, amount=Decimal("50000"), source_key="AR-2")
    payment = post_customer_receipt(
        legal_entity=foundation["entity"],
        liquidity_account=foundation["cash"],
        allocations=(
            {"receivable": first, "amount": Decimal("100000")},
            {"receivable": second, "amount": Decimal("50000")},
        ),
        payment_date=PAYMENT_DATE,
        source_key="RECEIPT-8B1-1",
        actor=foundation["user"],
    )
    replay = post_customer_receipt(
        legal_entity=foundation["entity"],
        liquidity_account=foundation["cash"],
        allocations=(),
        payment_date=PAYMENT_DATE,
        source_key="RECEIPT-8B1-1",
        actor=foundation["user"],
    )
    first.refresh_from_db()
    second.refresh_from_db()

    assert replay.pk == payment.pk
    assert payment.amount == Decimal("150000")
    assert payment.direction == PaymentDirection.RECEIPT
    assert payment.liquidity_entry.direction == LiquidityDirection.IN
    assert list(payment.journal.lines.values_list("line_role", flat=True)) == [
        "LIQUIDITY",
        "RECEIVABLE",
        "RECEIVABLE",
    ]
    assert first.open_amount == second.open_amount == Decimal("0")
    assert payment.allocations.count() == 2
    assert Payment.objects.count() == 1
    assert LiquidityEntry.objects.count() == 1


def test_customer_receipt_blocks_overallocation_fraction_currency_and_mapping(foundation):
    target = receivable(foundation, amount=Decimal("100000"), source_key="AR-VALID")
    before = (Payment.objects.count(), JournalEntry.objects.count(), LiquidityEntry.objects.count())
    with pytest.raises(ValidationError, match="exceeds"):
        post_customer_receipt(
            legal_entity=foundation["entity"],
            liquidity_account=foundation["cash"],
            allocations=({"receivable": target, "amount": Decimal("100001")},),
            payment_date=PAYMENT_DATE,
            source_key="OVER-8B1",
            actor=foundation["user"],
        )
    with pytest.raises(ValidationError, match="whole Rupiah"):
        post_customer_receipt(
            legal_entity=foundation["entity"],
            liquidity_account=foundation["cash"],
            allocations=({"receivable": target, "amount": Decimal("1.5")},),
            payment_date=PAYMENT_DATE,
            source_key="FRACTION-8B1",
            actor=foundation["user"],
        )
    with pytest.raises(ValidationError, match="currency"):
        post_customer_receipt(
            legal_entity=foundation["entity"],
            liquidity_account=foundation["cash"],
            allocations=({"receivable": target, "amount": Decimal("1")},),
            payment_date=PAYMENT_DATE,
            source_key="CURRENCY-8B1",
            currency="USD",
            actor=foundation["user"],
        )
    with pytest.raises(ValidationError, match="BLOCKED_MAPPING"):
        post_customer_receipt(
            legal_entity=foundation["entity"],
            liquidity_account=foundation["cash"],
            allocations=({"receivable": target, "amount": Decimal("1")},),
            payment_date=PAYMENT_DATE,
            source_key="MAPPING-8B1",
            actor=foundation["user"],
        )
    assert (
        Payment.objects.count(),
        JournalEntry.objects.count(),
        LiquidityEntry.objects.count(),
    ) == before


def test_customer_receipt_rejects_cross_entity_allocation(foundation):
    other = LegalEntity.objects.create(code="8B1OTHER", name="Other Entity")
    other_journal = JournalEntry.objects.create(
        legal_entity=other,
        journal_number="SRC-OTHER",
        accounting_date=PAYMENT_DATE,
        event_code="SOURCE",
        source_module="TEST",
        source_document_type="Source",
        source_document_id="OTHER",
        source_key="OTHER",
        total_debit=Decimal("0"),
        total_credit=Decimal("0"),
        posted_at=timezone.now(),
        posted_by=foundation["user"],
    )
    other_target = ReceivableEntry.objects.create(
        journal=other_journal,
        legal_entity=other,
        accounting_date=PAYMENT_DATE,
        original_amount=Decimal("1"),
        open_amount=Decimal("1"),
    )
    with pytest.raises(ValidationError, match="legal entity"):
        post_customer_receipt(
            legal_entity=foundation["entity"],
            liquidity_account=foundation["cash"],
            allocations=({"receivable": other_target, "amount": Decimal("1")},),
            payment_date=PAYMENT_DATE,
            source_key="CROSS-8B1",
            actor=foundation["user"],
        )


def test_vendor_payment_only_reduces_existing_ap_and_never_reposts_cost(foundation):
    payment_mappings(
        foundation,
        event_code="VENDOR_PAYMENT",
        direction=PaymentDirection.DISBURSEMENT,
        liquidity_account=foundation["bank"],
    )
    target = payable(foundation, amount=Decimal("90000"), source_key="AP-1")
    payment = post_vendor_payment(
        legal_entity=foundation["entity"],
        liquidity_account=foundation["bank"],
        allocations=({"payable": target, "amount": Decimal("90000")},),
        payment_date=PAYMENT_DATE,
        source_key="VENDOR-8B1-1",
        actor=foundation["user"],
    )
    target.refresh_from_db()

    assert target.open_amount == Decimal("0")
    assert payment.liquidity_entry.direction == LiquidityDirection.OUT
    assert set(payment.journal.lines.values_list("line_role", flat=True)) == {
        "PAYABLE",
        "LIQUIDITY",
    }
    assert not set(payment.journal.lines.values_list("line_role", flat=True)) & {
        "EXPENSE",
        "INVENTORY",
        "ASSET",
        "OVERHEAD",
    }


def test_confirmed_purchase_order_is_not_ap_or_vendor_payment_eligible(foundation):
    create_document_sequence(
        legal_entity=foundation["entity"],
        document_type="PURCHASE_ORDER",
        name="PO 8B1",
        prefix="PO8B1",
        format_template="{prefix}-{yyyy}-{seq}",
        padding=4,
        reset_mode=SequenceResetMode.YEARLY,
        effective_from=date(2026, 1, 1),
    )
    allocation = allocate_document_number(
        foundation["entity"], "PURCHASE_ORDER", business_date=PAYMENT_DATE
    )
    PurchaseOrder.objects.create(
        legal_entity=foundation["entity"],
        document_allocation=allocation,
        document_number=allocation.number,
        document_date=PAYMENT_DATE,
        vendor=foundation["vendor"],
        vendor_code_snapshot=foundation["vendor"].code,
        vendor_name_snapshot=foundation["vendor"].display_name,
        state=PurchaseOrderState.CONFIRMED,
        grand_total=Decimal("80000"),
        confirmed_by=foundation["user"],
        confirmed_at=timezone.now(),
    )
    with pytest.raises(ValidationError, match="At least one"):
        post_vendor_payment(
            legal_entity=foundation["entity"],
            liquidity_account=foundation["bank"],
            allocations=(),
            payment_date=PAYMENT_DATE,
            source_key="PO-NOT-PAYABLE",
            actor=foundation["user"],
        )
    assert PayableEntry.objects.count() == 0
    assert Payment.objects.count() == 0


def test_liquidity_ledgers_and_balance_are_read_projections(foundation):
    payment_mappings(
        foundation,
        event_code="CUSTOMER_PAYMENT",
        direction=PaymentDirection.RECEIPT,
        liquidity_account=foundation["cash"],
    )
    payment_mappings(
        foundation,
        event_code="VENDOR_PAYMENT",
        direction=PaymentDirection.DISBURSEMENT,
        liquidity_account=foundation["bank"],
    )
    ar = receivable(foundation, amount=Decimal("40000"), source_key="AR-CASH")
    ap = payable(foundation, amount=Decimal("25000"), source_key="AP-BANK")
    post_customer_receipt(
        legal_entity=foundation["entity"],
        liquidity_account=foundation["cash"],
        allocations=({"receivable": ar, "amount": Decimal("40000")},),
        payment_date=PAYMENT_DATE,
        source_key="CASH-RECEIPT",
        actor=foundation["user"],
    )
    post_vendor_payment(
        legal_entity=foundation["entity"],
        liquidity_account=foundation["bank"],
        allocations=({"payable": ap, "amount": Decimal("25000")},),
        payment_date=PAYMENT_DATE,
        source_key="BANK-PAYMENT",
        actor=foundation["user"],
    )
    before = (Payment.objects.count(), LiquidityEntry.objects.count())

    assert cash_ledger(legal_entity=foundation["entity"]).count() == 1
    assert bank_ledger(legal_entity=foundation["entity"]).count() == 1
    assert liquidity_balance(
        legal_entity=foundation["entity"], liquidity_account=foundation["cash"]
    ) == Decimal("40000")
    assert liquidity_balance(
        legal_entity=foundation["entity"], liquidity_account=foundation["bank"]
    ) == Decimal("-25000")
    assert payments(legal_entity=foundation["entity"]).count() == 2
    assert (Payment.objects.count(), LiquidityEntry.objects.count()) == before


def test_payment_reversal_is_compensating_and_idempotent(foundation):
    payment_mappings(
        foundation,
        event_code="CUSTOMER_PAYMENT",
        direction=PaymentDirection.RECEIPT,
        liquidity_account=foundation["cash"],
    )
    target = receivable(foundation, amount=Decimal("100000"), source_key="AR-REVERSE")
    payment = post_customer_receipt(
        legal_entity=foundation["entity"],
        liquidity_account=foundation["cash"],
        allocations=({"receivable": target, "amount": Decimal("100000")},),
        payment_date=PAYMENT_DATE,
        source_key="REVERSE-8B1",
        actor=foundation["user"],
    )
    reversal = reverse_payment(payment, actor=foundation["user"])
    replay = reverse_payment(payment, actor=foundation["user"])
    payment.refresh_from_db()
    target.refresh_from_db()

    assert replay.pk == reversal.pk
    assert payment.state == PaymentState.REVERSED
    assert reversal.reversal_of == payment
    assert reversal.journal.reversal_of == payment.journal
    assert reversal.liquidity_entry.reversal_of == payment.liquidity_entry
    assert reversal.liquidity_entry.direction == LiquidityDirection.OUT
    assert target.open_amount == Decimal("100000")
    assert Payment.objects.count() == 2
    assert LiquidityEntry.objects.count() == 2


def test_payment_source_constraint_exists_for_concurrent_idempotency(foundation):
    constraints = Payment._meta.constraints
    assert any(
        isinstance(constraint, UniqueConstraint)
        and tuple(constraint.fields) == ("legal_entity", "source_key")
        for constraint in constraints
    )
