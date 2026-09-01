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
    assert b"<summary>Purchasing</summary>" not in response.content
    assert client.get(reverse("purchasing_operations:order-list")).status_code == 403


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


@pytest.mark.django_db
def test_purchasing_operational_and_configuration_namespaces_coexist(client):
    assert reverse("purchasing_operations:order-list") == "/purchasing/"
    assert reverse("purchasing_operations:work-order-list") == "/purchasing/spk/"
    assert reverse("purchasing_operations:dispatch-list") == "/purchasing/kirim-bahan/"
    assert reverse("purchasing_operations:receipt-list") == "/purchasing/terima-maklun/"
    assert reverse("purchasing_operations:vendor-analytics") == "/purchasing/analitik-vendor/"
    assert reverse("purchasing:category-list") == "/settings/purchasing/purchase-categories/"


@pytest.mark.django_db
def test_home_renders_purchasing_sidebar_for_operational_permissions(client):
    entity = LegalEntity.objects.create(code="HOME-PO", name="Home Purchasing")
    user = User.objects.create_user("home-purchase@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(
        Permission.objects.get(codename="view_purchaseorder"),
        Permission.objects.get(codename="view_workorder"),
        Permission.objects.get(codename="view_subcontractmaterialdispatch"),
        Permission.objects.get(codename="view_subcontractreceipt"),
    )
    client.force_login(user)
    response = client.get(reverse("home:home"))
    assert response.status_code == 200
    for label in (b"Pembelian", b"SPK", b"Kirim Bahan", b"Terima Maklun"):
        assert label in response.content


@pytest.mark.django_db
def test_purchasing_operational_pages_render_with_registered_namespace(client):
    entity = LegalEntity.objects.create(code="PURCH-SMOKE", name="Purchasing Smoke")
    user = User.objects.create_user("purchasing-smoke@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(
        Permission.objects.get(codename="view_purchaseorder"),
        Permission.objects.get(codename="view_workorder"),
        Permission.objects.get(codename="view_subcontractmaterialdispatch"),
        Permission.objects.get(codename="view_subcontractreceipt"),
    )
    client.force_login(user)

    for route_name in (
        "purchasing_operations:order-list",
        "purchasing_operations:work-order-list",
        "purchasing_operations:dispatch-list",
        "purchasing_operations:receipt-list",
        "purchasing_operations:vendor-analytics",
    ):
        response = client.get(reverse(route_name))
        assert response.status_code == 200, route_name


@pytest.mark.django_db
def test_sidebar_superuser_operational_ordering(client):
    user = User.objects.create_superuser("sidebar-order@example.com", "password")
    client.force_login(user)
    content = client.get(reverse("home:home")).content
    positions = [
        content.index(label)
        for label in (
            b"Operasional",
            b"<summary>Warehouse</summary>",
            b"<summary>Omnichannel</summary>",
            b"<summary>POS &amp; Analitik</summary>",
            b"Master &amp; Konfigurasi",
        )
    ]
    assert positions == sorted(positions)
    assert content.index(b"<summary>Production Configuration</summary>") > positions[-1]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("codename", "visible"),
    [
        ("view_stockmovement", b"<summary>Warehouse</summary>"),
        ("view_omniorder", b"<summary>Omnichannel</summary>"),
        ("view_possale", b"<summary>POS &amp; Analitik</summary>"),
    ],
)
def test_sidebar_operational_only_permissions_show_operational_label(client, codename, visible):
    entity = LegalEntity.objects.create(code=f"NAV-{codename}", name=codename)
    user = User.objects.create_user(f"{codename}@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(Permission.objects.get(codename=codename))
    client.force_login(user)
    content = client.get(reverse("home:home")).content
    assert b"Operasional" in content
    assert visible in content


@pytest.mark.django_db
def test_sidebar_production_tariff_is_configuration_only(client):
    user = User.objects.create_user("tariff-nav@example.com", "password")
    user.user_permissions.add(Permission.objects.get(codename="view_productiontariff"))
    client.force_login(user)
    content = client.get(reverse("home:home")).content
    assert b"Master &amp; Konfigurasi" in content
    assert b"<summary>Production Configuration</summary>" in content
    assert b"<summary>Produksi</summary>" not in content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("codename", "label"),
    [
        ("view_productiondirectextracost", b"Biaya Langsung"),
        ("view_productioncostsnapshot", b"HPP / COGM"),
    ],
)
def test_sidebar_production_cost_permissions_are_operational(client, codename, label):
    user = User.objects.create_user(f"{codename}@example.com", "password")
    user.user_permissions.add(Permission.objects.get(codename=codename))
    client.force_login(user)
    content = client.get(reverse("home:home")).content
    assert b"Operasional" in content
    assert b"<summary>Produksi</summary>" in content
    assert label in content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("route", "permission", "active", "inactive"),
    [
        (
            "production:tariff-list",
            "view_productiontariff",
            b"Production Configuration",
            b"<summary>Produksi</summary>",
        ),
        (
            "production:extra-cost-list",
            "view_productiondirectextracost",
            b"<summary>Produksi</summary>",
            b"Production Configuration",
        ),
        (
            "omnichannel:pos-sale-list",
            "view_possale",
            b"POS &amp; Analitik",
            b"<summary>Omnichannel</summary>",
        ),
        (
            "omnichannel:order-list",
            "view_omniorder",
            b"<summary>Omnichannel</summary>",
            b"POS &amp; Analitik",
        ),
    ],
)
def test_sidebar_route_groups_are_mutually_active(client, route, permission, active, inactive):
    entity = LegalEntity.objects.create(code=f"ROUTE-{permission}", name=permission)
    user = User.objects.create_user(f"{permission}@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(Permission.objects.get(codename=permission))
    client.force_login(user)
    response = client.get(reverse(route))
    assert response.status_code == 200
    content = response.content
    assert active in content
    assert inactive not in content
