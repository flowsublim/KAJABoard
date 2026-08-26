from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.organizations.models import LegalEntity


class ImportBatchStatus(models.TextChoices):
    UPLOADED = "UPLOADED", "Uploaded"
    VALIDATED_WITH_ERRORS = "VALIDATED_WITH_ERRORS", "Validated with errors"
    READY_TO_IMPORT = "READY_TO_IMPORT", "Ready to import"
    IMPORTED = "IMPORTED", "Imported"
    PARTIAL_FAILED = "PARTIAL_FAILED", "Partial failed"


class ImportRowStatus(models.TextChoices):
    VALID = "VALID", "Valid"
    WARNING = "WARNING", "Warning"
    ERROR = "ERROR", "Error"
    IMPORTED = "IMPORTED", "Imported"
    SKIPPED = "SKIPPED", "Skipped"


class ImportBatch(UUIDPrimaryKeyModel, TimeStampedModel):
    """Reusable import metadata and preview state for non-transactional imports."""

    legal_entity = models.ForeignKey(
        LegalEntity,
        on_delete=models.PROTECT,
        related_name="import_batches",
    )
    import_type = models.CharField(max_length=50)
    template_version = models.CharField(max_length=20)
    source_filename = models.CharField(max_length=255)
    source_system = models.CharField(max_length=80, blank=True)
    checksum = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="import_batches",
    )
    status = models.CharField(
        max_length=30,
        choices=ImportBatchStatus.choices,
        default=ImportBatchStatus.UPLOADED,
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    replay_count = models.PositiveIntegerField(default=0)
    last_replayed_at = models.DateTimeField(null=True, blank=True)
    total_rows = models.PositiveIntegerField(default=0)
    success_rows = models.PositiveIntegerField(default=0)
    skipped_rows = models.PositiveIntegerField(default=0)
    warning_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("legal_entity", "import_type", "checksum"),
                name="data_import_entity_type_checksum_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=("legal_entity", "import_type", "status"),
                name="data_import_scope_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.import_type} {self.source_filename}"


class ImportRowResult(UUIDPrimaryKeyModel, TimeStampedModel):
    """Parsed import row plus validation/import result."""

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    raw_data = models.JSONField(default=dict)
    normalized_data = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=ImportRowStatus.choices)
    messages = models.JSONField(default=list, blank=True)
    target_reference = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("row_number",)
        constraints = [
            models.UniqueConstraint(
                fields=("batch", "row_number"),
                name="data_import_row_batch_number_unique",
            ),
        ]
        indexes = [
            models.Index(fields=("batch", "status"), name="data_import_row_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.batch_id} row {self.row_number}: {self.status}"
