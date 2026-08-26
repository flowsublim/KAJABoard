from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.organizations.models import CostCenter, LegalEntity, OrganizationMembership
from apps.purchasing.models import AccountingTreatment
from apps.purchasing.selectors import effective_purchase_categories, purchase_categories
from apps.purchasing.services import create_purchase_category, deactivate_purchase_category

User = get_user_model()


@pytest.fixture
def entity():
    return LegalEntity.objects.create(code="KAJA", name="PT KAJA")


@pytest.fixture
def user(entity):
    user = User.objects.create_user("member@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    return user


@pytest.fixture
def production_cc(entity):
    return CostCenter.objects.create(
        legal_entity=entity,
        code="PROD",
        name="Production Overhead",
        is_production_overhead_eligible=True,
        effective_from=date(2026, 1, 1),
    )


@pytest.fixture
def office_cc(entity):
    return CostCenter.objects.create(
        legal_entity=entity,
        code="OFFICE",
        name="Office",
        is_production_overhead_eligible=False,
        effective_from=date(2026, 1, 1),
    )


@pytest.mark.django_db
def test_expense_and_service_require_cost_center(entity):
    with pytest.raises(ValidationError, match="require a Cost Center"):
        create_purchase_category(
            legal_entity=entity,
            code="OFFICE-EXP",
            name="Office Expense",
            accounting_treatment=AccountingTreatment.EXPENSE,
        )


@pytest.mark.django_db
def test_asset_purchase_category_does_not_require_inventory_behavior(entity):
    category = create_purchase_category(
        legal_entity=entity,
        code="LAPTOP",
        name="Laptop Asset",
        accounting_treatment=AccountingTreatment.ASSET,
        asset_class_reference="FIXED_ASSET_IT",
    )

    assert category.accounting_treatment == AccountingTreatment.ASSET
    assert category.inventory_classification == ""


@pytest.mark.django_db
def test_production_snapshot_requires_expense_or_service_and_eligible_cost_center(
    entity,
    office_cc,
    production_cc,
):
    with pytest.raises(ValidationError, match="only for EXPENSE/SERVICE"):
        create_purchase_category(
            legal_entity=entity,
            code="INV-PROD",
            name="Inventory Named Produksi",
            accounting_treatment=AccountingTreatment.INVENTORY,
            snapshot_production=True,
        )
    with pytest.raises(ValidationError, match="not production-overhead eligible"):
        create_purchase_category(
            legal_entity=entity,
            code="OFFICE-PROD",
            name="Office Produksi",
            accounting_treatment=AccountingTreatment.EXPENSE,
            cost_center=office_cc,
            snapshot_production=True,
        )

    category = create_purchase_category(
        legal_entity=entity,
        code="OVERHEAD",
        name="Production Utilities",
        accounting_treatment=AccountingTreatment.SERVICE,
        cost_center=production_cc,
        snapshot_production=True,
    )

    assert category.snapshot_production is True


@pytest.mark.django_db
def test_category_overlap_and_historical_resolution(entity, user, office_cc):
    yesterday = timezone.localdate() - timedelta(days=1)
    category = create_purchase_category(
        legal_entity=entity,
        code="EXP-001",
        name="Old Expense",
        accounting_treatment=AccountingTreatment.EXPENSE,
        cost_center=office_cc,
        effective_from=yesterday,
    )

    with pytest.raises(ValidationError, match="cannot overlap"):
        create_purchase_category(
            legal_entity=entity,
            code="exp-001",
            name="Overlap",
            accounting_treatment=AccountingTreatment.EXPENSE,
            cost_center=office_cc,
            effective_from=yesterday,
        )

    deactivate_purchase_category(category, reason="Closed")

    assert effective_purchase_categories(user, business_date=yesterday).get() == category
    assert not effective_purchase_categories(user).filter(pk=category.pk).exists()
    assert AuditEvent.objects.filter(
        target_id=str(category.pk),
        action="purchasing.purchasecategory.deactivated",
    ).exists()


@pytest.mark.django_db
def test_purchase_category_selector_enforces_membership_scope(entity, user, office_cc):
    allowed = create_purchase_category(
        legal_entity=entity,
        code="EXP-ALLOWED",
        name="Allowed",
        accounting_treatment=AccountingTreatment.EXPENSE,
        cost_center=office_cc,
    )
    other_entity = LegalEntity.objects.create(code="OTHER", name="Other")
    other_cc = CostCenter.objects.create(
        legal_entity=other_entity,
        code="OTHER-CC",
        name="Other CC",
        effective_from=date(2026, 1, 1),
    )
    create_purchase_category(
        legal_entity=other_entity,
        code="EXP-OTHER",
        name="Other",
        accounting_treatment=AccountingTreatment.EXPENSE,
        cost_center=other_cc,
    )

    assert list(purchase_categories(user)) == [allowed]
