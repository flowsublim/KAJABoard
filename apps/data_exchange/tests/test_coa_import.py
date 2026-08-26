import pytest
from django.contrib.auth import get_user_model

from apps.data_exchange.models import ImportBatch, ImportBatchStatus, ImportRowStatus
from apps.data_exchange.services import confirm_import_batch, preview_coa_import
from apps.finance.models import COAAccount
from apps.organizations.models import LegalEntity, OrganizationMembership

User = get_user_model()


@pytest.fixture
def entity():
    return LegalEntity.objects.create(code="KAJA", name="PT KAJA")


@pytest.fixture
def user(entity):
    user = User.objects.create_user("member@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    return user


def csv_payload(*rows):
    header = (
        "account_code,account_name,account_type,normal_balance,report_group,"
        "report_subgroup,is_header,is_posting_allowed,manual_journal_allowed,"
        "is_cash_bank,is_control_account,effective_from,effective_to,notes\n"
    )
    return (header + "\n".join(rows) + "\n").encode()


@pytest.mark.django_db
def test_coa_import_preview_does_not_mutate_master_and_records_rows(entity, user):
    payload = csv_payload(
        "1101,Cash,ASSET,DEBIT,ASSET,CASH,false,true,false,true,false,2026-01-01,,ok",
        "BAD,MissingType,UNKNOWN,DEBIT,,,,,,,,,,",
    )

    batch = preview_coa_import(
        legal_entity=entity,
        payload=payload,
        source_filename="coa.csv",
        actor=user,
    )

    assert batch.status == ImportBatchStatus.VALIDATED_WITH_ERRORS
    assert batch.total_rows == 2
    assert batch.failed_rows == 1
    assert COAAccount.objects.count() == 0
    assert batch.rows.filter(status=ImportRowStatus.VALID).count() == 1
    assert batch.rows.filter(status=ImportRowStatus.ERROR).count() == 1


@pytest.mark.django_db
def test_coa_import_replay_uses_checksum_without_creating_new_batch(entity, user):
    payload = csv_payload(
        "1101,Cash,ASSET,DEBIT,ASSET,CASH,false,true,false,true,false,2026-01-01,,ok"
    )
    first = preview_coa_import(
        legal_entity=entity,
        payload=payload,
        source_filename="coa.csv",
        actor=user,
    )
    second = preview_coa_import(
        legal_entity=entity,
        payload=payload,
        source_filename="coa-again.csv",
        actor=user,
    )

    assert second.pk == first.pk
    assert second.replay_count == 1
    assert ImportBatch.objects.count() == 1


@pytest.mark.django_db
def test_coa_import_confirm_mutates_only_valid_rows(entity, user):
    payload = csv_payload(
        "1101,Cash,ASSET,DEBIT,ASSET,CASH,false,true,false,true,false,2026-01-01,,ok",
        "BAD,MissingType,UNKNOWN,DEBIT,,,,,,,,,,",
    )
    batch = preview_coa_import(
        legal_entity=entity,
        payload=payload,
        source_filename="coa.csv",
        actor=user,
    )

    confirmed = confirm_import_batch(batch=batch, actor=user, reason="Approved import")

    assert confirmed.status == ImportBatchStatus.PARTIAL_FAILED
    assert confirmed.success_rows == 1
    assert confirmed.failed_rows == 1
    assert COAAccount.objects.get().account_code == "1101"
    assert batch.rows.filter(status=ImportRowStatus.IMPORTED).count() == 1

    repeated = confirm_import_batch(batch=batch, actor=user, reason="Retry")

    assert repeated.pk == confirmed.pk
    assert repeated.success_rows == 1
    assert COAAccount.objects.count() == 1
