import pytest
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction

User = get_user_model()


@pytest.mark.django_db
def test_create_user_normalizes_email_and_hashes_password():
    user = User.objects.create_user("  OWNER@Example.COM ", "strong-test-password")

    assert user.email == "owner@example.com"
    assert user.check_password("strong-test-password")
    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False


@pytest.mark.django_db
def test_create_user_requires_email():
    with pytest.raises(ValueError, match="email address is required"):
        User.objects.create_user("", "strong-test-password")


@pytest.mark.django_db
def test_create_superuser_sets_required_flags():
    user = User.objects.create_superuser("admin@example.com", "strong-test-password")

    assert user.is_active is True
    assert user.is_staff is True
    assert user.is_superuser is True


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["is_staff", "is_superuser"])
def test_create_superuser_rejects_disabled_privilege_flags(field):
    with pytest.raises(ValueError, match="superuser must have"):
        User.objects.create_superuser(
            "admin@example.com",
            "strong-test-password",
            **{field: False},
        )


@pytest.mark.django_db
def test_email_uniqueness_is_case_insensitive_at_database_level():
    User.objects.create_user("owner@example.com", "strong-test-password")

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(email="OWNER@example.com")


@pytest.mark.django_db
def test_authentication_uses_email_case_insensitively():
    user = User.objects.create_user("owner@example.com", "strong-test-password")

    authenticated = authenticate(email="OWNER@EXAMPLE.COM", password="strong-test-password")

    assert authenticated == user


@pytest.mark.django_db
def test_inactive_user_cannot_authenticate():
    User.objects.create_user(
        "inactive@example.com",
        "strong-test-password",
        is_active=False,
    )

    assert (
        authenticate(
            email="inactive@example.com",
            password="strong-test-password",
        )
        is None
    )
