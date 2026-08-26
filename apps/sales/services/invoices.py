from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import IdempotencyStatus
from apps.core.services.audit import record_audit_event
from apps.core.services.idempotency import claim_idempotency, complete_idempotency
from apps.core.services.numbering import allocate_document_number
from apps.core.services.snapshots import changed_field_names, model_snapshot
from apps.organizations.models import LegalEntity
from apps.partners.models import BusinessPartner
from apps.sales.models import (
    DiscountType,
    InvoiceSourceMode,
    SalesDeliveryLine,
    SalesDeliveryState,
    SalesInvoice,
    SalesInvoiceDocumentKind,
    SalesInvoiceLine,
    SalesInvoiceState,
    SalesOrderLine,
    SalesOrderState,
)

SALES_INVOICE_DOCUMENT_TYPE = "SALES_INVOICE"
PROFORMA_DOCUMENT_TYPE = "PROFORMA"
MONEY_QUANTUM = Decimal("0.01")
HUNDRED = Decimal("100")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _quantity(value) -> Decimal:
    return Decimal(str(value or 0))


def _text(value) -> str:
    return " ".join(str(value or "").split())


def _audit(instance, *, action, actor=None, reason="", before=None, metadata=None):
    after = model_snapshot(instance)
    record_audit_event(
        action=action,
        target_type=instance._meta.label_lower,
        target_id=instance.pk,
        actor=actor,
        source="sales.invoice_service",
        reason=reason,
        before_state=before,
        after_state=after,
        changed_fields=changed_field_names(before, after) if before else sorted(after),
        metadata=metadata or {},
    )


def _assert_draft(invoice: SalesInvoice):
    if invoice.state != SalesInvoiceState.DRAFT:
        raise ValidationError("Only DRAFT Sales Invoice sources can be edited.")


def _snapshot_customer(invoice: SalesInvoice):
    invoice.customer_code_snapshot = invoice.customer.code
    invoice.customer_name_snapshot = invoice.customer.display_name
    invoice.customer_legal_name_snapshot = invoice.customer.legal_name


def _calculate_line(line: SalesInvoiceLine):
    if line.quantity <= 0:
        raise ValidationError({"quantity": "Invoice quantity must be greater than zero."})
    if line.unit_price < 0:
        raise ValidationError({"unit_price": "Unit price cannot be negative."})
    if line.discount_value < 0 or line.tax_rate < 0:
        raise ValidationError("Discount and tax rate cannot be negative.")
    line.line_amount = _money(line.quantity * line.unit_price)
    if line.discount_type == DiscountType.PERCENT:
        if line.discount_value > HUNDRED:
            raise ValidationError({"discount_value": "Percentage discount cannot exceed 100."})
        line.line_discount_amount = _money(line.line_amount * line.discount_value / HUNDRED)
    else:
        line.line_discount_amount = _money(line.discount_value)
    if line.line_discount_amount > line.line_amount:
        raise ValidationError({"discount_value": "Discount cannot exceed line amount."})
    line.line_tax_base = _money(line.line_amount - line.line_discount_amount)
    line.line_tax_amount = _money(line.line_tax_base * line.tax_rate / HUNDRED)
    line.line_total = _money(line.line_tax_base + line.line_tax_amount)


def _refresh_totals(invoice: SalesInvoice):
    lines = list(invoice.lines.all())
    invoice.subtotal = _money(sum((line.line_amount for line in lines), Decimal("0")))
    invoice.discount_total = _money(
        sum((line.line_discount_amount for line in lines), Decimal("0"))
    )
    invoice.tax_total = _money(sum((line.line_tax_amount for line in lines), Decimal("0")))
    invoice.freight_amount = _money(invoice.freight_amount)
    invoice.grand_total = _money(
        invoice.subtotal - invoice.discount_total + invoice.tax_total + invoice.freight_amount
    )


def _validate_customer(customer, entity):
    if customer.legal_entity_id != entity.id:
        raise ValidationError({"customer": "Customer must belong to the invoice legal entity."})


