from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.organizations.models import (
    CostCenterCategory,
    LegalEntity,
    OrganizationMembership,
    Warehouse,
)
from apps.organizations.selectors import accessible_legal_entities, effective_warehouses
from apps.organizations.services import (
    create_business_unit,
    create_cost_center,
    create_department,
    create_legal_entity,
    create_warehouse,
    deactivate_master,
    update_department,
)

User = get_user_model()


@pytest.mark.django_db
def test_legal_entity_code_is_case_insensitively_unique():
    LegalEntity.objects.create(code="KAJA", name="PT Kaja Vastraloka Kreasindo")

    with pytest.raises(IntegrityError), transaction.atomic():
        LegalEntity.objects.create(code="kaja", name="Duplicate")


@pytest.mark.django_db
def test_membership_assigns_user_to_legal_entity_once():
    user = User.objects.create_user("owner@example.com", "strong-test-password")
    entity = LegalEntity.objects.create(code="KAJA", name="PT Kaja Vastraloka Kreasindo")
    membership = OrganizationMembership.objects.create(user=user, legal_entity=entity)

    assert membership.is_active is True
    with pytest.raises(IntegrityError), transaction.atomic():
        OrganizationMembership.objects.create(user=user, legal_entity=entity)


@pytest.mark.django_db
def test_legal_entity_with_membership_cannot_be_deleted_silently():
    user = User.objects.create_user("owner@example.com", "strong-test-password")
    entity = LegalEntity.objects.create(code="KAJA", name="PT Kaja Vastraloka Kreasindo")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)

    with pytest.raises(ProtectedError):
        entity.delete()


@pytest.mark.django_db
def test_organization_services_normalize_identifiers_and_write_audit():
    actor = User.objects.create_user("owner@example.com", "strong-test-password")

    entity = create_legal_entity(
        code=" kaja ",
        name="PT KAJA VASTRALOKA KREASINDO",
        npwp=" 01 234 ",
        actor=actor,
        reason="Initial master",
        idempotency_key="org-create-1",
    )

    assert entity.code == "KAJA"
    assert entity.npwp == "01234"
    event = AuditEvent.objects.get(target_id=str(entity.pk))
    assert event.action == "organizations.legalentity.created"
    assert event.actor == actor
    assert event.reason == "Initial master"
    assert event.idempotency_key == "org-create-1"


@pytest.mark.django_db
def test_effective_period_rejects_end_before_start():
    with pytest.raises(ValidationError, match="Effective to cannot be before"):
        create_legal_entity(
            code="KAJA",
            name="PT KAJA",
            effective_from=date(2026, 8, 25),
            effective_to=date(2026, 8, 24),
        )


@pytest.mark.django_db
def test_organization_hierarchy_requires_same_legal_entity():
    first = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    second = LegalEntity.objects.create(code="OTHER", name="PT OTHER")
    unit = create_business_unit(legal_entity=first, code="KIRAL", name="Kiral")

    with pytest.raises(ValidationError, match="same legal entity"):
        create_department(
            legal_entity=second,
            business_unit=unit,
            code="OPS",
            name="Operations",
        )


@pytest.mark.django_db
def test_production_overhead_eligibility_is_explicit_not_inferred_from_category_or_name():
    entity = LegalEntity.objects.create(code="KAJA", name="PT KAJA")

    office_named_production = create_cost_center(
        legal_entity=entity,
        code="OFF-PROD",
        name="Production Administration Office",
        category=CostCenterCategory.OFFICE,
        is_production_overhead_eligible=False,
    )
    explicitly_eligible = create_cost_center(
        legal_entity=entity,
        code="CC-X",
        name="Cutting Floor",
        category=CostCenterCategory.PRODUCTION,
        is_production_overhead_eligible=True,
    )

    assert office_named_production.is_production_overhead_eligible is False
    assert explicitly_eligible.is_production_overhead_eligible is True


@pytest.mark.django_db
def test_only_one_default_warehouse_per_legal_entity():
    entity = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    create_warehouse(legal_entity=entity, code="MAIN", name="Main", is_default=True)

    with pytest.raises(ValidationError), transaction.atomic():
        create_warehouse(legal_entity=entity, code="SECOND", name="Second", is_default=True)


@pytest.mark.django_db
def test_deactivation_requires_reason_and_preserves_master_record():
    entity = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    warehouse = create_warehouse(legal_entity=entity, code="MAIN", name="Main")

    with pytest.raises(ValidationError, match="reason is required"):
        deactivate_master(warehouse, reason="")

    deactivated = deactivate_master(warehouse, reason="No longer used")
    assert deactivated.is_active is False
    assert deactivated.effective_to is not None
    assert Warehouse.objects.filter(pk=warehouse.pk).exists()
    assert AuditEvent.objects.filter(
        target_id=str(warehouse.pk), action="organizations.warehouse.deactivated"
    ).exists()


@pytest.mark.django_db
def test_deactivated_warehouse_remains_selectable_for_prior_business_date():
    user = User.objects.create_user("member@example.com", "strong-test-password")
    entity = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    yesterday = timezone.localdate() - timedelta(days=1)
    warehouse = create_warehouse(
        legal_entity=entity,
        code="MAIN",
        name="Main",
        effective_from=yesterday,
    )

    deactivate_master(warehouse, reason="No longer used")

    assert effective_warehouses(user, business_date=yesterday).get() == warehouse
    assert not effective_warehouses(user).filter(pk=warehouse.pk).exists()


@pytest.mark.django_db
def test_membership_limits_legal_entity_selector_without_inventing_business_unit_scope():
    user = User.objects.create_user("member@example.com", "strong-test-password")
    allowed = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    LegalEntity.objects.create(code="OTHER", name="PT OTHER")
    OrganizationMembership.objects.create(user=user, legal_entity=allowed)

    assert list(accessible_legal_entities(user)) == [allowed]


@pytest.mark.django_db
def test_department_and_cost_center_references_are_protected():
    entity = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    department = create_department(legal_entity=entity, code="OPS", name="Operations")
    create_cost_center(
        legal_entity=entity,
        department=department,
        code="OPS-GEN",
        name="Operations General",
    )

    with pytest.raises(ProtectedError):
        department.delete()


@pytest.mark.django_db
def test_department_hierarchy_rejects_indirect_cycle():
    entity = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    parent = create_department(legal_entity=entity, code="PARENT", name="Parent")
    child = create_department(
        legal_entity=entity,
        parent=parent,
        code="CHILD",
        name="Child",
    )

    with pytest.raises(ValidationError, match="cannot contain a cycle"):
        update_department(parent, parent=child, reason="Invalid reorganization")
