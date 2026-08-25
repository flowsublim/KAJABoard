from concurrent.futures import ThreadPoolExecutor
from datetime import date
from time import sleep

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, close_old_connections

from apps.core.models import (
    AuditEvent,
    DocumentNumberAllocation,
    DocumentSequenceState,
    SequenceResetMode,
)
from apps.core.services import (
    allocate_document_number,
    create_document_sequence,
    preview_document_number,
    update_document_sequence,
)
from apps.organizations.models import LegalEntity

User = get_user_model()


@pytest.fixture
def entity():
    return LegalEntity.objects.create(code="KAJA", name="PT KAJA")


def make_sequence(entity, **overrides):
    values = {
        "legal_entity": entity,
        "document_type": "SO",
        "name": "Sales Order",
        "prefix": "SO-",
        "format_template": "{prefix}{yyyymmdd}-{seq}",
        "padding": 4,
        "reset_mode": SequenceResetMode.DAILY,
        "effective_from": date(2026, 1, 1),
    }
    values.update(overrides)
    return create_document_sequence(**values)


@pytest.mark.django_db
def test_numbering_configuration_normalizes_and_audits(entity):
    actor = User.objects.create_user("owner@example.com", "password")
    sequence = make_sequence(
        entity,
        document_type=" so ",
        prefix=" so- ",
        actor=actor,
        reason="Approved series",
    )

    assert sequence.document_type == "SO"
    assert sequence.prefix == "SO-"
    event = AuditEvent.objects.get(
        target_id=str(sequence.pk),
        action="core.documentsequence.created",
    )
    assert event.actor == actor
    assert event.reason == "Approved series"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "template",
    (
        "{prefix}{yyyymmdd}",
        "{prefix}{seq}{seq}",
        "{prefix}{unknown}-{seq}",
        "{seq:04d}",
        "{{literal}}-{seq}",
    ),
)
def test_invalid_numbering_templates_are_rejected(entity, template):
    with pytest.raises(ValidationError):
        make_sequence(entity, format_template=template)


@pytest.mark.django_db
def test_reset_configuration_requires_period_identity_in_template(entity):
    with pytest.raises(ValidationError, match="uniquely identify its reset period"):
        make_sequence(entity, format_template="{prefix}{seq}", reset_mode=SequenceResetMode.DAILY)


@pytest.mark.django_db
def test_preview_does_not_consume_sequence(entity):
    make_sequence(entity)

    first_preview = preview_document_number(entity, "SO", business_date=date(2026, 8, 25))
    second_preview = preview_document_number(entity, "SO", business_date=date(2026, 8, 25))

    assert first_preview == second_preview == "SO-20260825-0001"
    assert DocumentSequenceState.objects.count() == 0
    assert DocumentNumberAllocation.objects.count() == 0
    allocated = allocate_document_number(entity, "SO", business_date=date(2026, 8, 25))
    assert allocated.number == first_preview


@pytest.mark.django_db
def test_daily_period_reset_and_increment_are_deterministic(entity):
    make_sequence(entity)

    first = allocate_document_number(entity, "SO", business_date=date(2026, 8, 25))
    second = allocate_document_number(entity, "SO", business_date=date(2026, 8, 25))
    next_day = allocate_document_number(entity, "SO", business_date=date(2026, 8, 26))

    assert first.number == "SO-20260825-0001"
    assert second.number == "SO-20260825-0002"
    assert next_day.number == "SO-20260826-0001"


@pytest.mark.django_db
def test_monthly_reset_uses_one_counter_per_calendar_month(entity):
    make_sequence(
        entity,
        document_type="INV",
        name="Invoice",
        prefix="INV-",
        format_template="{prefix}{yymmdd}/{seq}",
        padding=3,
        reset_mode=SequenceResetMode.MONTHLY,
    )

    january = allocate_document_number(entity, "INV", business_date=date(2026, 1, 31))
    february = allocate_document_number(entity, "INV", business_date=date(2026, 2, 1))

    assert january.number == "INV-260131/001"
    assert february.number == "INV-260201/001"


@pytest.mark.django_db
def test_request_key_retry_returns_original_allocation_without_consuming(entity):
    make_sequence(entity)

    original = allocate_document_number(
        entity,
        "SO",
        business_date=date(2026, 8, 25),
        request_key="sales-order:123",
    )
    replay = allocate_document_number(
        entity,
        "SO",
        business_date=date(2026, 8, 25),
        request_key="sales-order:123",
    )
    next_number = allocate_document_number(
        entity,
        "SO",
        business_date=date(2026, 8, 25),
        request_key="sales-order:124",
    )

    assert replay.pk == original.pk
    assert next_number.sequence_value == original.sequence_value + 1
    with pytest.raises(ValidationError, match="different business date"):
        allocate_document_number(
            entity,
            "SO",
            business_date=date(2026, 8, 26),
            request_key="sales-order:123",
        )


@pytest.mark.django_db
def test_database_prevents_duplicate_final_number_within_entity(entity):
    make_sequence(
        entity,
        document_type="TYPE_A",
        name="Type A",
        prefix="DUP-",
        format_template="{prefix}{seq}",
        padding=3,
        reset_mode=SequenceResetMode.NEVER,
    )
    make_sequence(
        entity,
        document_type="TYPE_B",
        name="Type B",
        prefix="DUP-",
        format_template="{prefix}{seq}",
        padding=3,
        reset_mode=SequenceResetMode.NEVER,
    )
    allocate_document_number(entity, "TYPE_A", business_date=date(2026, 8, 25))

    with pytest.raises(IntegrityError):
        allocate_document_number(entity, "TYPE_B", business_date=date(2026, 8, 25))


@pytest.mark.django_db
def test_numbering_configuration_periods_cannot_overlap(entity):
    make_sequence(entity, effective_to=date(2026, 6, 30))

    with pytest.raises(ValidationError, match="cannot overlap"):
        make_sequence(entity, effective_from=date(2026, 6, 30))

    later = make_sequence(entity, effective_from=date(2026, 7, 1))
    assert later.effective_from == date(2026, 7, 1)


@pytest.mark.django_db
def test_allocated_series_requires_new_effective_version_for_reformat(entity):
    sequence = make_sequence(entity)
    allocate_document_number(entity, "SO", business_date=date(2026, 8, 25))

    with pytest.raises(ValidationError, match="cannot be reformatted"):
        update_document_sequence(sequence, prefix="NEW-", reason="Requested format change")


@pytest.mark.django_db(transaction=True)
def test_concurrent_retrying_allocations_produce_unique_numbers():
    entity = LegalEntity.objects.create(code="KAJA", name="PT KAJA")
    make_sequence(entity)

    def worker(index):
        last_error = None
        for attempt in range(20):
            close_old_connections()
            try:
                current_entity = LegalEntity.objects.get(pk=entity.pk)
                allocation = allocate_document_number(
                    current_entity,
                    "SO",
                    business_date=date(2026, 8, 25),
                    request_key=f"concurrent:{index}",
                )
                close_old_connections()
                return allocation.number
            except OperationalError as error:
                last_error = error
                close_old_connections()
                sleep(0.01 * (attempt + 1))
        raise last_error

    with ThreadPoolExecutor(max_workers=5) as executor:
        numbers = list(executor.map(worker, range(5)))

    assert len(numbers) == len(set(numbers)) == 5
    assert DocumentNumberAllocation.objects.count() == 5
