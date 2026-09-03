from datetime import date

import pytest
from django.contrib.auth import get_user_model

from apps.finance.models import AccountType, AssetClass, JournalEntry, JournalState, NormalBalance
from apps.finance.selectors import fixed_asset_reconciliation
from apps.finance.services import (
    asset_acquisition_readiness,
    capitalize_fixed_asset,
    create_coa_account,
    create_coa_mapping,
    generate_depreciation_schedule,
    post_depreciation,
    reverse_depreciation,
)
from apps.organizations.models import LegalEntity, OrganizationMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    entity = LegalEntity.objects.create(code="8C1", name="Asset Test")
    user = get_user_model().objects.create_user("asset@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    asset_class = AssetClass.objects.create(
        legal_entity=entity,
        code="IT",
        name="IT",
        mapping_key="IT",
        default_useful_life_months=3,
        effective_from=date(2026, 1, 1),
    )
    for role, dc, account_type in (
        ("FIXED_ASSET", "DEBIT", AccountType.ASSET),
        ("ACQUISITION_CLEARING", "CREDIT", AccountType.LIABILITY),
        ("DEPRECIATION_EXPENSE", "DEBIT", AccountType.EXPENSE),
        ("ACCUMULATED_DEPRECIATION", "CREDIT", AccountType.ASSET),
    ):
        account = create_coa_account(
            legal_entity=entity,
            account_code=role[:30],
            account_name=role,
            account_type=account_type,
            normal_balance=NormalBalance.DEBIT if dc == "DEBIT" else NormalBalance.CREDIT,
            effective_from=date(2026, 1, 1),
        )
        create_coa_mapping(
            legal_entity=entity,
            module_code="FINANCE",
            event_code="PURCH_ASSET_PURCHASE"
            if role in {"FIXED_ASSET", "ACQUISITION_CLEARING"}
            else "FIXED_ASSET_DEPRECIATION",
            dimension_type="PURCHASE_CATEGORY",
            dimension_value="IT",
            line_role=role,
            dc=dc,
            account=account,
            effective_from=date(2026, 1, 1),
        )
    return entity, user, asset_class


def test_asset_requires_approved_source_and_capitalizes_idempotently(setup):
    _, user, asset_class = setup
    assert asset_acquisition_readiness(None)["status"] == "PENDING_SOURCE"
    source = {"approved": True, "source_key": "APPROVED-ASSET-1"}
    asset = capitalize_fixed_asset(
        asset_class=asset_class,
        name="Laptop",
        acquisition_date=date(2026, 1, 1),
        capitalization_date=date(2026, 1, 1),
        acquisition_cost=100,
        residual_value=1,
        source=source,
        actor=user,
    )
    assert asset.capitalization_journal.total_debit == 100
    assert (
        capitalize_fixed_asset(
            asset_class=asset_class,
            name="Changed",
            acquisition_date=date(2026, 1, 1),
            capitalization_date=date(2026, 1, 1),
            acquisition_cost=100,
            residual_value=1,
            source=source,
            actor=user,
        ).pk
        == asset.pk
    )


def test_schedule_depreciation_and_reversal(setup):
    _, user, asset_class = setup
    asset = capitalize_fixed_asset(
        asset_class=asset_class,
        name="Laptop",
        acquisition_date=date(2026, 1, 1),
        capitalization_date=date(2026, 1, 1),
        acquisition_cost=100,
        residual_value=1,
        source={"approved": True, "source_key": "APPROVED-ASSET-2"},
        actor=user,
    )
    schedule = list(generate_depreciation_schedule(asset))
    assert sum(row.scheduled_amount for row in schedule) == 99
    posted = post_depreciation(schedule[0], actor=user)
    assert posted.journal.total_debit == posted.journal.total_credit == posted.scheduled_amount
    before_reversal = fixed_asset_reconciliation(legal_entity=asset.legal_entity)
    assert before_reversal["accumulated_depreciation"] == {
        "status": "MATCH",
        "control": posted.scheduled_amount,
        "detail": posted.scheduled_amount,
    }
    nbv_after_depreciation = before_reversal["net_book_value"]

    reversal = reverse_depreciation(posted, actor=user)
    assert reversal.reversal_of_id == posted.journal_id
    posted.journal.refresh_from_db()
    assert posted.journal.state == JournalState.REVERSED
    assert JournalEntry.objects.filter(pk=posted.journal_id).exists()
    assert JournalEntry.objects.filter(pk=reversal.pk).exists()
    assert set(reversal.lines.values_list("line_role", flat=True)) == {
        "DEPRECIATION_EXPENSE",
        "ACCUMULATED_DEPRECIATION",
    }

    after_reversal = fixed_asset_reconciliation(legal_entity=asset.legal_entity)
    assert after_reversal["accumulated_depreciation"] == {
        "status": "MATCH",
        "control": 0,
        "detail": 0,
    }
    assert after_reversal["net_book_value"] == asset.acquisition_cost
    assert after_reversal["net_book_value"] > nbv_after_depreciation
    assert reverse_depreciation(posted, actor=user).pk == reversal.pk


def test_reconciliation_reports_pending_without_capitalization(setup):
    entity, _, _ = setup
    result = fixed_asset_reconciliation(legal_entity=entity)
    assert result["acquisition"]["status"] == "PENDING_SOURCE"
    assert result["accumulated_depreciation"]["status"] == "PENDING_SOURCE"
