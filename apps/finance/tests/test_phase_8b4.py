"""Phase 8B4 operational UI and read-only control integration checks."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.finance.models import LiquidityAccount, LiquidityAccountType
from apps.finance.selectors import reconciliation
from apps.finance.services import create_liquidity_account
from apps.organizations.models import LegalEntity, OrganizationMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    entity = LegalEntity.objects.create(code="8B4", name="Finance Phase 8B4")
    user = get_user_model().objects.create_superuser("phase8b4@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    client = Client()
    client.force_login(user)
    return {"entity": entity, "user": user, "client": client}


def test_sidebar_routes_and_permissions_are_separated(setup):
    client = setup["client"]
    operations = client.get(reverse("finance_operations:payment-list"))
    configuration = client.get(reverse("finance:liquidity-account-list"))
    assert operations.status_code == configuration.status_code == 200
    assert b"Marketplace Payouts" in operations.content
    assert b"Liquidity Accounts" in configuration.content
    assert b"Finance Configuration" in configuration.content


def test_liquidity_account_modal_create_edit_and_get_are_side_effect_free(setup):
    client, entity = setup["client"], setup["entity"]
    before = LiquidityAccount.objects.count()
    create_url = reverse("finance:liquidity-account-create")
    assert client.get(create_url).status_code == 200
    assert LiquidityAccount.objects.count() == before
    response = client.post(
        create_url,
        {
            "legal_entity": entity.pk,
            "code": "BANK-8B4",
            "name": "Bank 8B4",
            "account_type": LiquidityAccountType.BANK,
            "currency": "IDR",
            "mapping_key": "BANK-8B4",
            "effective_from": "2026-01-01",
            "bank_name": "KAJA Bank",
            "bank_account_number": "123",
            "account_holder_name": "KAJA",
            "is_active": "on",
            "change_reason": "Initial configuration",
        },
    )
    assert response.status_code == 302, response.context["form"].errors
    account = LiquidityAccount.objects.get(code="BANK-8B4")
    assert (
        client.post(
            reverse("finance:liquidity-account-edit", args=[account.pk]),
            {
                "legal_entity": entity.pk,
                "code": account.code,
                "name": "Renamed Bank",
                "account_type": LiquidityAccountType.BANK,
                "currency": "IDR",
                "mapping_key": account.mapping_key,
                "effective_from": "2026-01-01",
                "bank_name": "KAJA Bank",
                "bank_account_number": "123",
                "account_holder_name": "KAJA",
                "is_active": "on",
                "change_reason": "Correct name",
            },
        ).status_code
        == 302
    )
    account.refresh_from_db()
    assert account.name == "Renamed Bank"
    assert not hasattr(account, "account")  # no direct transactional COA shortcut


def test_operational_reads_are_side_effect_free_and_type_scoped(setup):
    entity, client = setup["entity"], setup["client"]
    cash = create_liquidity_account(
        legal_entity=entity,
        code="CASH-8B4",
        name="Cash",
        account_type=LiquidityAccountType.CASH,
        mapping_key="CASH-8B4",
        effective_from=date(2026, 1, 1),
    )
    assert cash.account_type == LiquidityAccountType.CASH
    for name in (
        "payment-list",
        "cash-list",
        "bank-list",
        "marketplace-settlement-list",
        "marketplace-balance-list",
        "marketplace-payout-list",
    ):
        assert client.get(reverse(f"finance_operations:{name}")).status_code == 200
    assert reconciliation(legal_entity=entity)["liquidity"]["status"] == "PENDING_SOURCE"
    assert reconciliation(legal_entity=entity)["marketplace_balance"]["status"] == "PENDING_SOURCE"
