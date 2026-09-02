"""Finance consumption of durable POS sources; POS and Warehouse remain source owners."""

from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.finance.models import (
    LiquidityAccountType,
    LiquidityDirection,
    LiquidityEntry,
    Payment,
    PaymentDirection,
)
from apps.finance.services.liquidity import liquidity_mapping_context
from apps.finance.services.payments import (
    _validate_liquidity_account,
    _whole_rupiah,
    reverse_payment,
)
from apps.finance.services.posting import post_journal
from apps.omnichannel.models import (
    PosCashSessionState,
    PosFinanceSource,
    PosFinanceSourceState,
    PosSale,
    PosSaleState,
    PosTenderMethod,
)

POS_REVENUE_EVENT = "POS_SALE_REVENUE"
POS_TENDER_EVENT = "POS_TENDER"
POS_REVERSAL_EVENT = "POS_REVERSAL"
POS_REFUND_EVENT = "POS_REFUND"
POS_CASH_VARIANCE_EVENT = "POS_CASH_VARIANCE"


def _store_context(store):
    dimension = store.finance_dimension or store.revenue_mapping_key
    if not dimension:
        raise ValidationError("BLOCKED_MAPPING: POS Store has no Finance mapping dimension.")
    return {"STORE": dimension}


def _payment_method_context(method):
    return {"PAYMENT_METHOD": method}


def _pos_context(*, store, liquidity_account, payment_method):
    return {
        **_store_context(store),
        **liquidity_mapping_context(liquidity_account),
        **_payment_method_context(payment_method),
    }


def _validate_tender_account(*, tender, liquidity_account):
    if tender.method == PosTenderMethod.CASH:
        if liquidity_account.account_type != LiquidityAccountType.CASH:
            raise ValidationError("CASH POS tender requires a CASH liquidity account.")
        return
    if tender.method in {PosTenderMethod.QRIS, PosTenderMethod.OTHER}:
        if liquidity_account.account_type != LiquidityAccountType.BANK:
            raise ValidationError("QRIS/OTHER POS tender requires a BANK liquidity account.")
        return
    raise ValidationError("Unsupported POS tender method.")


def _active_source(*, sale, event_code):
    source = (
        PosFinanceSource.objects.select_for_update()
        .filter(sale=sale, event_code=event_code, state=PosFinanceSourceState.ACTIVE)
        .first()
    )
    if source is None:
        raise ValidationError(f"PENDING_SOURCE: active {event_code} source is unavailable.")
    return source


