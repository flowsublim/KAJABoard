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
    assert b"Sales Order</a>" not in response.content
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


@pytest.mark.django_db
def test_sidebar_sales_children_are_permission_aware_and_never_offer_payment(client):
    entity = LegalEntity.objects.create(code="NAV-SALES", name="Sales Navigation")
    user = User.objects.create_user("sales-nav@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(Permission.objects.get(codename="view_salesorder"))
    client.force_login(user)

    response = client.get(reverse("home:home"))

    assert b"Sales" in response.content
    assert b"Sales Order" in response.content
    assert b'href="/sales/deliveries/"' not in response.content
    assert b'href="/sales/invoices/"' not in response.content
    assert b"Payment" not in response.content
    assert client.get(reverse("sales:delivery-list")).status_code == 403


@pytest.mark.django_db
def test_sidebar_hides_sales_parent_without_visible_sales_children(client):
    user = User.objects.create_user("no-sales-nav@example.com", "password")
    client.force_login(user)

    response = client.get(reverse("home:home"))

    assert b"<summary>Sales</summary>" not in response.content


@pytest.mark.django_db
def test_sidebar_uses_invoice_label_and_opens_sales_for_active_route(client):
    entity = LegalEntity.objects.create(code="NAV-ACTIVE", name="Active Navigation")
    user = User.objects.create_user("active-nav@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(
        Permission.objects.get(codename="view_salesinvoice"),
        Permission.objects.get(codename="view_salesorder"),
    )
    client.force_login(user)

    response = client.get(reverse("sales:invoice-list"))

    assert response.status_code == 200
    assert b">Invoice<" in response.content
    assert b'<a class="is-active" href="/sales/invoices/">Invoice</a>' in response.content
    assert b'nav-module is-active" open' in response.content


@pytest.mark.django_db
def test_superuser_sidebar_shows_current_modular_sections(client):
    user = User.objects.create_superuser("sidebar-admin@example.com", "password")
    client.force_login(user)

    response = client.get(reverse("home:home"))

    for label in (
        b"<summary>Sales</summary>",
        b"<summary>Projects &amp; Contracts</summary>",
        b"<summary>Master Data</summary>",
        b"<summary>Finance Configuration</summary>",
        b"<summary>System Configuration</summary>",
    ):
        assert label in response.content
