from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import IdempotencyConflictError, IdempotencyStateError
from apps.core.models import IdempotencyRecord, IdempotencyStatus


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    record: IdempotencyRecord
    is_new: bool

    @property
    def is_replay(self) -> bool:
        return not self.is_new


def hash_request_payload(payload: object) -> str:
    """Produce a deterministic SHA-256 for bytes, text, or JSON-compatible data."""

    if isinstance(payload, bytes):
        serialized = payload
    elif isinstance(payload, str):
        serialized = payload.encode("utf-8")
    else:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


@transaction.atomic
def claim_idempotency(*, namespace: str, key: str, payload: object, actor=None) -> IdempotencyClaim:
    """Claim a unique operation or return its existing same-payload record."""

    namespace = namespace.strip()
    key = key.strip()
    if not namespace or not key:
        raise ValueError("Idempotency namespace and key are required.")

    request_hash = hash_request_payload(payload)
    record, created = IdempotencyRecord.objects.get_or_create(
        namespace=namespace,
        key=key,
        defaults={"request_hash": request_hash, "actor": actor},
    )
    if not created:
        record = IdempotencyRecord.objects.select_for_update().get(pk=record.pk)
        if record.request_hash != request_hash:
            raise IdempotencyConflictError(
                "The idempotency key already belongs to a different request payload."
            )
    return IdempotencyClaim(record=record, is_new=created)


@transaction.atomic
def complete_idempotency(
    record_id,
    *,
    result_reference: str = "",
    response=None,
) -> IdempotencyRecord:
    """Complete once; later retries receive the originally persisted result."""

    record = IdempotencyRecord.objects.select_for_update().get(pk=record_id)
    if record.status == IdempotencyStatus.COMPLETED:
        return record
    if record.status != IdempotencyStatus.IN_PROGRESS:
        raise IdempotencyStateError("Only an in-progress idempotency record can complete.")

    record.status = IdempotencyStatus.COMPLETED
    record.result_reference = result_reference
    record.response = response
    record.finished_at = timezone.now()
    record.save(
        update_fields=("status", "result_reference", "response", "finished_at", "updated_at")
    )
    return record


@transaction.atomic
def fail_idempotency(record_id, *, error_code: str) -> IdempotencyRecord:
    """Mark an unfinished claim failed without changing an already completed result."""

    record = IdempotencyRecord.objects.select_for_update().get(pk=record_id)
    if record.status == IdempotencyStatus.FAILED:
        return record
    if record.status != IdempotencyStatus.IN_PROGRESS:
        raise IdempotencyStateError("Only an in-progress idempotency record can fail.")

    record.status = IdempotencyStatus.FAILED
    record.error_code = error_code
    record.finished_at = timezone.now()
    record.save(update_fields=("status", "error_code", "finished_at", "updated_at"))
    return record
