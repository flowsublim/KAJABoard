"""Explicit Finance-owned journal posting and reversal services."""

from dataclasses import asdict
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.finance.models import JournalEntry, JournalLine, JournalState, ReceivableEntry
from apps.finance.services.mappings import FinanceMappingError, resolve_account_mapping


def _amount(value):
    amount = Decimal(str(value))
    if amount != amount.to_integral_value() or amount <= 0:
        raise ValidationError("Journal amounts must be positive whole Rupiah.")
    return amount


@transaction.atomic
def post_journal(
    *,
    legal_entity,
    source_key,
    source_module,
    source_document_type,
    source_document_id,
    event_code,
    accounting_date,
    lines,
    actor,
    source_reference=None,
    description="",
    ar=None,
):
    existing = (
        JournalEntry.objects.select_for_update()
        .filter(legal_entity=legal_entity, source_key=source_key)
        .first()
    )
    if existing:
        return existing
    prepared = []
    for sequence, line in enumerate(lines, 1):
        amount = _amount(line["amount"])
        dc = line["dc"]
        if dc not in {"DEBIT", "CREDIT"}:
            raise ValidationError("Journal direction must be DEBIT or CREDIT.")
        try:
            mapping = resolve_account_mapping(
                legal_entity=legal_entity,
                module_code=source_module,
                event_code=event_code,
                line_role=line["line_role"],
                dc=dc,
                business_date=accounting_date,
                context=line.get("context", {}),
            )
        except FinanceMappingError as exc:
            raise ValidationError({"mapping": f"BLOCKED_MAPPING: {exc}"}) from exc
        prepared.append((sequence, line, amount, mapping))
    debit = sum((amount for _, line, amount, _ in prepared if line["dc"] == "DEBIT"), Decimal("0"))
    credit = sum(
        (amount for _, line, amount, _ in prepared if line["dc"] == "CREDIT"), Decimal("0")
    )
    if debit != credit:
        raise ValidationError("Journal debit must equal credit.")
    entry = JournalEntry.objects.create(
        legal_entity=legal_entity,
        journal_number=f"JRN-{uuid4().hex[:12].upper()}",
        accounting_date=accounting_date,
        event_code=event_code,
        source_module=source_module,
        source_document_type=source_document_type,
        source_document_id=str(source_document_id),
        source_key=source_key,
        source_reference=source_reference or {},
        total_debit=debit,
        total_credit=credit,
        description=description,
        posted_at=timezone.now(),
        posted_by=actor,
    )
    for sequence, line, amount, mapping in prepared:
        JournalLine.objects.create(
            journal=entry,
            sequence=sequence,
            line_role=line["line_role"],
            account_id=mapping.account_id,
            account_code_snapshot=mapping.account_code,
            account_name_snapshot=mapping.account_name,
            debit=amount if line["dc"] == "DEBIT" else 0,
            credit=amount if line["dc"] == "CREDIT" else 0,
            mapping_snapshot={
                **asdict(mapping),
                "business_date": mapping.business_date.isoformat(),
            },
        )
    if ar:
        ReceivableEntry.objects.create(
            journal=entry,
            legal_entity=legal_entity,
            accounting_date=accounting_date,
            original_amount=ar["amount"],
            open_amount=ar["amount"],
            currency=ar.get("currency", "IDR"),
            partner=ar.get("partner"),
            store=ar.get("store"),
        )
    return entry


@transaction.atomic
def reverse_journal(entry, *, actor, source_key):
    entry = JournalEntry.objects.select_for_update().prefetch_related("lines").get(pk=entry.pk)
    if hasattr(entry, "reversal"):
        return entry.reversal
    lines = []
    for line in entry.lines.all():
        lines.append(
            {
                "line_role": line.line_role,
                "dc": "CREDIT" if line.debit else "DEBIT",
                "amount": line.debit or line.credit,
                "context": {},
            }
        )
    # Reuse original mapping snapshots exactly for reversal audit fidelity.
    reversal = JournalEntry.objects.create(
        legal_entity=entry.legal_entity,
        journal_number=f"JRV-{uuid4().hex[:12].upper()}",
        accounting_date=entry.accounting_date,
        event_code=f"{entry.event_code}_REVERSAL",
        source_module=entry.source_module,
        source_document_type=entry.source_document_type,
        source_document_id=entry.source_document_id,
        source_key=source_key,
        source_reference=entry.source_reference,
        total_debit=entry.total_credit,
        total_credit=entry.total_debit,
        description=f"Reversal of {entry.journal_number}",
        posted_at=timezone.now(),
        posted_by=actor,
        reversal_of=entry,
    )
    for sequence, line in enumerate(entry.lines.all(), 1):
        JournalLine.objects.create(
            journal=reversal,
            sequence=sequence,
            line_role=line.line_role,
            account=line.account,
            account_code_snapshot=line.account_code_snapshot,
            account_name_snapshot=line.account_name_snapshot,
            debit=line.credit,
            credit=line.debit,
            mapping_snapshot=line.mapping_snapshot,
            metadata={"reversal_of_line": str(line.pk)},
        )
    entry.state = JournalState.REVERSED
    entry.save(update_fields=("state", "updated_at"))
    if hasattr(entry, "receivable"):
        ReceivableEntry.objects.create(
            journal=reversal,
            legal_entity=entry.legal_entity,
            accounting_date=entry.accounting_date,
            original_amount=-entry.receivable.original_amount,
            open_amount=-entry.receivable.open_amount,
            currency=entry.receivable.currency,
            partner=entry.receivable.partner,
            store=entry.receivable.store,
        )
    return reversal
