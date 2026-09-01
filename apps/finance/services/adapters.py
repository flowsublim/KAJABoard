"""Finance adapters for approved Phase 8A source contracts only."""

from django.core.exceptions import ValidationError

from apps.finance.services.posting import post_journal


def post_sales_invoice(invoice, *, actor):
    if invoice.state != "CONFIRMED" or invoice.document_kind != "INVOICE":
        raise ValidationError("Sales invoice is not an eligible Finance source.")
    amount = invoice.grand_total
    return post_journal(
        legal_entity=invoice.legal_entity,
        source_key=f"SALES_INVOICE|{invoice.pk}",
        source_module="SALES",
        source_document_type="SalesInvoice",
        source_document_id=invoice.pk,
        event_code="SALES_INVOICE",
        accounting_date=invoice.invoice_date,
        lines=[
            {"line_role": "AR_CONTROL", "dc": "DEBIT", "amount": amount},
            {"line_role": "REVENUE", "dc": "CREDIT", "amount": amount},
        ],
        actor=actor,
        source_reference={"invoice_number": invoice.document_number},
        ar={"amount": amount, "currency": invoice.currency, "partner": invoice.customer},
    )


def post_omni_completion(event, *, actor):
    from apps.omnichannel.services.phase7b import revenue_finance_candidate

    candidate = revenue_finance_candidate(event)
    amount = candidate["gross_revenue"]
    if amount is None:
        raise ValidationError("PENDING_SOURCE: completed revenue amount is unavailable.")
    return post_journal(
        legal_entity=event.legal_entity,
        source_key=f"OMNI_COMPLETION|{event.pk}",
        source_module="OMNI",
        source_document_type="OmniRevenueEvent",
        source_document_id=event.pk,
        event_code=candidate["event_code"],
        accounting_date=event.completion_date,
        lines=[
            {
                "line_role": "RECEIVABLE",
                "dc": "DEBIT",
                "amount": amount,
                "context": candidate["mapping_context"],
            },
            {
                "line_role": "REVENUE",
                "dc": "CREDIT",
                "amount": amount,
                "context": candidate["mapping_context"],
            },
        ],
        actor=actor,
        source_reference=candidate["source_lineage"],
        ar={"amount": amount, "currency": event.currency, "store": event.store},
    )
