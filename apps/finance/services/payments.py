"""Explicit Finance-owned receipt, disbursement, and payment reversal services."""

from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.finance.models import (
    JournalState,
    LiquidityAccount,
    LiquidityDirection,
    LiquidityEntry,
    PayableEntry,
    Payment,
    PaymentAllocation,
    PaymentDirection,
    PaymentState,
    ReceivableEntry,
)
from apps.finance.services.liquidity import liquidity_mapping_context
from apps.finance.services.posting import post_journal, reverse_journal
from apps.finance.services.wage_payables import wage_payable_control_snapshot


def _whole_rupiah(value, *, field):
    amount = Decimal(str(value))
    if amount <= 0 or amount != amount.to_integral_value():
        raise ValidationError({field: "Amount must be a positive whole Rupiah value."})
    return amount


def _validate_liquidity_account(liquidity_account, *, legal_entity, payment_date):
    account = LiquidityAccount.objects.select_for_update().get(pk=liquidity_account.pk)
    if account.legal_entity_id != legal_entity.pk:
        raise ValidationError("Liquidity account must belong to the payment legal entity.")
    if not account.is_active or not account.is_effective_on(payment_date):
        raise ValidationError("Liquidity account is not active/effective on the payment date.")
    return account


def _allocation_total(allocations):
    return sum((row["amount"] for row in allocations), Decimal("0"))


def _target_context(target):
    store = getattr(target, "store", None)
    if store and (store.finance_dimension or store.revenue_mapping_key):
        return {"STORE": store.finance_dimension or store.revenue_mapping_key}
    return {}


def _locked_allocations(*, allocations, model, target_name, legal_entity, currency):
    requested = []
    seen = set()
    for row in allocations:
        target = row.get(target_name)
        if target is None:
            raise ValidationError({target_name: "An allocation target is required."})
        if target.pk in seen:
            raise ValidationError({target_name: "Duplicate allocation target is not allowed."})
        seen.add(target.pk)
        requested.append((target.pk, _whole_rupiah(row.get("amount"), field="amount"), row))
    if not requested:
        raise ValidationError("At least one payment allocation is required.")
    locked = {
        target.pk: target
        for target in model.objects.select_for_update()
        .select_related("journal", "partner", "store" if model is ReceivableEntry else "journal")
        .filter(pk__in=[target_id for target_id, _, _ in requested])
    }
    if len(locked) != len(requested):
        raise ValidationError("An allocation target is no longer available.")
    result = []
    for target_id, amount, raw in requested:
        target = locked[target_id]
        if target.legal_entity_id != legal_entity.pk:
            raise ValidationError("Allocation target must belong to the payment legal entity.")
        if target.currency != currency:
            raise ValidationError("Allocation target currency must match the payment currency.")
        if target.journal.state != JournalState.POSTED:
            raise ValidationError("Allocation target must be backed by a posted journal.")
        if target.open_amount < amount:
            raise ValidationError("Payment allocation exceeds the target open amount.")
        result.append((target, amount, raw))
    return result


def _payment_party(locked_allocations, *, attribute):
    values = {getattr(target, attribute + "_id", None) for target, _, _ in locked_allocations}
    values.discard(None)
    return getattr(locked_allocations[0][0], attribute) if len(values) == 1 else None


