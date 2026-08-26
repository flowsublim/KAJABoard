from __future__ import annotations

import csv
import hashlib
import io

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone

from apps.core.services.audit import record_audit_event
from apps.data_exchange.models import (
    ImportBatch,
    ImportBatchStatus,
    ImportRowResult,
    ImportRowStatus,
)
from apps.finance.models import AccountType, NormalBalance
from apps.finance.services import create_coa_account
from apps.organizations.models import LegalEntity

IMPORT_TYPE_COA = "COA"
TEMPLATE_VERSION_COA = "2C-COA-v1"
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
COA_HEADERS = [
    "account_code",
    "account_name",
    "account_type",
    "normal_balance",
    "report_group",
    "report_subgroup",
    "is_header",
    "is_posting_allowed",
    "manual_journal_allowed",
    "is_cash_bank",
    "is_control_account",
    "effective_from",
    "effective_to",
    "notes",
]
REQUIRED_HEADERS = {"account_code", "account_name", "account_type", "normal_balance"}


def _checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _audit_batch(batch, *, action, actor, reason="", metadata=None):
    record_audit_event(
        action=action,
        target_type=batch._meta.label_lower,
        target_id=batch.pk,
        actor=actor,
        source="data_exchange.service",
        reason=reason,
        after_state={
            "status": batch.status,
            "checksum": batch.checksum,
            "total_rows": batch.total_rows,
            "success_rows": batch.success_rows,
            "failed_rows": batch.failed_rows,
            "warning_rows": batch.warning_rows,
            "skipped_rows": batch.skipped_rows,
        },
        changed_fields=["status", "row_counts"],
        metadata=metadata or {},
    )


def _parse_bool(value) -> bool:
    text = str(value or "").strip().lower()
    if text in {"", "false", "0", "no", "n", "tidak"}:
        return False
    if text in {"true", "1", "yes", "y", "ya"}:
        return True
    raise ValueError("Expected boolean value.")


def _parse_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    return timezone.datetime.strptime(text, "%Y-%m-%d").date()


def _normalize_row(row):
    normalized = {header: str(row.get(header, "") or "").strip() for header in COA_HEADERS}
    normalized["account_type"] = normalized["account_type"].upper()
    normalized["normal_balance"] = normalized["normal_balance"].upper()
    for field in (
        "is_header",
        "is_posting_allowed",
        "manual_journal_allowed",
        "is_cash_bank",
        "is_control_account",
    ):
        normalized[field] = _parse_bool(normalized[field])
    normalized["effective_from"] = _parse_date(normalized["effective_from"]) or timezone.localdate()
    normalized["effective_to"] = _parse_date(normalized["effective_to"])
    return normalized


def _validate_row(raw):
    errors = []
    warnings = []
    normalized = {}
    try:
        normalized = _normalize_row(raw)
    except ValueError as error:
        errors.append(str(error))
    except Exception as error:
        errors.append(str(error))
    if not errors:
        if not normalized["account_code"]:
            errors.append("account_code is required.")
        if not normalized["account_name"]:
            errors.append("account_name is required.")
        if normalized["account_type"] not in AccountType.values:
            errors.append("account_type is not supported.")
        if normalized["normal_balance"] not in NormalBalance.values:
            errors.append("normal_balance is not supported.")
        if normalized["is_header"] and normalized["is_posting_allowed"]:
            errors.append("Header accounts cannot allow posting.")
        if normalized["effective_to"] and normalized["effective_to"] < normalized["effective_from"]:
            errors.append("effective_to cannot be before effective_from.")
    if errors:
        status = ImportRowStatus.ERROR
    elif warnings:
        status = ImportRowStatus.WARNING
    else:
        status = ImportRowStatus.VALID
    return normalized, status, errors or warnings


def _read_csv(payload: bytes):
    if len(payload) > MAX_CSV_BYTES:
        raise ValidationError(f"CSV file is too large. Max size is {MAX_CSV_BYTES} bytes.")
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    headers = set(reader.fieldnames or [])
    missing = REQUIRED_HEADERS - headers
    if missing:
        raise ValidationError(f"Missing required headers: {', '.join(sorted(missing))}.")
    rows = list(reader)
    if len(rows) > MAX_ROWS:
        raise ValidationError(f"CSV file has too many rows. Max rows is {MAX_ROWS}.")
    return rows


