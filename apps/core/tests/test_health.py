from unittest.mock import patch

import pytest
from django.db import DatabaseError
from django.urls import reverse


def test_liveness_endpoint_does_not_require_database(client):
    with patch("apps.core.views.connection.cursor") as cursor:
        response = client.get(reverse("health:liveness"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    cursor.assert_not_called()


@pytest.mark.django_db
def test_readiness_endpoint_confirms_database_connection(client):
    response = client.get(reverse("health:readiness"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_readiness_endpoint_fails_closed_on_database_error(client):
    with patch("apps.core.views.connection.cursor", side_effect=DatabaseError):
        response = client.get(reverse("health:readiness"))

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
