import pytest
from django.db import IntegrityError, transaction

from apps.core.exceptions import IdempotencyConflictError, IdempotencyStateError
from apps.core.models import IdempotencyRecord, IdempotencyStatus
from apps.core.services.idempotency import (
    claim_idempotency,
    complete_idempotency,
    fail_idempotency,
    hash_request_payload,
)


def test_request_hash_is_deterministic_for_json_object_key_order():
    assert hash_request_payload({"quantity": 1, "sku": "A"}) == hash_request_payload(
        {"sku": "A", "quantity": 1}
    )


@pytest.mark.django_db
def test_same_key_and_payload_returns_original_claim():
    first = claim_idempotency(namespace="test", key="request-1", payload={"value": 1})
    replay = claim_idempotency(namespace="test", key="request-1", payload={"value": 1})

    assert first.is_new is True
    assert replay.is_replay is True
    assert replay.record.pk == first.record.pk


@pytest.mark.django_db
def test_same_key_with_different_payload_is_rejected():
    claim_idempotency(namespace="test", key="request-1", payload={"value": 1})

    with pytest.raises(IdempotencyConflictError, match="different request payload"):
        claim_idempotency(namespace="test", key="request-1", payload={"value": 2})


@pytest.mark.django_db
def test_namespace_and_key_database_constraint_is_unique():
    IdempotencyRecord.objects.create(namespace="test", key="request-1", request_hash="a" * 64)

    with pytest.raises(IntegrityError), transaction.atomic():
        IdempotencyRecord.objects.create(
            namespace="test",
            key="request-1",
            request_hash="a" * 64,
        )


@pytest.mark.django_db
def test_completed_claim_replays_original_result():
    claim = claim_idempotency(namespace="test", key="request-1", payload={"value": 1})
    completed = complete_idempotency(
        claim.record.pk,
        result_reference="result-1",
        response={"created": True},
    )
    replayed = complete_idempotency(
        claim.record.pk,
        result_reference="different-result",
        response={"created": False},
    )

    assert completed.status == IdempotencyStatus.COMPLETED
    assert completed.finished_at is not None
    assert replayed.result_reference == "result-1"
    assert replayed.response == {"created": True}


@pytest.mark.django_db
def test_failed_claim_cannot_be_completed():
    claim = claim_idempotency(namespace="test", key="request-1", payload={"value": 1})
    failed = fail_idempotency(claim.record.pk, error_code="EXPECTED_TEST_FAILURE")

    assert failed.status == IdempotencyStatus.FAILED
    assert failed.finished_at is not None
    with pytest.raises(IdempotencyStateError, match="in-progress"):
        complete_idempotency(claim.record.pk)


@pytest.mark.django_db
def test_finish_state_constraint_rejects_completed_without_timestamp():
    with pytest.raises(IntegrityError), transaction.atomic():
        IdempotencyRecord.objects.create(
            namespace="test",
            key="request-1",
            request_hash="a" * 64,
            status=IdempotencyStatus.COMPLETED,
        )