@transaction.atomic
def preview_coa_import(*, legal_entity, payload: bytes, source_filename: str, actor=None):
    if not source_filename.lower().endswith(".csv"):
        raise ValidationError("Only CSV import is supported in Phase 2C.")
    entity = LegalEntity.objects.select_for_update().get(pk=legal_entity.pk)
    checksum = _checksum(payload)
    existing = ImportBatch.objects.filter(
        legal_entity=entity,
        import_type=IMPORT_TYPE_COA,
        checksum=checksum,
    ).first()
    if existing:
        existing.replay_count += 1
        existing.last_replayed_at = timezone.now()
        existing.save(update_fields=("replay_count", "last_replayed_at", "updated_at"))
        _audit_batch(
            existing,
            action="data_exchange.importbatch.replayed",
            actor=actor,
            metadata={"source_filename": source_filename},
        )
        return existing
    rows = _read_csv(payload)
    batch = ImportBatch.objects.create(
        legal_entity=entity,
        import_type=IMPORT_TYPE_COA,
        template_version=TEMPLATE_VERSION_COA,
        source_filename=source_filename[:255],
        checksum=checksum,
        uploaded_by=actor,
        status=ImportBatchStatus.UPLOADED,
        total_rows=len(rows),
    )
    warning_count = 0
    failed_count = 0
    row_objects = []
    for index, raw in enumerate(rows, start=2):
        normalized, status, messages = _validate_row(raw)
        if status == ImportRowStatus.WARNING:
            warning_count += 1
        if status == ImportRowStatus.ERROR:
            failed_count += 1
        row_objects.append(
            ImportRowResult(
                batch=batch,
                row_number=index,
                raw_data=raw,
                normalized_data={
                    key: ""
                    if value is None
                    else str(value)
                    if not isinstance(value, bool)
                    else value
                    for key, value in normalized.items()
                },
                status=status,
                messages=messages,
            )
        )
    ImportRowResult.objects.bulk_create(row_objects)
    batch.warning_rows = warning_count
    batch.failed_rows = failed_count
    batch.status = (
        ImportBatchStatus.VALIDATED_WITH_ERRORS
        if failed_count
        else ImportBatchStatus.READY_TO_IMPORT
    )
    batch.save(update_fields=("warning_rows", "failed_rows", "status", "updated_at"))
    _audit_batch(batch, action="data_exchange.importbatch.previewed", actor=actor)
    return batch


def _row_to_values(row: ImportRowResult):
    data = row.normalized_data
    return {
        "account_code": data["account_code"],
        "account_name": data["account_name"],
        "account_type": data["account_type"],
        "normal_balance": data["normal_balance"],
        "report_group": data.get("report_group", ""),
        "report_subgroup": data.get("report_subgroup", ""),
        "is_header": data.get("is_header", False),
        "is_posting_allowed": data.get("is_posting_allowed", True),
        "manual_journal_allowed": data.get("manual_journal_allowed", False),
        "is_cash_bank": data.get("is_cash_bank", False),
        "is_control_account": data.get("is_control_account", False),
        "effective_from": _parse_date(data.get("effective_from")) or timezone.localdate(),
        "effective_to": _parse_date(data.get("effective_to")),
        "notes": data.get("notes", ""),
    }


@transaction.atomic
def confirm_import_batch(*, batch, actor=None, reason=""):
    locked = ImportBatch.objects.select_for_update().get(pk=batch.pk)
    if locked.confirmed_at:
        return locked
    if locked.import_type != IMPORT_TYPE_COA:
        raise ValidationError("Unsupported import type.")
    valid_rows = list(locked.rows.select_for_update().filter(status=ImportRowStatus.VALID))
    imported = 0
    skipped = locked.rows.exclude(status=ImportRowStatus.VALID).count()
    for row in valid_rows:
        try:
            account = create_coa_account(
                actor=actor,
                reason=reason or "COA import confirm",
                legal_entity=locked.legal_entity,
                **_row_to_values(row),
            )
        except (IntegrityError, ValidationError) as error:
            row.status = ImportRowStatus.ERROR
            row.messages = [str(error)]
            row.save(update_fields=("status", "messages", "updated_at"))
            skipped += 1
            continue
        row.status = ImportRowStatus.IMPORTED
        row.target_reference = str(account.pk)
        row.save(update_fields=("status", "target_reference", "updated_at"))
        imported += 1
    locked.success_rows = imported
    locked.skipped_rows = skipped
    locked.failed_rows = locked.rows.filter(status=ImportRowStatus.ERROR).count()
    locked.status = (
        ImportBatchStatus.IMPORTED if locked.failed_rows == 0 else ImportBatchStatus.PARTIAL_FAILED
    )
    locked.confirmed_at = timezone.now()
    locked.save(
        update_fields=(
            "success_rows",
            "skipped_rows",
            "failed_rows",
            "status",
            "confirmed_at",
            "updated_at",
        )
    )
    _audit_batch(locked, action="data_exchange.importbatch.confirmed", actor=actor, reason=reason)
    return locked


def coa_template_csv() -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="coa_template_2c.csv"'
    writer = csv.writer(response)
    writer.writerow(COA_HEADERS)
    writer.writerow(
        [
            "1101",
            "Cash on Hand",
            "ASSET",
            "DEBIT",
            "ASSET",
            "CASH",
            "false",
            "true",
            "false",
            "true",
            "false",
            timezone.localdate().isoformat(),
            "",
            "Example row",
        ]
    )
    return response


def export_coa_csv(queryset) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="coa_export.csv"'
    writer = csv.writer(response)
    writer.writerow(COA_HEADERS)
    for account in queryset:
        writer.writerow(
            [
                account.account_code,
                account.account_name,
                account.account_type,
                account.normal_balance,
                account.report_group,
                account.report_subgroup,
                account.is_header,
                account.is_posting_allowed,
                account.manual_journal_allowed,
                account.is_cash_bank,
                account.is_control_account,
                account.effective_from,
                account.effective_to or "",
                account.notes,
            ]
        )
    return response
