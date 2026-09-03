# ruff: noqa: E501
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.finance.models import AccountingPeriod, AccountingPeriodState
from apps.organizations.models import LegalEntity, OrganizationMembership

pytestmark = pytest.mark.django_db


def test_accounting_period_detail_get_is_safe_and_close_requires_post():
    entity = LegalEntity.objects.create(code="8C3A1", name="UI Test")
    user = get_user_model().objects.create_superuser("ui@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    period = AccountingPeriod.objects.create(
        legal_entity=entity,
        fiscal_year=2026,
        period_number=9,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
    )
    client = Client()
    client.force_login(user)
    detail = reverse("finance_operations:accounting-period-detail", args=[period.pk])
    assert client.get(detail).status_code == 200
    period.refresh_from_db()
    assert period.state == AccountingPeriodState.OPEN
    assert (
        client.post(
            reverse("finance_operations:accounting-period-close", args=[period.pk]),
            {"reason": "month close"},
        ).status_code
        == 302
    )
    period.refresh_from_db()
    assert period.state == AccountingPeriodState.CLOSED
    assert (
        "reopen"
        not in str(reverse("finance_operations:accounting-period-detail", args=[period.pk])).lower()
    )
