from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.organizations.models import LegalEntity, OrganizationMembership

User = get_user_model()
ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.django_db
def test_application_shell_exposes_one_global_modal_and_toast_container(client):
    user = User.objects.create_user("modal@example.com", "password")
    client.force_login(user)

    response = client.get(reverse("home:home"))

    assert b'id="kb-modal"' in response.content
    assert b'id="toast-container"' in response.content
    assert b"alert alert-" not in response.content
    assert b"static/js/kajaboard.js" in response.content


@pytest.mark.django_db
def test_create_modal_trigger_and_permission_boundary_remain_separate(client):
    entity = LegalEntity.objects.create(code="MODAL", name="Modal Entity")
    user = User.objects.create_user("modal-sales@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(Permission.objects.get(codename="view_salesorder"))
    client.force_login(user)

    response = client.get(reverse("sales:order-list"))

    assert b'data-modal href="/sales/new/"' not in response.content
    assert client.get(reverse("sales:order-create")).status_code == 403


def test_global_interaction_script_and_print_contract_are_shared():
    script = (ROOT / "static" / "js" / "kajaboard.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "css" / "kajaboard.css").read_text(encoding="utf-8")
    delivery = (ROOT / "templates" / "sales" / "delivery_detail.html").read_text(encoding="utf-8")
    invoice = (ROOT / "templates" / "sales" / "invoice_detail.html").read_text(encoding="utf-8")

    assert "data-modal" in script and "window.print()" in script
    assert "@media print" in css and "#kb-print-root" in css
    assert 'target="_blank"' not in delivery
    assert 'target="_blank"' not in invoice
    assert "data-modal" in delivery and "data-modal" in invoice
