from __future__ import annotations

from datetime import datetime
from string import Formatter

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import (
    DocumentNumberAllocation,
    DocumentSequence,
    DocumentSequenceState,
    SequenceResetMode,
)
from apps.core.selectors import document_sequence_for_date
from apps.core.services.audit import record_audit_event
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.organizations.models import LegalEntity

ALLOWED_TEMPLATE_TOKENS = {
    "prefix",
    "yyyy",
    "yy",
    "mm",
    "dd",
    "yyyymmdd",
    "yymmdd",
    "seq",
}


def _normalize(values: dict[str, object]) -> dict[str, object]:
    normalized = values.copy()
    for field in ("document_type", "prefix"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = value.strip().upper()
    for field in ("name", "format_template", "notes"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = value.strip()
    return normalized


def _as_date(value):
    if value is None:
        return timezone.localdate()
    if isinstance(value, datetime):
        return value.date()
    return value


def validate_number_template(*, template: str, prefix: str, padding: int) -> None:
    if not template:
        raise ValidationError({"format_template": "A numbering template is required."})
    if "{{" in template or "}}" in template:
        raise ValidationError(
            {"format_template": "Escaped literal braces are not supported in numbering templates."}
        )
    if "{" in prefix or "}" in prefix:
        raise ValidationError({"prefix": "Prefix cannot contain template braces."})
    fields = []
    try:
        parsed = list(Formatter().parse(template))
    except ValueError as exc:
        raise ValidationError({"format_template": "Template braces are invalid."}) from exc
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name not in ALLOWED_TEMPLATE_TOKENS:
            raise ValidationError(
                {"format_template": f"Unsupported template token: {{{field_name}}}."}
            )
        if format_spec or conversion:
            raise ValidationError(
                {"format_template": "Format specifications and conversions are not supported."}
            )
        fields.append(field_name)
    if fields.count("seq") != 1:
        raise ValidationError({"format_template": "Template must contain exactly one {seq} token."})
    if not 1 <= padding <= 12:
        raise ValidationError({"padding": "Padding must be between 1 and 12."})


def _date_tokens(business_date, *, prefix: str, sequence_value: int, padding: int):
    yyyy = f"{business_date.year:04d}"
    mm = f"{business_date.month:02d}"
    dd = f"{business_date.day:02d}"
    return {
        "prefix": prefix,
        "yyyy": yyyy,
        "yy": yyyy[-2:],
        "mm": mm,
        "dd": dd,
        "yyyymmdd": f"{yyyy}{mm}{dd}",
        "yymmdd": f"{yyyy[-2:]}{mm}{dd}",
        "seq": str(sequence_value).zfill(padding),
    }


def render_document_number(sequence, *, business_date, sequence_value: int) -> str:
    validate_number_template(
        template=sequence.format_template,
        prefix=sequence.prefix,
        padding=sequence.padding,
    )
    sequence.full_clean()
    number = sequence.format_template.format(
        **_date_tokens(
            business_date,
            prefix=sequence.prefix,
            sequence_value=sequence_value,
            padding=sequence.padding,
        )
    )
    if not number or len(number) > 120:
        raise ValidationError(
            {"format_template": "Rendered document number must be between 1 and 120 characters."}
        )
    return number


def period_key(reset_mode: str, business_date) -> str:
    if reset_mode == SequenceResetMode.DAILY:
        return business_date.strftime("%Y%m%d")
    if reset_mode == SequenceResetMode.MONTHLY:
        return business_date.strftime("%Y%m")
    if reset_mode == SequenceResetMode.YEARLY:
        return business_date.strftime("%Y")
    return "ALL"


def _validate_no_overlap(sequence: DocumentSequence, *, exclude_pk=None) -> None:
    queryset = DocumentSequence.objects.filter(
        legal_entity=sequence.legal_entity,
        document_type=sequence.document_type,
    )
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    queryset = queryset.filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=sequence.effective_from)
    )
    if sequence.effective_to:
        queryset = queryset.filter(effective_from__lte=sequence.effective_to)
    if queryset.exists():
        raise ValidationError(
            {"effective_from": "Numbering configurations for the same scope cannot overlap."}
        )


def _validate_sequence(sequence: DocumentSequence, *, exclude_pk=None) -> None:
    validate_number_template(
        template=sequence.format_template,
        prefix=sequence.prefix,
        padding=sequence.padding,
    )
    template = sequence.format_template
    has_year = "{yyyy}" in template or "{yy}" in template
    has_month = "{mm}" in template
    has_day = "{dd}" in template
    has_full_date = "{yyyymmdd}" in template or "{yymmdd}" in template
    reset_has_period_token = {
        SequenceResetMode.NEVER: True,
        SequenceResetMode.YEARLY: has_year or has_full_date,
        SequenceResetMode.MONTHLY: has_full_date or (has_year and has_month),
        SequenceResetMode.DAILY: has_full_date or (has_year and has_month and has_day),
    }[sequence.reset_mode]
    if not reset_has_period_token:
        raise ValidationError(
            {
                "format_template": (
                    "Template must contain date tokens that uniquely identify its reset period."
                )
            }
        )
    _validate_no_overlap(sequence, exclude_pk=exclude_pk)
    render_document_number(
        sequence,
        business_date=sequence.effective_from,
        sequence_value=sequence.starting_number,
    )


@transaction.atomic
def create_document_sequence(*, actor=None, reason="", idempotency_key="", **values):
    values = _normalize(values)
    legal_entity = LegalEntity.objects.select_for_update().get(pk=values["legal_entity"].pk)
    values["legal_entity"] = legal_entity
    sequence = DocumentSequence(**values)
    _validate_sequence(sequence)
    sequence.save()
    after = model_snapshot(sequence)
    record_audit_event(
        action="core.documentsequence.created",
        target_type=sequence._meta.label_lower,
        target_id=sequence.pk,
        actor=actor,
        source="core.numbering.service",
        reason=reason,
        idempotency_key=idempotency_key,
        after_state=after,
        changed_fields=sorted(after),
    )
    return sequence


