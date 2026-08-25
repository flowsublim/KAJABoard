import pytest

from apps.core.exceptions import AuditEventImmutableError
from apps.core.models import AuditEvent
from apps.core.services.audit import record_audit_event


@pytest.mark.django_db
def test_record_audit_event_captures_traceability_context():
    event = record_audit_event(
        action="foundation.tested",
        target_type="system",
        target_id="phase-1",
        source="pytest",
        reference="FOUNDATION-1",
        reason="Regression coverage",
        idempotency_key="test:phase-1",
        before_state={"status": "DRAFT"},
        after_state={"status": "POSTED"},
        changed_fields=["status"],
        metadata={"suite": "core"},
    )

    assert event.pk is not None
    assert event.changed_fields == ["status"]
    assert event.metadata == {"suite": "core"}


@pytest.mark.django_db
def test_audit_event_instance_cannot_be_updated_or_deleted():
    event = record_audit_event(action="created", target_type="test", target_id="1")
    event.action = "changed"

    with pytest.raises(AuditEventImmutableError, match="append-only"):
        event.save()
    with pytest.raises(AuditEventImmutableError, match="append-only"):
        event.delete()


@pytest.mark.django_db
def test_audit_event_queryset_cannot_be_updated_or_deleted():
    event = record_audit_event(action="created", target_type="test", target_id="1")

    with pytest.raises(AuditEventImmutableError, match="append-only"):
        AuditEvent.objects.filter(pk=event.pk).update(action="changed")
    with pytest.raises(AuditEventImmutableError, match="append-only"):
        AuditEvent.objects.filter(pk=event.pk).delete()