def _create_payload(entity, customer, invoice_date, source_mode, document_kind, values):
    return {
        "entity": str(entity.pk),
        "customer": str(customer.pk),
        "date": invoice_date.isoformat(),
        "source_mode": source_mode,
        "kind": document_kind,
        "currency": _text(values.get("currency", entity.reporting_currency)).upper(),
        "freight": str(values.get("freight_amount", 0)),
        "reason": _text(values.get("source_exception_reason")),
    }


@transaction.atomic
def create_draft_invoice(
    *,
    actor=None,
    idempotency_key="",
    source_mode=InvoiceSourceMode.DELIVERY,
    document_kind=SalesInvoiceDocumentKind.INVOICE,
    **values,
) -> SalesInvoice:
    entity = LegalEntity.objects.select_for_update().get(pk=values["legal_entity"].pk)
    customer = BusinessPartner.objects.get(pk=values["customer"].pk)
    invoice_date = values["invoice_date"]
    _validate_customer(customer, entity)
    if source_mode not in InvoiceSourceMode.values:
        raise ValidationError({"source_mode": "Unsupported invoice source mode."})
    if document_kind not in SalesInvoiceDocumentKind.values:
        raise ValidationError({"document_kind": "Unsupported invoice document kind."})
    exception_reason = _text(values.get("source_exception_reason"))
    if (
        source_mode == InvoiceSourceMode.SALES_ORDER
        and document_kind == SalesInvoiceDocumentKind.INVOICE
    ):
        if not exception_reason:
            raise ValidationError(
                {"source_exception_reason": "Sales Order invoice exception reason is required."}
            )
    payload = _create_payload(entity, customer, invoice_date, source_mode, document_kind, values)
    if idempotency_key:
        claim = claim_idempotency(
            namespace="sales.invoice.create", key=idempotency_key, payload=payload, actor=actor
        )
        if not claim.is_new:
            if claim.record.status == IdempotencyStatus.COMPLETED and claim.record.result_reference:
                return SalesInvoice.objects.get(pk=claim.record.result_reference)
            raise ValidationError(
                "A prior invoice request with this idempotency key is still in progress."
            )
    else:
        claim = None
    document_type = (
        PROFORMA_DOCUMENT_TYPE
        if document_kind == SalesInvoiceDocumentKind.PROFORMA
        else SALES_INVOICE_DOCUMENT_TYPE
    )
    allocation = allocate_document_number(
        entity,
        document_type,
        business_date=invoice_date,
        request_key=f"sales-invoice:{idempotency_key}" if idempotency_key else "",
        actor=actor,
    )
    invoice = SalesInvoice(
        legal_entity=entity,
        document_allocation=allocation,
        document_number=allocation.number,
        invoice_date=invoice_date,
        customer=customer,
        source_mode=source_mode,
        document_kind=document_kind,
        source_exception_reason=exception_reason,
        currency=_text(values.get("currency", entity.reporting_currency)).upper(),
        freight_amount=_money(values.get("freight_amount", 0)),
        notes=str(values.get("notes", "") or "").strip(),
        created_by=actor,
    )
    if len(invoice.currency) != 3:
        raise ValidationError({"currency": "Currency must be a three-letter code."})
    _snapshot_customer(invoice)
    invoice.full_clean()
    invoice.save()
    _audit(
        invoice,
        action="sales.salesinvoice.created",
        actor=actor,
        metadata={"source_mode": source_mode, "document_kind": document_kind},
    )
    if claim:
        complete_idempotency(
            claim.record.pk,
            result_reference=str(invoice.pk),
            response={
                "sales_invoice_id": str(invoice.pk),
                "document_number": invoice.document_number,
            },
        )
    return invoice


def create_draft_delivery_invoice(*, actor=None, idempotency_key="", **values) -> SalesInvoice:
    return create_draft_invoice(
        actor=actor,
        idempotency_key=idempotency_key,
        source_mode=InvoiceSourceMode.DELIVERY,
        document_kind=SalesInvoiceDocumentKind.INVOICE,
        **values,
    )


