from django.db import models

from .exceptions import PostedRecordImmutableError


class PostingState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class CorrectionType(models.TextChoices):
    REVERSAL = "REVERSAL", "Reversal"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"
    REVALUATION = "REVALUATION", "Revaluation"


def ensure_record_is_mutable(state: str) -> None:
    """Guard explicit service-layer edit paths; only drafts may be mutated in place."""

    if state != PostingState.DRAFT:
        raise PostedRecordImmutableError(
            "Posted history is immutable; use a traceable correction document."
        )
