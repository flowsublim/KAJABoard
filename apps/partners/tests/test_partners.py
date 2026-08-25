from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.organizations.models import LegalEntity
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.partners.selectors import effective_business_partners, effective_partner_roles
from apps.partners.services import (
    assign_partner_role,
    create_business_partner,
    deactivate_business_partner,
    remove_partner_role,
    update_business_partner,
    update_business_partner_with_roles,
)

User = get_user_model()


@pytest.fixture
def entity():
    return LegalEntity.objects.create(code="KAJA", name="PT KAJA")


@pytest.mark.django_db
def test_one_partner_identity_supports_customer_and_vendor_roles(entity):
    partner = create_business_partner(
        legal_entity=entity,
        code="BP-001",
        display_name="Partner Satu",
        role_types=(PartnerRoleType.CUSTOMER, PartnerRoleType.VENDOR),
    )

    assert BusinessPartner.objects.count() == 1
    assert set(partner.roles.values_list("role_type", flat=True)) == {
        PartnerRoleType.CUSTOMER,
        PartnerRoleType.VENDOR,
    }


@pytest.mark.django_db
def test_partner_code_is_case_insensitively_unique(entity):
    BusinessPartner.objects.create(legal_entity=entity, code="BP-001", display_name="First")

    with pytest.raises(IntegrityError), transaction.atomic():
        BusinessPartner.objects.create(legal_entity=entity, code="bp-001", display_name="Duplicate")


@pytest.mark.django_db
def test_credit_limit_cannot_be_negative(entity):
    with pytest.raises(ValidationError):
        create_business_partner(
            legal_entity=entity,
            code="BP-001",
            display_name="Partner",
            credit_limit=-1,
        )


@pytest.mark.django_db
def test_role_removal_is_effective_dated_and_audited(entity):
    actor = User.objects.create_user("owner@example.com", "password")
    partner = create_business_partner(
        legal_entity=entity,
        code="BP-001",
        display_name="Partner",
    )
    role = assign_partner_role(
        partner,
        role_type=PartnerRoleType.VENDOR,
        actor=actor,
        reason="Approved vendor role",
    )

    removed = remove_partner_role(role, actor=actor, reason="Vendor relationship ended")

    assert removed.is_active is False
    assert removed.effective_to is not None
    assert PartnerRole.objects.filter(pk=role.pk).exists()
    event = AuditEvent.objects.get(target_id=str(role.pk), action="partners.partnerrole.removed")
    assert event.reason == "Vendor relationship ended"


@pytest.mark.django_db
def test_removed_role_remains_selectable_as_of_prior_business_date(entity):
    user = User.objects.create_user("member@example.com", "password")
    yesterday = timezone.localdate() - timedelta(days=1)
    partner = create_business_partner(
        legal_entity=entity,
        code="BP-001",
        display_name="Partner",
        effective_from=yesterday,
    )
    role = assign_partner_role(
        partner,
        role_type=PartnerRoleType.VENDOR,
        effective_from=yesterday,
        reason="Approved vendor role",
    )

    remove_partner_role(role, reason="Vendor relationship ended")

    assert effective_partner_roles(partner, business_date=yesterday).get() == role
    assert not effective_partner_roles(partner).filter(pk=role.pk).exists()
    user.organization_memberships.create(legal_entity=entity)
    assert (
        effective_business_partners(
            user,
            business_date=yesterday,
            role_type=PartnerRoleType.VENDOR,
        ).get()
        == partner
    )


@pytest.mark.django_db
def test_inactive_partner_cannot_receive_role(entity):
    partner = create_business_partner(
        legal_entity=entity,
        code="BP-001",
        display_name="Partner",
    )
    partner = deactivate_business_partner(partner, reason="Dormant")

    with pytest.raises(ValidationError, match="inactive"):
        assign_partner_role(
            partner,
            role_type=PartnerRoleType.CUSTOMER,
            reason="Customer onboarding",
        )


@pytest.mark.django_db
def test_deactivating_partner_ends_active_roles_without_deleting_history(entity):
    partner = create_business_partner(
        legal_entity=entity,
        code="BP-001",
        display_name="Partner",
        role_types=(PartnerRoleType.CUSTOMER, PartnerRoleType.VENDOR),
    )

    deactivated = deactivate_business_partner(partner, reason="Business closed")

    assert deactivated.is_active is False
    assert deactivated.roles.filter(is_active=True).count() == 0
    assert deactivated.roles.count() == 2


@pytest.mark.django_db
def test_partner_update_audit_preserves_before_and_after_master_meaning(entity):
    partner = create_business_partner(
        legal_entity=entity,
        code="BP-001",
        display_name="Old Name",
        payment_terms_days=14,
    )

    update_business_partner(
        partner,
        display_name="New Name",
        payment_terms_days=30,
        reason="Terms updated",
    )

    event = AuditEvent.objects.get(
        target_id=str(partner.pk), action="partners.businesspartner.updated"
    )
    assert event.before_state["display_name"] == "Old Name"
    assert event.after_state["display_name"] == "New Name"
    assert set(event.changed_fields) >= {"display_name", "payment_terms_days"}


@pytest.mark.django_db
def test_partner_and_role_edit_is_one_atomic_service_command(entity):
    partner = create_business_partner(
        legal_entity=entity,
        code="BP-001",
        display_name="Partner",
        role_types=(PartnerRoleType.CUSTOMER, PartnerRoleType.VENDOR),
    )

    updated = update_business_partner_with_roles(
        partner,
        role_types=(PartnerRoleType.CUSTOMER, PartnerRoleType.OTHER),
        display_name="Partner Updated",
        reason="Commercial role review",
    )

    assert updated.display_name == "Partner Updated"
    assert set(updated.roles.filter(is_active=True).values_list("role_type", flat=True)) == {
        PartnerRoleType.CUSTOMER,
        PartnerRoleType.OTHER,
    }
    assert updated.roles.filter(role_type=PartnerRoleType.VENDOR, is_active=False).exists()
