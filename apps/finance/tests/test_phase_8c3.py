# ruff: noqa: E501
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.finance.models import (
    JournalEntry,
    LiquidityAccount,
    LiquidityAccountType,
    LiquidityDirection,
    LiquidityEntry,
)
from apps.finance.selectors import bank_match_candidates, bank_statement_reconciliation
from apps.finance.services import (
    add_bank_statement_line,
    create_bank_statement,
    match_bank_statement_line,
    unmatch_bank_statement_line,
)
from apps.organizations.models import LegalEntity, OrganizationMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    entity = LegalEntity.objects.create(code="8C3", name="Bank Test")
    user = get_user_model().objects.create_user("bank@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    bank = LiquidityAccount.objects.create(
        legal_entity=entity,
        code="B",
        name="Bank",
        account_type=LiquidityAccountType.BANK,
        mapping_key="B",
        effective_from=date(2026, 1, 1),
    )
    cash = LiquidityAccount.objects.create(
        legal_entity=entity,
        code="C",
        name="Cash",
        account_type=LiquidityAccountType.CASH,
        mapping_key="C",
        effective_from=date(2026, 1, 1),
    )
    journal = JournalEntry.objects.create(
        legal_entity=entity,
        journal_number="J",
        accounting_date=date(2026, 9, 1),
        event_code="T",
        source_module="T",
        source_document_type="T",
        source_document_id="1",
        source_key="J",
        total_debit=100,
        total_credit=100,
        posted_at=timezone.now(),
        posted_by=user,
    )
    entry = LiquidityEntry.objects.create(
        legal_entity=entity,
        liquidity_account=bank,
        journal=journal,
        transaction_date=date(2026, 9, 1),
        direction=LiquidityDirection.IN,
        amount=100,
        source_module="T",
        source_document_type="T",
        source_document_id="1",
        source_key="L",
        posted_at=timezone.now(),
        posted_by=user,
    )
    return entity, user, bank, cash, entry


def test_statement_evidence_matching_and_unmatch(setup):
    entity, user, bank, cash, entry = setup
    with pytest.raises(ValidationError):
        create_bank_statement(
            legal_entity=entity,
            liquidity_account=cash,
            statement_reference="CASH",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 1),
            opening_balance=0,
            closing_balance=100,
        )
    statement = create_bank_statement(
        legal_entity=entity,
        liquidity_account=bank,
        statement_reference="S1",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
        opening_balance=0,
        closing_balance=100,
        actor=user,
    )
    line = add_bank_statement_line(
        statement=statement,
        source_identity="1",
        transaction_date=date(2026, 9, 1),
        direction="IN",
        amount=100,
        sequence=1,
    )
    assert (
        add_bank_statement_line(
            statement=statement,
            source_identity="1",
            transaction_date=date(2026, 9, 1),
            direction="IN",
            amount=100,
            sequence=1,
        ).pk
        == line.pk
    )
    before = (JournalEntry.objects.count(), LiquidityEntry.objects.count())
    match = match_bank_statement_line(
        statement_line=line, liquidity_entry=entry, amount=100, source_key="M1", actor=user
    )
    assert bank_statement_reconciliation(statement=statement)["status"] == "MATCH"
    assert list(bank_match_candidates(statement_line=line)) == [entry]
    assert (JournalEntry.objects.count(), LiquidityEntry.objects.count()) == before
    assert (
        unmatch_bank_statement_line(match, actor=user, reason="evidence correction").state
        == "REVERSED"
    )
    assert bank_statement_reconciliation(statement=statement)[
        "unmatched_statement_amount"
    ] == Decimal("100")


def test_statement_balance_source_and_match_guards(setup):
    entity, user, bank, _, entry = setup
    statement = create_bank_statement(
        legal_entity=entity,
        liquidity_account=bank,
        statement_reference="S2",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
        closing_balance=100,
        actor=user,
    )
    line = add_bank_statement_line(
        statement=statement,
        source_identity="2",
        transaction_date=date(2026, 9, 1),
        direction="IN",
        amount=100,
        sequence=1,
    )
    assert (
        bank_statement_reconciliation(statement=statement)["statement_arithmetic"]
        == "PENDING_SOURCE"
    )
    with pytest.raises(ValidationError):
        match_bank_statement_line(
            statement_line=line, liquidity_entry=entry, amount=101, source_key="OVER", actor=user
        )
