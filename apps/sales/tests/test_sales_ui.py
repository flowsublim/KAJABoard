import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.organizations.models import LegalEntity, OrganizationMembership

User = get_user_model()


@pytest.mark.django_db
def test_sales_order_routes_require_model_permission_and_render_for_scoped_user(client):
    entity = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    user = User.objects.create_user("sales-ui@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    client.force_login(user)
    url = reverse("sales:order-list")

    assert client.get(url).status_code == 403

    user.user_permissions.add(Permission.objects.get(codename="view_salesorder"))
    response = client.get(url)

    assert response.status_code == 200
    assert b"Sales Orders" in response.content
