import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.organizations.models import LegalEntity, OrganizationMembership

User = get_user_model()


@pytest.mark.django_db
def test_root_requires_login_and_successful_login_lands_on_home(client):
    user = User.objects.create_user("home-user@example.com", "password")
    home_url = reverse("home:home")

    response = client.get(home_url)
    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next=/"

    response = client.post(
        reverse("login"),
        {"username": user.email, "password": "password"},
    )
    assert response.status_code == 302
    assert response.url == home_url

    response = client.get(home_url)
    assert response.status_code == 200
    assert b"Beranda" in response.content


@pytest.mark.django_db
def test_superuser_home_shows_all_current_module_shortcuts(client):
    user = User.objects.create_superuser("shell-admin@example.com", "password")
    client.force_login(user)

    response = client.get(reverse("home:home"))

    assert response.status_code == 200
    for label in (
        b"Sales",
        b"Organisasi",
        b"Partners",
        b"Catalog",
        b"Channels &amp; Stores",
        b"Purchasing Configuration",
        b"Finance Configuration",
        b"Tax Configuration",
        b"Data Exchange",
    ):
        assert label in response.content


@pytest.mark.django_db
def test_restricted_home_and_sidebar_only_show_permitted_modules(client):
    entity = LegalEntity.objects.create(code="HOME", name="Home Entity")
    user = User.objects.create_user("restricted-home@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(Permission.objects.get(codename="view_businesspartner"))
    client.force_login(user)

    response = client.get(reverse("home:home"))

    assert response.status_code == 200
    assert b"Partners" in response.content
    assert b"Sales" not in response.content
    assert b"Finance Configuration" not in response.content
    assert b"Surat Jalan" not in response.content
    assert client.get(reverse("sales:order-list")).status_code == 403
    assert client.get(reverse("partners:list")).status_code == 200


@pytest.mark.django_db
def test_master_workspace_remains_available_at_settings_for_authorized_user(client):
    entity = LegalEntity.objects.create(code="SETTINGS", name="Settings Entity")
    user = User.objects.create_user("workspace-user@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(Permission.objects.get(codename="view_legalentity"))
    client.force_login(user)

    response = client.get(reverse("organizations:workspace"))

    assert response.status_code == 200
    assert response.request["PATH_INFO"] == "/settings/"
    assert b"Master Data Workspace" in response.content
