import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

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


class EffectivePeriodModel(models.Model):
    """Opt-in validity interval for master data selected as of a business date."""

    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="%(app_label)s_%(class)s_effective_period_valid",
            )
        ]

    def clean(self):
        super().clean()
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Effective to cannot be before effective from."})

    def is_effective_on(self, business_date) -> bool:
        return self.effective_from <= business_date and (
            self.effective_to is None or self.effective_to >= business_date
        )


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


class SequenceResetMode(models.TextChoices):
    NEVER = "NEVER", "Never"
    YEARLY = "YEARLY", "Yearly"
    MONTHLY = "MONTHLY", "Monthly"
    DAILY = "DAILY", "Daily"


class DocumentSequence(UUIDPrimaryKeyModel, TimeStampedModel, EffectivePeriodModel):
    """Effective document-number configuration owned by Core."""

    legal_entity = models.ForeignKey(
        "organizations.LegalEntity",
        on_delete=models.PROTECT,
        related_name="document_sequences",
    )
    document_type = models.CharField(max_length=64)
    name = models.CharField(max_length=150)
    prefix = models.CharField(max_length=32, blank=True)
    format_template = models.CharField(
        max_length=120,
        default="{prefix}{yyyymmdd}-{seq}",
        help_text=(
            "Allowed tokens: {prefix}, {yyyy}, {yy}, {mm}, {dd}, "
            "{yyyymmdd}, {yymmdd}, and exactly one {seq}."
        ),
    )
    padding = models.PositiveSmallIntegerField(default=4)
    starting_number = models.PositiveBigIntegerField(default=1)
    reset_mode = models.CharField(
        max_length=10,
        choices=SequenceResetMode.choices,
        default=SequenceResetMode.DAILY,
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("legal_entity__code", "document_type", "-effective_from")
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "document_type", "effective_from"),
                name="core_sequence_entity_type_start_unique",
            ),
            models.CheckConstraint(
                condition=Q(padding__gte=1) & Q(padding__lte=12),
                name="core_sequence_padding_valid",
            ),
            models.CheckConstraint(
                condition=Q(starting_number__gte=1),
                name="core_sequence_starting_number_positive",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="core_documentsequence_effective_period_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "document_type", "is_active"),
                name="core_sequence_lookup_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.legal_entity.code}/{self.document_type}"


class DocumentSequenceState(UUIDPrimaryKeyModel, TimeStampedModel):
    """Locked counter for one effective configuration and reset period."""

    sequence = models.ForeignKey(
        DocumentSequence,
        on_delete=models.PROTECT,
        related_name="states",
    )
    period_key = models.CharField(max_length=16)
    last_value = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("sequence", "period_key"),
                name="core_sequence_state_period_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sequence} [{self.period_key}] = {self.last_value}"


class DocumentNumberAllocation(UUIDPrimaryKeyModel):
    """Final allocated number; this is not a business transaction document."""

    sequence = models.ForeignKey(
        DocumentSequence,
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    legal_entity = models.ForeignKey(
        "organizations.LegalEntity",
        on_delete=models.PROTECT,
        related_name="document_number_allocations",
    )
    document_type = models.CharField(max_length=64)
    business_date = models.DateField()
    period_key = models.CharField(max_length=16)
    sequence_value = models.PositiveBigIntegerField()
    number = models.CharField(max_length=120)
    request_key = models.CharField(max_length=120, blank=True)
    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="document_number_allocations",
    )
    allocated_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-allocated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "number"),
                name="core_document_number_entity_unique",
            ),
            models.UniqueConstraint(
                fields=("sequence", "period_key", "sequence_value"),
                name="core_document_number_value_unique",
            ),
            models.UniqueConstraint(
                fields=("legal_entity", "document_type", "request_key"),
                condition=~Q(request_key=""),
                name="core_document_number_request_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "document_type", "business_date"),
                name="core_docnum_lookup_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.number
