from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.organizations.models import LegalEntity, OrganizationMembership
from apps.partners.services import create_business_partner
from apps.tax.models import TaxRegistration
from apps.tax.selectors import effective_tax_registrations, tax_registrations
from apps.tax.services import create_tax_registration, deactivate_tax_registration

User = get_user_model()


@pytest.fixture
def entity():
    return LegalEntity.objects.create(
        code="KAJA",
        name="PT KAJA",
        npwp="01.234.567.8-999.000",
        nitku="NITKU-KAJA",
    )


@pytest.fixture
def user(entity):
    user = User.objects.create_user("member@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    return user


@pytest.mark.django_db
def test_tax_registration_uses_subject_npwp_without_duplicate_source(entity):
    registration = create_tax_registration(
        legal_entity=entity,
        registration_status="registered",
        tax_classification_key="PKP",
        effective_from=date(2026, 1, 1),
    )

    assert registration.npwp == entity.npwp
    assert registration.nitku == entity.nitku
    assert "npwp" not in {field.name for field in TaxRegistration._meta.fields}
    assert "nitku" not in {field.name for field in TaxRegistration._meta.fields}


@pytest.mark.django_db
def test_tax_registration_requires_exactly_one_subject(entity):
    partner = create_business_partner(
        legal_entity=entity,
        code="BP-001",
        display_name="Vendor",
    )

    with pytest.raises(ValidationError, match="Exactly one"):
        create_tax_registration(
            legal_entity=entity,
            business_partner=partner,
            registration_status="REGISTERED",
        )


@pytest.mark.django_db
def test_tax_registration_overlap_and_historical_lookup(entity, user):
    yesterday = timezone.localdate() - timedelta(days=1)
    registration = create_tax_registration(
        legal_entity=entity,
        registration_status="REGISTERED",
        tax_classification_key="PKP",
        effective_from=yesterday,
    )

    with pytest.raises(ValidationError, match="cannot overlap"):
        create_tax_registration(
            legal_entity=entity,
            registration_status="UPDATED",
            effective_from=yesterday,
        )

    deactivate_tax_registration(registration, reason="Closed")

    assert effective_tax_registrations(user, business_date=yesterday).get() == registration
    assert not effective_tax_registrations(user).filter(pk=registration.pk).exists()
    assert AuditEvent.objects.filter(
        target_id=str(registration.pk),
        action="tax.taxregistration.deactivated",
    ).exists()


@pytest.mark.django_db
def test_tax_selector_enforces_membership_scope(entity, user):
    allowed = create_tax_registration(
        legal_entity=entity,
        registration_status="REGISTERED",
        effective_from=date(2026, 1, 1),
    )
    other_entity = LegalEntity.objects.create(code="OTHER", name="Other")
    create_tax_registration(
        legal_entity=other_entity,
        registration_status="REGISTERED",
        effective_from=date(2026, 1, 1),
    )

    assert list(tax_registrations(user)) == [allowed]
