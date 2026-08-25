from apps.core.models import AuditEvent


def record_audit_event(
    *,
    action: str,
    target_type: str,
    target_id: str,
    actor=None,
    source: str = "",
    correlation_id=None,
    reference: str = "",
    reason: str = "",
    approval_reference: str = "",
    idempotency_key: str = "",
    before_state=None,
    after_state=None,
    changed_fields=None,
    metadata=None,
) -> AuditEvent:
    """Append an audit event through one explicit application entry point."""

    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        source=source,
        correlation_id=correlation_id,
        reference=reference,
        reason=reason,
        approval_reference=approval_reference,
        idempotency_key=idempotency_key,
        before_state=before_state,
        after_state=after_state,
        changed_fields=changed_fields or [],
        metadata=metadata or {},
    )
