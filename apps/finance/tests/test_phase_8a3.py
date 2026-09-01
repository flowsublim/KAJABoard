from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from apps.channels.models import Store
from apps.finance.models import (
    AccountType,
    JournalEntry,
    JournalLine,
    NormalBalance,
    ReceivableEntry,
)
from apps.finance.services import create_coa_account
from apps.organizations.models import LegalEntity, OrganizationMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def foundation():
    entity = LegalEntity.objects.create(code="8A3", name="Finance Phase 8A3")
    user = get_user_model().objects.create_user("phase8a3@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    store = Store.objects.create(
        legal_entity=entity,
        code="STORE-8A3",
        name="Marketplace Store 8A3",
        channel="SHOPEE",
        effective_from=date(2026, 1, 1),
    )
    return {"entity": entity, "user": user, "store": store}


def grant(user, *codenames):
    user.user_permissions.add(
        *Permission.objects.filter(content_type__app_label="finance", codename__in=codenames)
    )


def create_marketplace_receivable(foundation):
    ar_account = create_coa_account(
        legal_entity=foundation["entity"],
        account_code="1108A3",
        account_name="Marketplace Receivable",
        account_type=AccountType.ASSET,
        normal_balance=NormalBalance.DEBIT,
        effective_from=date(2026, 1, 1),
    )
    revenue_account = create_coa_account(
        legal_entity=foundation["entity"],
        account_code="4108A3",
        account_name="Marketplace Revenue",
        account_type=AccountType.REVENUE,
        normal_balance=NormalBalance.CREDIT,
        effective_from=date(2026, 1, 1),
    )
    journal = JournalEntry.objects.create(
        legal_entity=foundation["entity"],
        journal_number="JRN-8A3-001",
        accounting_date=date(2026, 9, 1),
        event_code="OMNI_ORDER_COMPLETED",
        source_module="OMNI",
        source_document_type="OmniRevenueEvent",
        source_document_id="OMNI-8A3",
        source_key="OMNI_COMPLETION|8A3",
        source_reference={"external_order_number": "ORDER-8A3"},
        total_debit=Decimal("150000"),
        total_credit=Decimal("150000"),
        description="Marketplace completion",
        posted_at=timezone.now(),
        posted_by=foundation["user"],
    )
    JournalLine.objects.create(
        journal=journal,
        sequence=1,
        line_role="RECEIVABLE",
        account=ar_account,
        account_code_snapshot=ar_account.account_code,
        account_name_snapshot=ar_account.account_name,
        debit=Decimal("150000"),
        mapping_snapshot={"mapping_id": "MAP-AR-8A3"},
    )
    JournalLine.objects.create(
        journal=journal,
        sequence=2,
        line_role="REVENUE",
        account=revenue_account,
        account_code_snapshot=revenue_account.account_code,
        account_name_snapshot=revenue_account.account_name,
        credit=Decimal("150000"),
        mapping_snapshot={"mapping_id": "MAP-REV-8A3"},
    )
    ReceivableEntry.objects.create(
        journal=journal,
        legal_entity=foundation["entity"],
        accounting_date=journal.accounting_date,
        original_amount=Decimal("150000"),
        open_amount=Decimal("150000"),
        store=foundation["store"],
    )
    return journal


def test_finance_operational_sidebar_permission_visibility(client, foundation):
    grant(foundation["user"], "view_gl")
    client.force_login(foundation["user"])

    content = client.get(reverse("home:home")).content

    assert b"Operasional" in content
    assert b"<summary>Finance</summary>" in content
    assert b"General Ledger" in content
    assert b"Finance Configuration" not in content


def test_finance_operational_parent_hidden_without_permission(client, foundation):
    client.force_login(foundation["user"])

    content = client.get(reverse("home:home")).content

    assert b"<summary>Finance</summary>" not in content
    assert client.get(reverse("finance_operations:general-ledger")).status_code == 403


def test_finance_configuration_stays_separate_and_route_active(client, foundation):
    grant(foundation["user"], "view_coaaccount")
    client.force_login(foundation["user"])

    response = client.get(reverse("finance:account-list"))

    assert response.status_code == 200
    assert b"Master &amp; Konfigurasi" in response.content
    active_configuration_prefix = b'nav-module is-active" open>'
    active_configuration = active_configuration_prefix + b"<summary>Finance Configuration</summary>"
    assert active_configuration in response.content
    assert b"<summary>Finance</summary>" not in response.content


def test_operational_route_opens_only_operational_finance(client, foundation):
    grant(foundation["user"], "view_gl", "view_coaaccount")
    client.force_login(foundation["user"])

    response = client.get(reverse("finance_operations:general-ledger"))

    assert response.status_code == 200
    assert b'nav-module is-active" open><summary>Finance</summary>' in response.content
    configuration_position = response.content.index(b"<summary>Finance Configuration</summary>")
    configuration_parent_start = configuration_position - 80
    configuration_parent = response.content[configuration_parent_start:configuration_position]
    assert b"is-active" not in configuration_parent


def test_superuser_sees_all_phase_8a_operational_children(client):
    user = get_user_model().objects.create_superuser("finance8a-admin@example.com", "password")
    client.force_login(user)

    content = client.get(reverse("home:home")).content

    for label in (
        b"<summary>Finance</summary>",
        b">Journal<",
        b">General Ledger<",
        b">Accounts Receivable<",
        b">Accounts Payable<",
        b">Reconciliation<",
        b"<summary>Finance Configuration</summary>",
    ):
        assert label in content


def test_finance_read_pages_render_source_data_without_side_effects(client, foundation):
    grant(
        foundation["user"],
        "view_journalentry",
        "view_gl",
        "view_ar",
        "view_ap",
        "view_reconciliation",
    )
    journal = create_marketplace_receivable(foundation)
    client.force_login(foundation["user"])
    before = (
        JournalEntry.objects.count(),
        JournalLine.objects.count(),
        ReceivableEntry.objects.count(),
    )

    routes = (
        "finance_operations:journal-list",
        "finance_operations:general-ledger",
        "finance_operations:receivable-list",
        "finance_operations:payable-list",
        "finance_operations:reconciliation",
    )
    responses = {route: client.get(reverse(route)) for route in routes}
    detail = client.get(reverse("finance_operations:journal-detail", args=(journal.pk,)))

    assert all(response.status_code == 200 for response in responses.values())
    assert detail.status_code == 200
    assert journal.journal_number.encode() in responses["finance_operations:journal-list"].content
    assert b"OMNI_COMPLETION|8A3" in responses["finance_operations:general-ledger"].content
    assert b"Marketplace Store 8A3" in responses["finance_operations:receivable-list"].content
    assert (
        b"No approved operational AP source is integrated yet"
        in responses["finance_operations:payable-list"].content
    )
    reconciliation_content = responses["finance_operations:reconciliation"].content
    assert b"MATCH" in reconciliation_content
    assert b"PENDING_SOURCE" in reconciliation_content
    assert b"MAP-AR-8A3" in detail.content
    after = (
        JournalEntry.objects.count(),
        JournalLine.objects.count(),
        ReceivableEntry.objects.count(),
    )
    assert after == before


def test_phase_8a_operational_routes_do_not_replace_existing_namespaces():
    assert reverse("finance_operations:journal-list") == "/finance/journals/"
    assert reverse("finance:account-list") == "/settings/finance/coa/"
    assert reverse("purchasing_operations:order-list") == "/purchasing/"
    assert reverse("omnichannel:order-list") == "/omnichannel/orders/"
    assert reverse("omnichannel:pos-sale-list") == "/omnichannel/pos/"
