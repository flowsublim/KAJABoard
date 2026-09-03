import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_finance_sidebar_shows_phase_8_routes_for_superuser():
    user = get_user_model().objects.create_superuser("nav@example.com", "password")
    client = Client()
    client.force_login(user)
    response = client.get(reverse("finance_operations:fixed-asset-list"))
    assert response.status_code == 200
    content = response.content.decode()
    for label in (
        "Fixed Assets",
        "Depreciation",
        "Wage Payables",
        "Accounting Periods",
        "Bank Reconciliation",
    ):
        assert label in content
    assert "Asset Classes" in content
    assert 'details class="nav-module is-active"' in content


def test_configuration_route_opens_only_configuration_parent():
    user = get_user_model().objects.create_superuser("config@example.com", "password")
    client = Client()
    client.force_login(user)
    response = client.get(reverse("finance:asset-class-list"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Asset Classes" in content
    assert content.count('details class="nav-module is-active"') == 1