def create_draft_sales_order_invoice(*, actor=None, idempotency_key="", **values) -> SalesInvoice:
    return create_draft_invoice(
        actor=actor,
        idempotency_key=idempotency_key,
        source_mode=InvoiceSourceMode.SALES_ORDER,
        document_kind=SalesInvoiceDocumentKind.INVOICE,
        **values,
    )


def create_proforma(*, actor=None, idempotency_key="", **values) -> SalesInvoice:
    return create_draft_invoice(
        actor=actor,
        idempotency_key=idempotency_key,
        source_mode=InvoiceSourceMode.SALES_ORDER,
        document_kind=SalesInvoiceDocumentKind.PROFORMA,
        **values,
    )


def _next_line_number(invoice: SalesInvoice) -> int:
    return (
        invoice.lines.order_by("-line_number").values_list("line_number", flat=True).first() or 0
    ) + 1


def _validate_order_line(invoice: SalesInvoice, source: SalesOrderLine):
    order = source.sales_order
    if order.legal_entity_id != invoice.legal_entity_id:
        raise ValidationError("Sales Order line must belong to the invoice legal entity.")
    if order.customer_id != invoice.customer_id:
        raise ValidationError("All invoice lines must belong to the selected customer.")
    if order.state != SalesOrderState.CONFIRMED:
        raise ValidationError("Only CONFIRMED Sales Order lines are eligible for invoicing.")


def _add_line(
    invoice: SalesInvoice, *, source: SalesOrderLine, quantity, delivery_line=None, notes=""
):
    qty = _quantity(quantity)
    if qty <= 0:
        raise ValidationError({"quantity": "Invoice quantity must be greater than zero."})
    line = SalesInvoiceLine(
        sales_invoice=invoice,
        source_sales_order_line=source,
        source_sales_delivery_line=delivery_line,
        line_number=_next_line_number(invoice),
        item=source.item,
        source_sales_order_number_snapshot=source.sales_order.document_number,
        source_sales_delivery_number_snapshot=(
            delivery_line.sales_delivery.document_number if delivery_line is not None else ""
        ),
        item_code_snapshot=source.item_code_snapshot,
        item_name_snapshot=source.item_name_snapshot,
        description_snapshot=source.description_snapshot,
        uom_code_snapshot=source.uom_code_snapshot,
        quantity=qty,
        unit_price=source.unit_price,
        discount_type=source.discount_type,
        discount_value=source.discount_value,
        tax_classification_snapshot=source.tax_classification_snapshot,
        tax_rate=source.tax_rate,
        notes=str(notes or "").strip(),
    )
    _calculate_line(line)
    line.full_clean()
    line.save()
    _refresh_totals(invoice)
    invoice.full_clean()
    invoice.save()
    return line


@transaction.atomic
def add_draft_delivery_invoice_line(
    invoice: SalesInvoice, *, source_sales_delivery_line, quantity, actor=None, reason="", notes=""
) -> SalesInvoiceLine:
    invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk)
    _assert_draft(invoice)
    if invoice.source_mode != InvoiceSourceMode.DELIVERY:
        raise ValidationError("This invoice does not accept delivery source lines.")
    source_delivery = SalesDeliveryLine.objects.select_related(
        "sales_delivery", "source_sales_order_line__sales_order", "source_sales_order_line__item"
    ).get(pk=source_sales_delivery_line.pk)
    if source_delivery.sales_delivery.state != SalesDeliveryState.POSTED:
        raise ValidationError("Only POSTED delivery lines can be invoiced.")
    _validate_order_line(invoice, source_delivery.source_sales_order_line)
    before = model_snapshot(invoice)
    line = _add_line(
        invoice,
        source=source_delivery.source_sales_order_line,
        quantity=quantity,
        delivery_line=source_delivery,
        notes=notes,
    )
    _audit(
        invoice,
        action="sales.salesinvoice.delivery_line_added",
        actor=actor,
        reason=reason,
        before=before,
        metadata={"line_id": str(line.pk), "source_delivery_line_id": str(source_delivery.pk)},
    )
    return line