@transaction.atomic
def post_customer_receipt(
    *,
    legal_entity,
    liquidity_account,
    allocations,
    payment_date,
    source_key,
    actor,
    currency="IDR",
    source_module="FINANCE",
    source_document_type="CustomerReceipt",
    source_document_id="",
    source_reference=None,
    partner=None,
    store=None,
):
    existing = (
        Payment.objects.select_for_update()
        .filter(legal_entity=legal_entity, source_key=source_key)
        .first()
    )
    if existing:
        return existing
    account = _validate_liquidity_account(
        liquidity_account, legal_entity=legal_entity, payment_date=payment_date
    )
    if account.currency != currency:
        raise ValidationError("Payment currency must match the liquidity account currency.")
    locked = _locked_allocations(
        allocations=allocations,
        model=ReceivableEntry,
        target_name="receivable",
        legal_entity=legal_entity,
        currency=currency,
    )
    amount = _allocation_total([{"amount": row_amount} for _, row_amount, _ in locked])
    lines = [
        {
            "line_role": "LIQUIDITY",
            "dc": "DEBIT",
            "amount": amount,
            "context": liquidity_mapping_context(account),
        }
    ]
    lines.extend(
        {
            "line_role": "RECEIVABLE",
            "dc": "CREDIT",
            "amount": allocation_amount,
            "context": _target_context(receivable),
        }
        for receivable, allocation_amount, _ in locked
    )
    journal = post_journal(
        legal_entity=legal_entity,
        source_key=f"PAYMENT|{source_key}",
        source_module="FINANCE",
        source_document_type=source_document_type,
        source_document_id=source_document_id or source_key,
        event_code="CUSTOMER_PAYMENT",
        accounting_date=payment_date,
        lines=lines,
        actor=actor,
        source_reference=source_reference or {},
        description="Customer receipt",
    )
    entry = LiquidityEntry.objects.create(
        legal_entity=legal_entity,
        liquidity_account=account,
        journal=journal,
        transaction_date=payment_date,
        direction=LiquidityDirection.IN,
        amount=amount,
        currency=currency,
        source_module=source_module,
        source_document_type=source_document_type,
        source_document_id=source_document_id or source_key,
        source_key=f"PAYMENT_LIQUIDITY|{source_key}",
        source_reference=source_reference or {},
        posted_by=actor,
        posted_at=timezone.now(),
    )
    payment = Payment.objects.create(
        legal_entity=legal_entity,
        payment_number=f"PAY-{uuid4().hex[:12].upper()}",
        payment_date=payment_date,
        direction=PaymentDirection.RECEIPT,
        liquidity_account=account,
        amount=amount,
        currency=currency,
        partner=partner or _payment_party(locked, attribute="partner"),
        store=store or _payment_party(locked, attribute="store"),
        source_module=source_module,
        source_document_type=source_document_type,
        source_document_id=source_document_id or source_key,
        source_key=source_key,
        source_reference=source_reference or {},
        journal=journal,
        liquidity_entry=entry,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    for receivable, allocation_amount, raw in locked:
        PaymentAllocation.objects.create(
            payment=payment,
            receivable=receivable,
            amount=allocation_amount,
            metadata=raw.get("metadata", {}),
        )
        receivable.open_amount -= allocation_amount
        receivable.save(update_fields=("open_amount", "updated_at"))
    return payment


@transaction.atomic
def post_vendor_payment(
    *,
    legal_entity,
    liquidity_account,
    allocations,
    payment_date,
    source_key,
    actor,
    currency="IDR",
    source_module="FINANCE",
    source_document_type="VendorPayment",
    source_document_id="",
    source_reference=None,
    partner=None,
):
    existing = (
        Payment.objects.select_for_update()
        .filter(legal_entity=legal_entity, source_key=source_key)
        .first()
    )
    if existing:
        return existing
    account = _validate_liquidity_account(
        liquidity_account, legal_entity=legal_entity, payment_date=payment_date
    )
    if account.currency != currency:
        raise ValidationError("Payment currency must match the liquidity account currency.")
    locked = _locked_allocations(
        allocations=allocations,
        model=PayableEntry,
        target_name="payable",
        legal_entity=legal_entity,
        currency=currency,
    )
    amount = _allocation_total([{"amount": row_amount} for _, row_amount, _ in locked])
    lines = []
    for payable, allocation_amount, _ in locked:
        if hasattr(payable, "wage_accrual"):
            lines.append(
                {
                    "line_role": "WAGE_PAYABLE",
                    "dc": "DEBIT",
                    "amount": allocation_amount,
                    "mapping_snapshot_override": wage_payable_control_snapshot(payable),
                }
            )
        else:
            lines.append({"line_role": "PAYABLE", "dc": "DEBIT", "amount": allocation_amount})
    lines.append(
        {
            "line_role": "LIQUIDITY",
            "dc": "CREDIT",
            "amount": amount,
            "context": liquidity_mapping_context(account),
        }
    )
    journal = post_journal(
        legal_entity=legal_entity,
        source_key=f"PAYMENT|{source_key}",
        source_module="FINANCE",
        source_document_type=source_document_type,
        source_document_id=source_document_id or source_key,
        event_code="VENDOR_PAYMENT",
        accounting_date=payment_date,
        lines=lines,
        actor=actor,
        source_reference=source_reference or {},
        description="Vendor payment",
    )
    entry = LiquidityEntry.objects.create(
        legal_entity=legal_entity,
        liquidity_account=account,
        journal=journal,
        transaction_date=payment_date,
        direction=LiquidityDirection.OUT,
        amount=amount,
        currency=currency,
        source_module=source_module,
        source_document_type=source_document_type,
        source_document_id=source_document_id or source_key,
        source_key=f"PAYMENT_LIQUIDITY|{source_key}",
        source_reference=source_reference or {},
        posted_by=actor,
        posted_at=timezone.now(),
    )
    payment = Payment.objects.create(
        legal_entity=legal_entity,
        payment_number=f"PAY-{uuid4().hex[:12].upper()}",
        payment_date=payment_date,
        direction=PaymentDirection.DISBURSEMENT,
        liquidity_account=account,
        amount=amount,
        currency=currency,
        partner=partner or _payment_party(locked, attribute="partner"),
        source_module=source_module,
        source_document_type=source_document_type,
        source_document_id=source_document_id or source_key,
        source_key=source_key,
        source_reference=source_reference or {},
        journal=journal,
        liquidity_entry=entry,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    for payable, allocation_amount, raw in locked:
        PaymentAllocation.objects.create(
            payment=payment,
            payable=payable,
            amount=allocation_amount,
            metadata=raw.get("metadata", {}),
        )
        payable.open_amount -= allocation_amount
        payable.save(update_fields=("open_amount", "updated_at"))
    return payment


@transaction.atomic
def reverse_payment(payment, *, actor):
    payment = (
        Payment.objects.select_for_update()
        .select_related("journal", "liquidity_entry", "liquidity_account")
        .prefetch_related("allocations")
        .get(pk=payment.pk)
    )
    if hasattr(payment, "reversal"):
        return payment.reversal
    allocations = list(payment.allocations.select_related("receivable", "payable"))
    receivable_ids = [row.receivable_id for row in allocations if row.receivable_id]
    payable_ids = [row.payable_id for row in allocations if row.payable_id]
    receivables = {
        row.pk: row
        for row in ReceivableEntry.objects.select_for_update().filter(pk__in=receivable_ids)
    }
    payables = {
        row.pk: row for row in PayableEntry.objects.select_for_update().filter(pk__in=payable_ids)
    }
    journal = reverse_journal(
        payment.journal,
        actor=actor,
        source_key=f"PAYMENT_JOURNAL_REVERSAL|{payment.pk}",
    )
    direction = (
        LiquidityDirection.OUT
        if payment.liquidity_entry.direction == LiquidityDirection.IN
        else LiquidityDirection.IN
    )
    entry = LiquidityEntry.objects.create(
        legal_entity=payment.legal_entity,
        liquidity_account=payment.liquidity_account,
        journal=journal,
        transaction_date=payment.payment_date,
        direction=direction,
        amount=payment.amount,
        currency=payment.currency,
        source_module="FINANCE",
        source_document_type="PaymentReversal",
        source_document_id=str(payment.pk),
        source_key=f"PAYMENT_LIQUIDITY_REVERSAL|{payment.pk}",
        source_reference={"reversal_of_payment_id": str(payment.pk)},
        reversal_of=payment.liquidity_entry,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    reversal = Payment.objects.create(
        legal_entity=payment.legal_entity,
        payment_number=f"PAYREV-{uuid4().hex[:10].upper()}",
        payment_date=payment.payment_date,
        direction=(
            PaymentDirection.DISBURSEMENT
            if payment.direction == PaymentDirection.RECEIPT
            else PaymentDirection.RECEIPT
        ),
        liquidity_account=payment.liquidity_account,
        amount=payment.amount,
        currency=payment.currency,
        partner=payment.partner,
        store=payment.store,
        source_module="FINANCE",
        source_document_type="PaymentReversal",
        source_document_id=str(payment.pk),
        source_key=f"PAYMENT_REVERSAL|{payment.pk}",
        source_reference={"reversal_of_payment_id": str(payment.pk)},
        journal=journal,
        liquidity_entry=entry,
        reversal_of=payment,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    for allocation in allocations:
        target = (
            receivables[allocation.receivable_id]
            if allocation.receivable_id
            else payables[allocation.payable_id]
        )
        target.open_amount += allocation.amount
        target.save(update_fields=("open_amount", "updated_at"))
    payment.state = PaymentState.REVERSED
    payment.save(update_fields=("state", "updated_at"))
    return reversal
