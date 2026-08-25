import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.staticfiles import finders
from django.template.loader import get_template
from django.urls import reverse

from apps.organizations.models import LegalEntity, OrganizationMembership

User = get_user_model()


@pytest.mark.django_db
def test_master_workspace_requires_authentication(client):
    response = client.get(reverse("organizations:workspace"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_superuser_can_render_responsive_master_workspace_and_lists(client):
    user = User.objects.create_superuser("admin@example.com", "password")
    client.force_login(user)

    workspace = client.get(reverse("organizations:workspace"))
    partners = client.get(reverse("partners:list"))
    items = client.get(reverse("catalog:list", args=("items",)))

    assert workspace.status_code == 200
    assert b"Master Data Workspace" in workspace.content
    assert b"Phase 2A" in workspace.content
    assert partners.status_code == 200
    assert items.status_code == 200


@pytest.mark.django_db
def test_organization_list_is_limited_by_accepted_membership_scope(client):
    user = User.objects.create_user("member@example.com", "password")
    allowed = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    LegalEntity.objects.create(code="OTHER", name="PT OTHER")
    OrganizationMembership.objects.create(user=user, legal_entity=allowed)
    user.user_permissions.add(Permission.objects.get(codename="view_legalentity"))
    client.force_login(user)

    response = client.get(
        reverse("organizations:master-list", args=("legal-entities",)),
        {"inactive": "1"},
    )

    assert response.status_code == 200
    assert b"PT KAJA" in response.content
    assert b"PT OTHER" not in response.content


@pytest.mark.django_db
def test_view_permission_does_not_authorize_master_mutation(client):
    user = User.objects.create_user("viewer@example.com", "password")
    entity = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(Permission.objects.get(codename="view_legalentity"))
    client.force_login(user)

    response = client.get(reverse("organizations:master-edit", args=("legal-entities", entity.pk)))

    assert response.status_code == 403


@pytest.mark.django_db
def test_navigation_hides_master_domains_without_view_permission(client):
    user = User.objects.create_user("limited@example.com", "password")
    client.force_login(user)

    response = client.get(reverse("organizations:workspace"))

    assert response.status_code == 200
    assert b"Business Partners" not in response.content
    assert b"Items &amp; SKU" not in response.content


def test_login_page_uses_custom_application_shell(client):
    response = client.get(reverse("login"))

    assert response.status_code == 200
    assert b"PT KAJA VASTRALOKA KREASINDO" in response.content


def test_all_phase_2a_templates_compile_and_local_stylesheet_is_discoverable():
    template_root = settings.BASE_DIR / "templates"
    for template_path in template_root.rglob("*.html"):
        get_template(template_path.relative_to(template_root).as_posix())

    assert finders.find("css/kajaboard.css") is not None