@transaction.atomic
def add_draft_sales_order_invoice_line(
    invoice: SalesInvoice, *, source_sales_order_line, quantity, actor=None, reason="", notes=""
) -> SalesInvoiceLine:
    invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk)
    _assert_draft(invoice)
    if invoice.source_mode != InvoiceSourceMode.SALES_ORDER:
        raise ValidationError("This invoice does not accept Sales Order source lines.")
    source = SalesOrderLine.objects.select_related("sales_order", "item").get(
        pk=source_sales_order_line.pk
    )
    _validate_order_line(invoice, source)
    before = model_snapshot(invoice)
    line = _add_line(invoice, source=source, quantity=quantity, notes=notes)
    _audit(
        invoice,
        action="sales.salesinvoice.sales_order_line_added",
        actor=actor,
        reason=reason,
        before=before,
        metadata={"line_id": str(line.pk), "source_sales_order_line_id": str(source.pk)},
    )
    return line


@transaction.atomic
def update_draft_invoice_line(
    line: SalesInvoiceLine, *, quantity, actor=None, reason="", notes=""
) -> SalesInvoiceLine:
    line = (
        SalesInvoiceLine.objects.select_for_update().select_related("sales_invoice").get(pk=line.pk)
    )
    _assert_draft(line.sales_invoice)
    before = model_snapshot(line)
    line.quantity = _quantity(quantity)
    line.notes = str(notes or "").strip()
    _calculate_line(line)
    line.full_clean()
    line.save()
    _refresh_totals(line.sales_invoice)
    line.sales_invoice.full_clean()
    line.sales_invoice.save()
    _audit(line, action="sales.salesinvoiceline.updated", actor=actor, reason=reason, before=before)
    return line


@transaction.atomic
def remove_draft_invoice_line(line: SalesInvoiceLine, *, actor=None, reason=""):
    line = (
        SalesInvoiceLine.objects.select_for_update().select_related("sales_invoice").get(pk=line.pk)
    )
    invoice = line.sales_invoice
    _assert_draft(invoice)
    before = model_snapshot(line)
    line.delete()
    _refresh_totals(invoice)
    invoice.full_clean()
    invoice.save()
    _audit(
        invoice,
        action="sales.salesinvoice.line_removed",
        actor=actor,
        reason=reason,
        metadata={"deleted_line": before},
    )


@transaction.atomic
def update_draft_invoice(invoice: SalesInvoice, *, actor=None, reason="", **values) -> SalesInvoice:
    invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk)
    _assert_draft(invoice)
    before = model_snapshot(invoice)
    if "invoice_date" in values and values["invoice_date"] != invoice.invoice_date:
        raise ValidationError(
            {"invoice_date": "Invoice date is immutable after number allocation."}
        )
    for field in ("currency", "notes", "freight_amount"):
        if field in values:
            setattr(invoice, field, values[field])
    invoice.currency = _text(invoice.currency).upper()
    invoice.freight_amount = _money(invoice.freight_amount)
    _refresh_totals(invoice)
    invoice.full_clean()
    invoice.save()
    _audit(invoice, action="sales.salesinvoice.updated", actor=actor, reason=reason, before=before)
    return invoice


def _confirmed_invoice_quantity(
    *, order_line_id=None, delivery_line_id=None, exclude_invoice_id=None
):
    queryset = SalesInvoiceLine.objects.filter(
        sales_invoice__state=SalesInvoiceState.CONFIRMED,
        sales_invoice__document_kind=SalesInvoiceDocumentKind.INVOICE,
    )
    if order_line_id is not None:
        queryset = queryset.filter(source_sales_order_line_id=order_line_id)
    if delivery_line_id is not None:
        queryset = queryset.filter(source_sales_delivery_line_id=delivery_line_id)
    if exclude_invoice_id is not None:
        queryset = queryset.exclude(sales_invoice_id=exclude_invoice_id)
    return queryset.aggregate(total=Sum("quantity"))["total"] or Decimal("0")


