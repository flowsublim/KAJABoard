from datetime import date

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.purchasing.models import WorkOrderType
from apps.purchasing.services import (
    add_work_order_output,
    approve_work_order,
    create_draft_work_order,
    submit_work_order,
)

from .test_work_orders import _foundation


@pytest.mark.django_db
def test_vendor_analytics_scope_and_document_print_modal_routes(client):
    entity, user, item, _ = _foundation("P4CU")
    vendor = BusinessPartner.objects.create(legal_entity=entity, code="P4CV", display_name="Vendor")
    PartnerRole.objects.create(
        partner=vendor, role_type=PartnerRoleType.SUBCONTRACTOR, effective_from=date(2026, 1, 1)
    )
    work_order = create_draft_work_order(
        legal_entity=entity,
        document_date=date(2026, 8, 27),
        work_order_type=WorkOrderType.SUBCONTRACT,
        vendor=vendor,
    )
    add_work_order_output(work_order, item=item, target_quantity=1)
    submit_work_order(work_order)
    approve_work_order(work_order)
    client.force_login(user)
    analytics = reverse("purchasing_operations:vendor-analytics")
    assert client.get(analytics).status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="view_purchaseorder"))
    summary = client.get(analytics)
    assert summary.status_code == 200
    detail_url = reverse("purchasing_operations:vendor-analytics-detail", args=[vendor.pk])
    assert detail_url.encode() in summary.content
    assert client.get(detail_url).status_code == 200
    other = BusinessPartner.objects.create(legal_entity=entity, code="P4CO", display_name="Other")
    assert str(other.pk).encode() not in client.get(detail_url).content


@pytest.mark.django_db
def test_purchase_print_routes_are_secure_and_modal_templates_have_no_new_tab(client):
    entity, user, _, _ = _foundation("P4CP")
    client.force_login(user)
    assert client.get(reverse("purchasing_operations:order-list")).status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="view_purchaseorder"))
    from pathlib import Path

    root = Path("templates/purchasing")
    for name in (
        "order_detail.html",
        "subcontract_detail.html",
        "order_print.html",
        "dispatch_print.html",
        "receipt_print.html",
    ):
        assert 'target="_blank"' not in (root / name).read_text(encoding="utf-8")
    assert b"data-modal" in (root / "order_detail.html").read_bytes()
    assert b"data-modal" in (root / "subcontract_detail.html").read_bytes()
