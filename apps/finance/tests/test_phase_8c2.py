from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.finance.models import AccountType, JournalEntry, NormalBalance, PayableEntry
from apps.finance.selectors import (
    accounting_periods,
    period_control_status,
    wage_payable_reconciliation,
)
from apps.finance.services import (
    accrue_wage_payable,
    close_accounting_period,
    create_accounting_period,
    create_coa_account,
    create_coa_mapping,
    create_liquidity_account,
    post_journal,
    post_vendor_payment,
    reverse_wage_payable,
    wage_payable_source_readiness,
)
from apps.organizations.models import LegalEntity, OrganizationMembership

pytestmark = pytest.mark.django_db
DATE = date(2026, 9, 1)


@pytest.fixture
def setup():
    entity = LegalEntity.objects.create(code="8C2", name="Wage Test")
    user = get_user_model().objects.create_user("wage@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    roles = (
        ("PRODUCTION_DIRECT_LABOR", "DEBIT", AccountType.EXPENSE),
        ("WAGE_PAYABLE", "CREDIT", AccountType.LIABILITY),
        ("LIQUIDITY", "CREDIT", AccountType.ASSET),
        ("TEST_DEBIT", "DEBIT", AccountType.EXPENSE),
        ("TEST_CREDIT", "CREDIT", AccountType.LIABILITY),
    )
    accounts = {}
    for role, dc, account_type in roles:
        account = accounts[role] = create_coa_account(
            legal_entity=entity,
            account_code=role[:30],
            account_name=role,
            account_type=account_type,
            normal_balance=NormalBalance.DEBIT if dc == "DEBIT" else NormalBalance.CREDIT,
            effective_from=DATE,
        )
        for event in (
            {"PROD_DIRECT_LABOR", "VENDOR_PAYMENT"}
            if role in {"WAGE_PAYABLE", "LIQUIDITY"}
            else {"PROD_DIRECT_LABOR" if role == "PRODUCTION_DIRECT_LABOR" else "TEST"}
        ):
            if role == "LIQUIDITY" and event == "PROD_DIRECT_LABOR":
                continue
            create_coa_mapping(
                legal_entity=entity,
                module_code="FINANCE",
                event_code=event,
                dimension_type="DEFAULT",
                dimension_value="DEFAULT",
                line_role=role,
                dc=dc,
                account=account,
                effective_from=DATE,
            )
    liquidity = create_liquidity_account(
        legal_entity=entity,
        code="CASH",
        name="Cash",
        account_type="CASH",
        mapping_key="CASH",
        effective_from=DATE,
    )
    return entity, user, liquidity


def source(entity, **overrides):
    values = {
        "legal_entity": entity,
        "source_module": "PRODUCTION",
        "source_type": "ProductionLaborCost",
        "source_id": "LABOR-1",
        "source_key": "PROD_LABOR|LABOR-1",
        "accrual_date": DATE,
        "amount": Decimal("100"),
        "currency": "IDR",
        "event_code": "PROD_DIRECT_LABOR",
        "debit_line_role": "PRODUCTION_DIRECT_LABOR",
        "payable_treatment": "WAGE_PAYABLE",
        "production_lineage": {"work_order_id": "WO-1", "output_id": "OUT-1"},
        "beneficiary_reference": "EMPLOYEE-1",
        "mapping_context": {},
        "source_reference": {"immutable": True},
    }
    values.update(overrides)
    return values