@transaction.atomic
def confirm_invoice(invoice: SalesInvoice, *, actor=None, idempotency_key="") -> SalesInvoice:
    invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.state == SalesInvoiceState.CONFIRMED:
        return invoice
    _assert_draft(invoice)
    lines = list(
        invoice.lines.select_related(
            "source_sales_order_line__sales_order", "source_sales_delivery_line__sales_delivery"
        ).order_by("line_number")
    )
    if not lines:
        raise ValidationError("An invoice source requires at least one line before confirmation.")
    order_ids = sorted({line.source_sales_order_line_id for line in lines}, key=str)
    order_lines = {
        source.pk: source
        for source in SalesOrderLine.objects.select_for_update()
        .select_related("sales_order")
        .filter(pk__in=order_ids)
    }
    delivery_ids = sorted(
        {
            line.source_sales_delivery_line_id
            for line in lines
            if line.source_sales_delivery_line_id
        },
        key=str,
    )
    delivery_lines = {
        source.pk: source
        for source in SalesDeliveryLine.objects.select_for_update()
        .select_related("sales_delivery")
        .filter(pk__in=delivery_ids)
    }
    for line in lines:
        order_line = order_lines[line.source_sales_order_line_id]
        _validate_order_line(invoice, order_line)
        if invoice.source_mode == InvoiceSourceMode.DELIVERY:
            if line.source_sales_delivery_line_id is None:
                raise ValidationError("Delivery-based invoice lines require delivery lineage.")
            delivery_line = delivery_lines[line.source_sales_delivery_line_id]
            if delivery_line.sales_delivery.state != SalesDeliveryState.POSTED:
                raise ValidationError("Only POSTED delivery lines can be invoiced.")
            if delivery_line.source_sales_order_line_id != order_line.pk:
                raise ValidationError(
                    "Invoice delivery lineage does not match the Sales Order line."
                )
            available = delivery_line.quantity - _confirmed_invoice_quantity(
                delivery_line_id=delivery_line.pk, exclude_invoice_id=invoice.pk
            )
        else:
            if line.source_sales_delivery_line_id is not None:
                raise ValidationError("Sales Order invoice lines cannot carry delivery lineage.")
            available = order_line.quantity - _confirmed_invoice_quantity(
                order_line_id=order_line.pk, exclude_invoice_id=invoice.pk
            )
        if line.quantity > available:
            raise ValidationError(
                "Invoice quantity exceeds the remaining eligible source quantity."
            )
    if idempotency_key:
        claim = claim_idempotency(
            namespace="sales.invoice.confirm",
            key=idempotency_key,
            payload={"sales_invoice_id": str(invoice.pk)},
            actor=actor,
        )
        if not claim.is_new:
            if claim.record.status == IdempotencyStatus.COMPLETED:
                return invoice
            raise ValidationError("A prior invoice confirmation request is still in progress.")
    else:
        claim = None
    before = model_snapshot(invoice)
    invoice.state = SalesInvoiceState.CONFIRMED
    invoice.confirmed_by = actor
    invoice.confirmed_at = timezone.now()
    invoice.full_clean()
    invoice.save(update_fields=("state", "confirmed_by", "confirmed_at", "updated_at"))
    _audit(
        invoice,
        action="sales.salesinvoice.confirmed",
        actor=actor,
        before=before,
        metadata={"finance_candidate": invoice.document_kind == SalesInvoiceDocumentKind.INVOICE},
    )
    if claim:
        complete_idempotency(
            claim.record.pk,
            result_reference=str(invoice.pk),
            response={"sales_invoice_id": str(invoice.pk)},
        )
    return invoice


@transaction.atomic
def cancel_invoice(invoice: SalesInvoice, *, actor=None, reason="") -> SalesInvoice:
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Cancellation reason is required."})
    invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.state not in {SalesInvoiceState.DRAFT, SalesInvoiceState.CONFIRMED}:
        raise ValidationError("Only DRAFT or CONFIRMED invoice sources can be cancelled.")
    before = model_snapshot(invoice)
    invoice.state = SalesInvoiceState.CANCELLED
    invoice.cancelled_by = actor
    invoice.cancelled_at = timezone.now()
    invoice.full_clean()
    invoice.save(update_fields=("state", "cancelled_by", "cancelled_at", "updated_at"))
    _audit(
        invoice,
        action="sales.salesinvoice.cancelled",
        actor=actor,
        reason=reason,
        before=before,
    )
    return invoice
