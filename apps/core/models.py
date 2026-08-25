import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from .exceptions import AuditEventImmutableError


class UUIDPrimaryKeyModel(models.Model):
    """Opt-in stable identity convention for durable KAJABoard records."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """Opt-in creation/update timestamps; not a universal business base model."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AuditEventImmutableError("Audit events are append-only and cannot be updated.")

    def delete(self):
        raise AuditEventImmutableError("Audit events are append-only and cannot be deleted.")


class AuditEvent(UUIDPrimaryKeyModel):
    """Append-oriented evidence of a security- or business-relevant action."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    action = models.CharField(max_length=100, db_index=True)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=255)
    source = models.CharField(max_length=100, blank=True)
    correlation_id = models.UUIDField(null=True, blank=True, db_index=True)
    reference = models.CharField(max_length=255, blank=True)
    reason = models.TextField(blank=True)
    approval_reference = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=255, blank=True, db_index=True)
    before_state = models.JSONField(null=True, blank=True)
    after_state = models.JSONField(null=True, blank=True)
    changed_fields = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("target_type", "target_id"), name="core_audit_target_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action}: {self.target_type}/{self.target_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditEventImmutableError("Audit events are append-only and cannot be updated.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditEventImmutableError("Audit events are append-only and cannot be deleted.")


class IdempotencyStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class IdempotencyRecord(UUIDPrimaryKeyModel):
    """Database-enforced claim/result record for retry-safe operations."""

    namespace = models.CharField(max_length=100)
    key = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="idempotency_records",
    )
    status = models.CharField(
        max_length=20,
        choices=IdempotencyStatus.choices,
        default=IdempotencyStatus.IN_PROGRESS,
    )
    result_reference = models.CharField(max_length=255, blank=True)
    response = models.JSONField(null=True, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("namespace", "key"),
                name="core_idempotency_namespace_key_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=IdempotencyStatus.IN_PROGRESS, finished_at__isnull=True)
                    | Q(
                        status__in=(IdempotencyStatus.COMPLETED, IdempotencyStatus.FAILED),
                        finished_at__isnull=False,
                    )
                ),
                name="core_idempotency_finish_state_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("namespace", "status"), name="core_idem_scope_status_idx"),
        ]
        ordering = ("-started_at",)

    def __str__(self) -> str:
        return f"{self.namespace}:{self.key} ({self.status})"