@transaction.atomic
def update_document_sequence(sequence, *, actor=None, reason="", idempotency_key="", **values):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to edit numbering configuration."})
    LegalEntity.objects.select_for_update().get(pk=sequence.legal_entity_id)
    locked = DocumentSequence.objects.select_for_update().get(pk=sequence.pk)
    values = _normalize(values)
    if "legal_entity" in values and values["legal_entity"].pk != locked.legal_entity_id:
        raise ValidationError({"legal_entity": "A numbering configuration cannot change entity."})
    if "document_type" in values and values["document_type"] != locked.document_type:
        raise ValidationError({"document_type": "Document type is a stable configuration key."})
    semantic_fields = {
        "prefix",
        "format_template",
        "padding",
        "starting_number",
        "reset_mode",
        "effective_from",
    }
    if locked.allocations.exists() and any(
        field in values and getattr(locked, field) != values[field] for field in semantic_fields
    ):
        raise ValidationError(
            "An allocated series cannot be reformatted; end it and create a new effective version."
        )
    before = model_snapshot(locked)
    for field, value in values.items():
        setattr(locked, field, value)
    _validate_sequence(locked, exclude_pk=locked.pk)
    locked.save()
    after = model_snapshot(locked)
    record_audit_event(
        action="core.documentsequence.updated",
        target_type=locked._meta.label_lower,
        target_id=locked.pk,
        actor=actor,
        source="core.numbering.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    return locked


@transaction.atomic
def deactivate_document_sequence(
    sequence, *, actor=None, reason: str, effective_to=None, idempotency_key=""
):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to deactivate numbering."})
    LegalEntity.objects.select_for_update().get(pk=sequence.legal_entity_id)
    locked = DocumentSequence.objects.select_for_update().get(pk=sequence.pk)
    if not locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = False
    locked.effective_to = max(_as_date(effective_to), locked.effective_from)
    locked.full_clean()
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    after = model_snapshot(locked)
    record_audit_event(
        action="core.documentsequence.deactivated",
        target_type=locked._meta.label_lower,
        target_id=locked.pk,
        actor=actor,
        source="core.numbering.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    return locked


@transaction.atomic
def reactivate_document_sequence(sequence, *, actor=None, reason: str, idempotency_key=""):
    if not reason.strip():
        raise ValidationError({"reason": "A reason is required to reactivate numbering."})
    LegalEntity.objects.select_for_update().get(pk=sequence.legal_entity_id)
    locked = DocumentSequence.objects.select_for_update().get(pk=sequence.pk)
    if locked.is_active:
        return locked
    before = model_snapshot(locked)
    locked.is_active = True
    locked.effective_to = None
    _validate_sequence(locked, exclude_pk=locked.pk)
    locked.save(update_fields=("is_active", "effective_to", "updated_at"))
    after = model_snapshot(locked)
    record_audit_event(
        action="core.documentsequence.reactivated",
        target_type=locked._meta.label_lower,
        target_id=locked.pk,
        actor=actor,
        source="core.numbering.service",
        reason=reason,
        idempotency_key=idempotency_key,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after),
    )
    return locked


def preview_document_number(legal_entity, document_type, *, business_date=None) -> str:
    business_date = _as_date(business_date)
    sequence = document_sequence_for_date(
        legal_entity,
        document_type,
        business_date=business_date,
    )
    key = period_key(sequence.reset_mode, business_date)
    state = DocumentSequenceState.objects.filter(sequence=sequence, period_key=key).first()
    next_value = (state.last_value + 1) if state else sequence.starting_number
    return render_document_number(
        sequence,
        business_date=business_date,
        sequence_value=next_value,
    )


@transaction.atomic
def allocate_document_number(
    legal_entity,
    document_type,
    *,
    business_date=None,
    request_key="",
    actor=None,
):
    business_date = _as_date(business_date)
    document_type = str(document_type).strip().upper()
    request_key = str(request_key).strip()
    locked_entity = LegalEntity.objects.select_for_update().get(pk=legal_entity.pk)
    if request_key:
        existing = (
            DocumentNumberAllocation.objects.select_for_update()
            .filter(
                legal_entity=locked_entity,
                document_type=document_type,
                request_key=request_key,
            )
            .first()
        )
        if existing:
            if existing.business_date != business_date:
                raise ValidationError(
                    {"request_key": "This request key was used with a different business date."}
                )
            return existing
    sequence = document_sequence_for_date(
        locked_entity,
        document_type,
        business_date=business_date,
        for_update=True,
    )
    key = period_key(sequence.reset_mode, business_date)
    state, created = DocumentSequenceState.objects.get_or_create(
        sequence=sequence,
        period_key=key,
        defaults={"last_value": sequence.starting_number - 1},
    )
    if not created:
        state = DocumentSequenceState.objects.select_for_update().get(pk=state.pk)
    next_value = state.last_value + 1
    number = render_document_number(
        sequence,
        business_date=business_date,
        sequence_value=next_value,
    )
    allocation = DocumentNumberAllocation.objects.create(
        sequence=sequence,
        legal_entity=locked_entity,
        document_type=document_type,
        business_date=business_date,
        period_key=key,
        sequence_value=next_value,
        number=number,
        request_key=request_key,
        allocated_by=actor,
    )
    state.last_value = next_value
    state.save(update_fields=("last_value", "updated_at"))
    return allocation
