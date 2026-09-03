from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.finance.models import (
    AccountingPeriod,
    BankReconciliationMatch,
    DepreciationScheduleEntry,
    FixedAsset,
    JournalEntry,
    LiquidityAccount,
    LiquidityAccountType,
    LiquidityDirection,
    LiquidityEntry,
    MarketplaceBalanceEntry,
    Payment,
    WagePayableAccrual,
)
from apps.finance.selectors import bank_statement_reconciliation, reconciliation
from apps.finance.services import (
    add_bank_statement_line,
    create_bank_statement,
    match_bank_statement_line,
)
from apps.organizations.models import LegalEntity, OrganizationMembership

pytestmark = pytest.mark.django_db


def _counts():
    return {
        model.__name__: model.objects.count()
        for model in (
            JournalEntry,
            Payment,
            LiquidityEntry,
            MarketplaceBalanceEntry,
            FixedAsset,
            DepreciationScheduleEntry,
            WagePayableAccrual,
            AccountingPeriod,
            BankReconciliationMatch,
        )
    }


@pytest.fixture
def bank_evidence():
    entity = LegalEntity.objects.create(code="8C3B1", name="Reconciliation Test")
    user = get_user_model().objects.create_superuser("reconcile@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    bank = LiquidityAccount.objects.create(
        legal_entity=entity,
        code="BANK",
        name="Bank",
        account_type=LiquidityAccountType.BANK,
        mapping_key="BANK",
        effective_from=date(2026, 1, 1),
    )
    journal = JournalEntry.objects.create(
        legal_entity=entity,
        journal_number="REC-BANK-1",
        accounting_date=date(2026, 9, 1),
        event_code="TEST",
        source_module="TEST",
        source_document_type="Test",
        source_document_id="1",
        source_key="REC-BANK-1",
        total_debit=Decimal("100"),
        total_credit=Decimal("100"),
        posted_by=user,
        posted_at=timezone.now(),
    )
    entry = LiquidityEntry.objects.create(
        legal_entity=entity,
        liquidity_account=bank,
        journal=journal,
        transaction_date=date(2026, 9, 1),
        direction=LiquidityDirection.IN,
        amount=Decimal("100"),
        source_module="TEST",
        source_document_type="Test",
        source_document_id="1",
        source_key="REC-LIQUIDITY-1",
        posted_by=user,
        posted_at=timezone.now(),
    )
    statement = create_bank_statement(
        legal_entity=entity,
        liquidity_account=bank,
        statement_reference="REC-STATEMENT-1",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
        opening_balance=Decimal("0"),
        closing_balance=Decimal("100"),
        actor=user,
    )
    line = add_bank_statement_line(
        statement=statement,
        source_identity="REC-LINE-1",
        transaction_date=date(2026, 9, 1),
        direction=LiquidityDirection.IN,
        amount=Decimal("100"),
        sequence=1,
        actor=user,
    )
    match_bank_statement_line(
        statement_line=line,
        liquidity_entry=entry,
        amount=Decimal("100"),
        source_key="REC-MATCH-1",
        actor=user,
    )
    return entity, user, bank, statement


def test_reconciliation_contract_includes_all_phase_8_controls(bank_evidence):
    entity, _, _, statement = bank_evidence

    result = reconciliation(legal_entity=entity)

    assert set(result) == {
        "journal",
        "ar",
        "ap",
        "inventory",
        "liquidity",
        "marketplace_balance",
        "fixed_assets",
        "wage_payable",
        "bank_reconciliation",
    }
    assert result["journal"]["status"] == "MATCH"
    assert result["liquidity"] == {
        "status": "DIFFERENCE",
        "control": Decimal("0"),
        "detail": Decimal("100"),
    }
    assert result["bank_reconciliation"]["status"] == "MATCH"
    assert result["fixed_assets"]["acquisition"]["status"] == "PENDING_SOURCE"
    assert result["wage_payable"]["status"] == "PENDING_SOURCE"
    assert bank_statement_reconciliation(statement=statement)["unmatched_ledger_amount"] == 0


def test_reconciliation_and_page_reads_have_no_side_effects(bank_evidence):
    entity, user, _, statement = bank_evidence
    before = _counts()

    reconciliation(legal_entity=entity)
    bank_statement_reconciliation(statement=statement)
    client = Client()
    client.force_login(user)
    response = client.get(reverse("finance_operations:reconciliation"), {"legal_entity": entity.pk})

    assert response.status_code == 200
    assert "Bank Reconciliation" in response.content.decode()
    assert _counts() == before
