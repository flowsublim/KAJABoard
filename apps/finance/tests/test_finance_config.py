from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.finance.models import AccountType, DCDirection, MappingDimensionType, NormalBalance
from apps.finance.selectors import effective_coa_accounts
from apps.finance.services import (
    FinanceMappingError,
    create_coa_account,
    create_coa_mapping,
    deactivate_coa_account,
    resolve_account_mapping,
)
from apps.organizations.models import LegalEntity, OrganizationMembership

User = get_user_model()


@pytest.fixture
def entity():
    return LegalEntity.objects.create(code="KAJA", name="PT KAJA")


@pytest.fixture
def user(entity):
    user = User.objects.create_user("member@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    return user


def make_account(entity, code="5101", name="Expense", *, active_from=None):
    return create_coa_account(
        legal_entity=entity,
        account_code=code,
        account_name=name,
        account_type=AccountType.EXPENSE,
        normal_balance=NormalBalance.DEBIT,
        effective_from=active_from or date(2026, 1, 1),
    )


@pytest.mark.django_db
def test_coa_hierarchy_cycle_is_rejected(entity):
    future = timezone.localdate() + timedelta(days=1)
    parent = make_account(entity, code="5000", name="Expenses", active_from=future)
    child = make_account(entity, code="5101", name="Office Expense", active_from=future)
    child.parent = parent
    child.save()

    with pytest.raises(ValidationError, match="cycle"):
        from apps.finance.services import update_coa_account

        update_coa_account(parent, parent=child, reason="Invalid parent")


@pytest.mark.django_db
def test_inactive_historical_coa_remains_resolvable_for_prior_date(entity, user):
    yesterday = timezone.localdate() - timedelta(days=1)
    account = make_account(entity, active_from=yesterday)
    deactivate_coa_account(account, reason="Closed")

    assert effective_coa_accounts(user, business_date=yesterday).get() == account
    assert not effective_coa_accounts(user).filter(pk=account.pk).exists()


@pytest.mark.django_db
def test_coa_successor_version_resolves_by_business_date(entity, user):
    old_account = make_account(
        entity,
        code="5101",
        name="Old Expense",
        active_from=date(2026, 1, 1),
    )
    old_account.effective_to = date(2026, 6, 30)
    old_account.save(update_fields=("effective_to", "updated_at"))
    new_account = make_account(
        entity,
        code="5101",
        name="Replacement Expense",
        active_from=date(2026, 7, 1),
    )

    assert effective_coa_accounts(user, business_date=date(2026, 6, 1)).get() == old_account
    assert effective_coa_accounts(user, business_date=date(2026, 8, 1)).get() == new_account


@pytest.mark.django_db
def test_mapping_exact_dimension_beats_default_and_returns_snapshot_metadata(entity):
    default_account = make_account(entity, code="5101", name="Default Expense")
    store_account = make_account(entity, code="5102", name="Store Expense")
    create_coa_mapping(
        legal_entity=entity,
        module_code="PURCH",
        event_code="PURCH_EXPENSE_PURCHASE",
        dimension_type=MappingDimensionType.DEFAULT,
        dimension_value="ignored",
        line_role="EXPENSE",
        dc=DCDirection.DEBIT,
        account=default_account,
        priority=999,
        effective_from=date(2026, 1, 1),
    )
    exact = create_coa_mapping(
        legal_entity=entity,
        module_code="PURCH",
        event_code="PURCH_EXPENSE_PURCHASE",
        dimension_type=MappingDimensionType.STORE,
        dimension_value="STORE-A",
        line_role="EXPENSE",
        dc=DCDirection.DEBIT,
        account=store_account,
        priority=1,
        effective_from=date(2026, 1, 1),
    )

    result = resolve_account_mapping(
        legal_entity=entity,
        module_code="PURCH",
        event_code="PURCH_EXPENSE_PURCHASE",
        line_role="EXPENSE",
        dc=DCDirection.DEBIT,
        business_date=date(2026, 8, 1),
        context={"STORE": "store-a"},
    )

    assert result.mapping_id == str(exact.pk)
    assert result.account_code == "5102"
    assert result.selected_dimension_type == MappingDimensionType.STORE


@pytest.mark.django_db
def test_mapping_priority_and_ambiguity_are_explicit(entity):
    low = make_account(entity, code="5101", name="Low")
    high = make_account(entity, code="5102", name="High")
    duplicate_high = make_account(entity, code="5103", name="Duplicate High")
    for account, priority, value in (
        (low, 10, "CC-LOW"),
        (high, 20, "CC-HIGH"),
        (duplicate_high, 20, "STORE-HIGH"),
    ):
        create_coa_mapping(
            legal_entity=entity,
            module_code="PURCH",
            event_code="PURCH_SERVICE_PURCHASE",
            dimension_type=(
                MappingDimensionType.COST_CENTER
                if value.startswith("CC")
                else MappingDimensionType.STORE
            ),
            dimension_value=value,
            line_role="EXPENSE",
            dc=DCDirection.DEBIT,
            account=account,
            priority=priority,
            effective_from=date(2026, 1, 1),
        )

    with pytest.raises(FinanceMappingError, match="Ambiguous"):
        resolve_account_mapping(
            legal_entity=entity,
            module_code="PURCH",
            event_code="PURCH_SERVICE_PURCHASE",
            line_role="EXPENSE",
            dc=DCDirection.DEBIT,
            business_date=date(2026, 8, 1),
            context={"COST_CENTER": "CC-HIGH", "STORE": "STORE-HIGH"},
        )


@pytest.mark.django_db
def test_resolver_rejects_inactive_account_at_as_of_date(entity):
    account = make_account(entity)
    mapping = create_coa_mapping(
        legal_entity=entity,
        module_code="PURCH",
        event_code="PURCH_EXPENSE_PURCHASE",
        dimension_type=MappingDimensionType.DEFAULT,
        dimension_value="DEFAULT",
        line_role="EXPENSE",
        dc=DCDirection.DEBIT,
        account=account,
        effective_from=date(2026, 1, 1),
    )
    deactivate_coa_account(account, reason="Closed")

    with pytest.raises(FinanceMappingError, match="inactive"):
        resolve_account_mapping(
            legal_entity=entity,
            module_code=mapping.module_code,
            event_code=mapping.event_code,
            line_role=mapping.line_role,
            business_date=timezone.localdate(),
        )


@pytest.mark.django_db
def test_coa_mapping_overlap_and_audit(entity):
    account = make_account(entity)
    mapping = create_coa_mapping(
        legal_entity=entity,
        module_code="PURCH",
        event_code="PURCH_EXPENSE_PURCHASE",
        dimension_type=MappingDimensionType.DEFAULT,
        dimension_value="DEFAULT",
        line_role="EXPENSE",
        dc=DCDirection.DEBIT,
        account=account,
        priority=100,
        effective_from=date(2026, 1, 1),
    )

    with pytest.raises(ValidationError, match="cannot overlap"):
        create_coa_mapping(
            legal_entity=entity,
            module_code="PURCH",
            event_code="PURCH_EXPENSE_PURCHASE",
            dimension_type=MappingDimensionType.DEFAULT,
            dimension_value="DEFAULT",
            line_role="EXPENSE",
            dc=DCDirection.DEBIT,
            account=account,
            priority=100,
            effective_from=date(2026, 6, 1),
        )
    assert AuditEvent.objects.filter(
        target_id=str(mapping.pk),
        action="finance.coamapping.created",
    ).exists()