def _post_pos_payment(
    *,
    legal_entity,
    liquidity_account,
    amount,
    payment_date,
    payment_direction,
    liquidity_direction,
    event_code,
    lines,
    source_key,
    source_document_type,
    source_document_id,
    source_reference,
    actor,
    store,
    currency,
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
        raise ValidationError("POS source currency must match the liquidity account currency.")
    amount = _whole_rupiah(amount, field="amount")
    journal = post_journal(
        legal_entity=legal_entity,
        source_key=f"PAYMENT|{source_key}",
        source_module="OMNI",
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        event_code=event_code,
        accounting_date=payment_date,
        lines=lines,
        actor=actor,
        source_reference=source_reference,
        description=event_code.replace("_", " ").title(),
    )
    entry = LiquidityEntry.objects.create(
        legal_entity=legal_entity,
        liquidity_account=account,
        journal=journal,
        transaction_date=payment_date,
        direction=liquidity_direction,
        amount=amount,
        currency=currency,
        source_module="OMNI",
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        source_key=f"PAYMENT_LIQUIDITY|{source_key}",
        source_reference=source_reference,
        posted_by=actor,
        posted_at=timezone.now(),
    )
    return Payment.objects.create(
        legal_entity=legal_entity,
        payment_number=f"PAY-{uuid4().hex[:12].upper()}",
        payment_date=payment_date,
        direction=payment_direction,
        liquidity_account=account,
        amount=amount,
        currency=currency,
        store=store,
        source_module="OMNI",
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        source_key=source_key,
        source_reference=source_reference,
        journal=journal,
        liquidity_entry=entry,
        posted_by=actor,
        posted_at=timezone.now(),
    )


@transaction.atomic
def post_pos_sale_finance(sale, *, liquidity_account, actor):
    sale = (
        PosSale.objects.select_for_update()
        .select_related("legal_entity", "store", "tender")
        .get(pk=sale.pk)
    )
    source_key = f"POS_PAYMENT|{sale.pk}"
    existing = (
        Payment.objects.select_for_update()
        .filter(legal_entity=sale.legal_entity, source_key=source_key)
        .first()
    )
    if existing:
        return existing
    if sale.state != PosSaleState.POSTED:
        raise ValidationError("Only POSTED POS sales are eligible for Finance receipt posting.")
    tender = sale.tender
    if tender.amount != sale.grand_total_amount:
        raise ValidationError("POS tender amount must equal the posted POS sale amount.")
    account = _validate_liquidity_account(
        liquidity_account, legal_entity=sale.legal_entity, payment_date=sale.transaction_date
    )
    _validate_tender_account(tender=tender, liquidity_account=account)
    amount = _whole_rupiah(sale.grand_total_amount, field="sale_amount")
    revenue = _active_source(sale=sale, event_code=POS_REVENUE_EVENT)
    tender_source = _active_source(sale=sale, event_code=POS_TENDER_EVENT)
    if revenue.amount != amount or tender_source.amount != amount:
        raise ValidationError("PENDING_SOURCE: POS revenue/tender source amount is inconsistent.")
    context = _pos_context(
        store=sale.store, liquidity_account=account, payment_method=tender.method
    )
    source_reference = {
        "pos_sale_id": str(sale.pk),
        "pos_tender_id": str(tender.pk),
        "pos_finance_source_ids": [str(revenue.pk), str(tender_source.pk)],
        "tender_method": tender.method,
        "tender_reference": tender.method_reference,
    }
    return _post_pos_payment(
        legal_entity=sale.legal_entity,
        liquidity_account=account,
        amount=amount,
        payment_date=sale.transaction_date,
        payment_direction=PaymentDirection.RECEIPT,
        liquidity_direction=LiquidityDirection.IN,
        event_code=POS_REVENUE_EVENT,
        lines=(
            {"line_role": "LIQUIDITY", "dc": "DEBIT", "amount": amount, "context": context},
            {"line_role": "REVENUE", "dc": "CREDIT", "amount": amount, "context": context},
        ),
        source_key=source_key,
        source_document_type="PosSale",
        source_document_id=str(sale.pk),
        source_reference=source_reference,
        actor=actor,
        store=sale.store,
        currency=sale.currency,
    )


@transaction.atomic
def post_pos_refund_finance(source, *, liquidity_account, actor, payment_method=None):
    source = (
        PosFinanceSource.objects.select_for_update()
        .select_related("legal_entity", "store", "cash_session", "pos_return")
        .get(pk=source.pk)
    )
    source_key = f"POS_REFUND_PAYMENT|{source.pk}"
    existing = (
        Payment.objects.select_for_update()
        .filter(legal_entity=source.legal_entity, source_key=source_key)
        .first()
    )
    if existing:
        return existing
    if source.event_code != POS_REFUND_EVENT or source.state != PosFinanceSourceState.ACTIVE:
        raise ValidationError("Only active POS_REFUND sources are eligible for Finance posting.")
    if source.amount is None:
        raise ValidationError("PENDING_SOURCE: POS refund amount is unavailable.")
    account = _validate_liquidity_account(
        liquidity_account, legal_entity=source.legal_entity, payment_date=source.transaction_date
    )
    if source.cash_session_id:
        if source.cash_session.state != PosCashSessionState.OPEN:
            raise ValidationError("PENDING_SOURCE: POS cash refund session is not open.")
        payment_method = PosTenderMethod.CASH
    if payment_method not in {PosTenderMethod.CASH, PosTenderMethod.QRIS, PosTenderMethod.OTHER}:
        raise ValidationError("PENDING_SOURCE: POS refund payment method is unavailable.")
    tender_proxy = type("TenderMethod", (), {"method": payment_method})()
    _validate_tender_account(tender=tender_proxy, liquidity_account=account)
    amount = _whole_rupiah(source.amount, field="refund_amount")
    context = _pos_context(
        store=source.store, liquidity_account=account, payment_method=payment_method
    )
    source_reference = {
        "pos_finance_source_id": str(source.pk),
        "pos_return_id": str(source.pos_return_id) if source.pos_return_id else None,
        "tender_method": payment_method,
    }
    return _post_pos_payment(
        legal_entity=source.legal_entity,
        liquidity_account=account,
        amount=amount,
        payment_date=source.transaction_date,
        payment_direction=PaymentDirection.DISBURSEMENT,
        liquidity_direction=LiquidityDirection.OUT,
        event_code=POS_REFUND_EVENT,
        lines=(
            {"line_role": "SALES_RETURN", "dc": "DEBIT", "amount": amount, "context": context},
            {"line_role": "LIQUIDITY", "dc": "CREDIT", "amount": amount, "context": context},
        ),
        source_key=source_key,
        source_document_type="PosFinanceSource",
        source_document_id=str(source.pk),
        source_reference=source_reference,
        actor=actor,
        store=source.store,
        currency=source.currency,
    )


@transaction.atomic
def reverse_pos_sale_finance(sale, *, actor):
    sale = PosSale.objects.select_for_update().get(pk=sale.pk)
    if sale.state != PosSaleState.REVERSED or not hasattr(sale, "reversal"):
        raise ValidationError("PENDING_SOURCE: POS sale reversal source is unavailable.")
    _active_source(sale=sale, event_code=POS_REVERSAL_EVENT)
    payment = Payment.objects.filter(
        legal_entity=sale.legal_entity, source_key=f"POS_PAYMENT|{sale.pk}"
    ).first()
    if payment is None:
        raise ValidationError("PENDING_SOURCE: original POS Finance receipt is unavailable.")
    return reverse_payment(payment, actor=actor)


@transaction.atomic
def post_pos_cash_variance_finance(source, *, liquidity_account, actor):
    source = (
        PosFinanceSource.objects.select_for_update()
        .select_related("legal_entity", "store", "cash_session")
        .get(pk=source.pk)
    )
    if source.event_code != POS_CASH_VARIANCE_EVENT or source.state != PosFinanceSourceState.ACTIVE:
        raise ValidationError(
            "Only active POS_CASH_VARIANCE sources are eligible for Finance posting."
        )
    if source.amount is None:
        raise ValidationError("PENDING_SOURCE: POS cash variance amount is unavailable.")
    if source.amount == Decimal("0"):
        return {"status": "NO_ACCOUNTING_EFFECT", "source_id": str(source.pk)}
    account = _validate_liquidity_account(
        liquidity_account, legal_entity=source.legal_entity, payment_date=source.transaction_date
    )
    if account.account_type != LiquidityAccountType.CASH:
        raise ValidationError("POS cash variance requires a CASH liquidity account.")
    if source.cash_session_id and source.cash_session.state != PosCashSessionState.CLOSED:
        raise ValidationError(
            "PENDING_SOURCE: POS cash session must be closed for variance posting."
        )
    amount = _whole_rupiah(abs(source.amount), field="variance_amount")
    source_key = f"POS_CASH_VARIANCE_ACCOUNTING|{source.pk}"
    existing = (
        LiquidityEntry.objects.select_for_update()
        .filter(legal_entity=source.legal_entity, source_key=source_key)
        .first()
    )
    if existing:
        return existing
    context = _pos_context(
        store=source.store, liquidity_account=account, payment_method=PosTenderMethod.CASH
    )
    overage = source.amount > Decimal("0")
    journal = post_journal(
        legal_entity=source.legal_entity,
        source_key=source_key,
        source_module="OMNI",
        source_document_type="PosFinanceSource",
        source_document_id=str(source.pk),
        event_code=POS_CASH_VARIANCE_EVENT,
        accounting_date=source.transaction_date,
        lines=(
            {
                "line_role": "LIQUIDITY" if overage else "CASH_VARIANCE",
                "dc": "DEBIT",
                "amount": amount,
                "context": context,
            },
            {
                "line_role": "CASH_VARIANCE" if overage else "LIQUIDITY",
                "dc": "CREDIT",
                "amount": amount,
                "context": context,
            },
        ),
        actor=actor,
        source_reference={
            "pos_finance_source_id": str(source.pk),
            "cash_session_id": str(source.cash_session_id) if source.cash_session_id else None,
        },
        description="POS cash variance",
    )
    return LiquidityEntry.objects.create(
        legal_entity=source.legal_entity,
        liquidity_account=account,
        journal=journal,
        transaction_date=source.transaction_date,
        direction=LiquidityDirection.IN if overage else LiquidityDirection.OUT,
        amount=amount,
        currency=source.currency,
        source_module="OMNI",
        source_document_type="PosFinanceSource",
        source_document_id=str(source.pk),
        source_key=source_key,
        source_reference={"pos_finance_source_id": str(source.pk)},
        posted_by=actor,
        posted_at=timezone.now(),
    )