def test_wage_source_accrual_payment_and_reconciliation(setup):
    entity, user, liquidity = setup
    assert wage_payable_source_readiness({"legal_entity": entity})["status"] == "PENDING_SOURCE"
    assert (
        wage_payable_source_readiness(source(entity, payable_treatment="DIRECT_PAID"))["status"]
        == "PENDING_SOURCE"
    )
    assert (
        wage_payable_source_readiness(source(entity, amount="99.5"))["status"] == "PENDING_SOURCE"
    )
    accrual = accrue_wage_payable(source=source(entity), actor=user)
    assert accrue_wage_payable(source=source(entity), actor=user).pk == accrual.pk
    assert accrual.journal.total_debit == accrual.journal.total_credit == 100
    assert accrual.payable_entry.original_amount == accrual.payable_entry.open_amount == 100
    assert accrual.journal.lines.get(line_role="WAGE_PAYABLE").credit == 100
    assert wage_payable_reconciliation(legal_entity=entity)["status"] == "MATCH"
    payment = post_vendor_payment(
        legal_entity=entity,
        liquidity_account=liquidity,
        allocations=[{"payable": accrual.payable_entry, "amount": 40}],
        payment_date=DATE,
        source_key="WAGE-PAY-1",
        actor=user,
    )
    accrual.payable_entry.refresh_from_db()
    assert (
        payment.journal.lines.get(line_role="WAGE_PAYABLE").account_id
        == accrual.journal.lines.get(line_role="WAGE_PAYABLE").account_id
    )
    assert accrual.payable_entry.open_amount == 60
    assert wage_payable_reconciliation(legal_entity=entity)["status"] == "MATCH"
    with pytest.raises(ValidationError):
        post_vendor_payment(
            legal_entity=entity,
            liquidity_account=liquidity,
            allocations=[{"payable": accrual.payable_entry, "amount": 61}],
            payment_date=DATE,
            source_key="WAGE-PAY-OVER",
            actor=user,
        )
    with pytest.raises(ValidationError, match="PAYABLE_ALREADY_SETTLED"):
        reverse_wage_payable(accrual, actor=user)


def test_wage_reversal_is_immutable_and_idempotent(setup):
    entity, user, _ = setup
    accrual = accrue_wage_payable(source=source(entity), actor=user)
    reversal = reverse_wage_payable(accrual, actor=user, accounting_date=DATE)
    accrual.payable_entry.refresh_from_db()
    assert JournalEntry.objects.filter(pk=accrual.journal_id).exists()
    assert reversal.reversal_of_id == accrual.journal_id
    assert accrual.payable_entry.open_amount == 0
    assert reverse_wage_payable(accrual, actor=user, accounting_date=DATE).pk == reversal.pk
    assert wage_payable_reconciliation(legal_entity=entity) == {
        "status": "MATCH",
        "control": 0,
        "detail": 0,
    }


def test_period_activation_and_central_posting(setup):
    entity, user, _ = setup
    assert period_control_status(legal_entity=entity, accounting_date=DATE)["activated"] is False
    period = create_accounting_period(
        legal_entity=entity,
        fiscal_year=2026,
        period_number=9,
        start_date=DATE,
        end_date=date(2026, 9, 30),
        actor=user,
    )
    assert accounting_periods(legal_entity=entity).count() == 1
    with pytest.raises(ValidationError):
        create_accounting_period(
            legal_entity=entity,
            fiscal_year=2026,
            period_number=10,
            start_date=date(2026, 9, 15),
            end_date=date(2026, 10, 15),
            actor=user,
        )
    post_journal(
        legal_entity=entity,
        source_key="OPEN",
        source_module="FINANCE",
        source_document_type="Test",
        source_document_id="1",
        event_code="TEST",
        accounting_date=DATE,
        actor=user,
        lines=(
            ({"line_role": "TEST_DEBIT", "dc": "DEBIT", "amount": 1}),
            ({"line_role": "TEST_CREDIT", "dc": "CREDIT", "amount": 1}),
        ),
    )
    close_accounting_period(period, actor=user, reason="month close")
    before = JournalEntry.objects.count()
    with pytest.raises(ValidationError, match="PERIOD_CLOSED"):
        post_journal(
            legal_entity=entity,
            source_key="CLOSED",
            source_module="FINANCE",
            source_document_type="Test",
            source_document_id="2",
            event_code="TEST",
            accounting_date=DATE,
            actor=user,
            lines=(
                ({"line_role": "TEST_DEBIT", "dc": "DEBIT", "amount": 1}),
                ({"line_role": "TEST_CREDIT", "dc": "CREDIT", "amount": 1}),
            ),
        )
    assert JournalEntry.objects.count() == before
    with pytest.raises(ValidationError, match="PERIOD_NOT_CONFIGURED"):
        accrue_wage_payable(
            source=source(
                entity, source_key="GAP", source_id="GAP", accrual_date=date(2026, 10, 1)
            ),
            actor=user,
        )
    assert PayableEntry.objects.count() == 0
