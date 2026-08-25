import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from apps.organizations.models import LegalEntity, OrganizationMembership

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
