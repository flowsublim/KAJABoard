"""Phase 7C POS source services.

POS owns its documents, tenders, source candidates, and cash-session control.
Warehouse owns every physical movement; Finance owns all ledger posting.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Item
from apps.core.services.audit import record_audit_event
from apps.finance.models import DCDirection
from apps.finance.services import FinanceMappingError, resolve_account_mapping
from apps.omnichannel.models import (
    PosCashSession,
    PosCashSessionState,
    PosFinanceSource,
    PosFinanceSourceState,
    PosReturn,
    PosReturnLine,
    PosReturnState,
    PosSale,
    PosSaleLine,
    PosSaleReversal,
    PosSaleState,
    PosTender,
    PosTenderMethod,
)
from apps.warehouse.models import MovementDirection, MovementType, ValuationStatus
from apps.warehouse.services import post_stock_movement

POS_REVENUE_EVENT = "POS_SALE_REVENUE"
POS_COGS_EVENT = "POS_COGS"
POS_TENDER_EVENT = "POS_TENDER"
POS_REVERSAL_EVENT = "POS_REVERSAL"
POS_RETURN_EVENT = "POS_RETURN"
POS_REFUND_EVENT = "POS_REFUND"
POS_CASH_VARIANCE_EVENT = "POS_CASH_VARIANCE"

ZERO = Decimal("0")


def _decimal(value, field, *, nonnegative=False, positive=False):
    try:
        parsed = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError) as error:
        raise ValidationError({field: "Value must be numeric."}) from error
    if positive and parsed <= ZERO:
        raise ValidationError({field: "Value must be greater than zero."})
    if nonnegative and parsed < ZERO:
        raise ValidationError({field: "Value cannot be negative."})
    return parsed


def _transaction_at(value):
    if value is None:
        return timezone.now()
    if isinstance(value, datetime):
        return timezone.make_aware(value) if timezone.is_naive(value) else value
    raise ValidationError({"transaction_at": "A transaction datetime is required."})


def _is_effective(instance, business_date):
    return instance.effective_from <= business_date and (
        instance.effective_to is None or instance.effective_to >= business_date
    )


def _validate_store(store, legal_entity, business_date):
    if (
        store.legal_entity_id != legal_entity.pk
        or not store.is_active
        or not _is_effective(store, business_date)
    ):
        raise ValidationError("Store must be active and effective for the POS transaction date.")


def _validate_item(item, legal_entity, business_date):
    if not isinstance(item, Item):
        raise ValidationError("POS line requires a canonical Item instance.")
    if (
        item.legal_entity_id != legal_entity.pk
        or not item.is_active
        or not item.sales_eligible
        or not item.inventory_eligible
        or not _is_effective(item, business_date)
    ):
        raise ValidationError(
            "POS Item must be active, sales eligible, inventory eligible, and effective."
        )


def _validate_warehouse(warehouse, legal_entity):
    if warehouse.legal_entity_id != legal_entity.pk or not warehouse.is_active:
        raise ValidationError("Warehouse must be active and belong to the POS legal entity.")


def _mapping_status(store, event_code, line_role, dc, business_date):
    if not (store.finance_dimension or store.revenue_mapping_key):
        return "BLOCKED_MAPPING"
    try:
        resolve_account_mapping(
            legal_entity=store.legal_entity,
            module_code="OMNI",
            event_code=event_code,
            line_role=line_role,
            dc=dc,
            business_date=business_date,
            context={"STORE": store.finance_dimension or store.revenue_mapping_key},
        )
    except FinanceMappingError:
        return "BLOCKED_MAPPING"
    return "READY"


def _audit(obj, action, actor=None, *, key="", metadata=None):
    record_audit_event(
        action=action,
        target_type=obj._meta.label_lower,
        target_id=obj.pk,
        actor=actor,
        source="omnichannel.phase7c",
        idempotency_key=key,
        metadata=metadata or {},
    )


def _candidate(
    *,
    legal_entity,
    store,
    event_code,
    transaction_date,
    source_key,
    amount,
    sale=None,
    sale_line=None,
    pos_return=None,
    cash_session=None,
    state=PosFinanceSourceState.ACTIVE,
    reversal_of=None,
    metadata=None,
):
    line_role, dc = {
        POS_REVENUE_EVENT: ("REVENUE", DCDirection.CREDIT),
        POS_COGS_EVENT: ("COGS", DCDirection.DEBIT),
        POS_TENDER_EVENT: ("TENDER", DCDirection.DEBIT),
        POS_REVERSAL_EVENT: ("REVERSAL", DCDirection.DEBIT),
        POS_RETURN_EVENT: ("RETURN", DCDirection.DEBIT),
        POS_REFUND_EVENT: ("REFUND", DCDirection.CREDIT),
        POS_CASH_VARIANCE_EVENT: ("CASH_VARIANCE", DCDirection.DEBIT),
    }[event_code]
    mapping_status = _mapping_status(store, event_code, line_role, dc, transaction_date)
    if state == PosFinanceSourceState.PENDING_VALUATION:
        mapping_status = "BLOCKED_MAPPING" if mapping_status != "READY" else mapping_status
    return PosFinanceSource.objects.create(
        legal_entity=legal_entity,
        store=store,
        sale=sale,
        sale_line=sale_line,
        pos_return=pos_return,
        cash_session=cash_session,
        event_code=event_code,
        transaction_date=transaction_date,
        amount=amount,
        mapping_status=mapping_status,
        source_key=source_key,
        state=state,
        reversal_of=reversal_of,
        metadata=metadata or {},
    )


@transaction.atomic
def open_pos_cash_session(*, legal_entity, store, opening_cash_amount, actor, source_key, notes=""):
    existing = PosCashSession.objects.filter(source_key=source_key).first()
    if existing:
        return existing
    _validate_store(store, legal_entity, timezone.localdate())
    session = PosCashSession.objects.create(
        legal_entity=legal_entity,
        store=store,
        opened_by=actor,
        opened_at=timezone.now(),
        opening_cash_amount=_decimal(opening_cash_amount, "opening_cash_amount", nonnegative=True),
        source_key=source_key,
        notes=str(notes or "").strip(),
    )
    _audit(session, "omnichannel.pos_cash_session.opened", actor, key=source_key)
    return session


@transaction.atomic
def create_pos_sale(
    *,
    legal_entity,
    store,
    warehouse,
    lines,
    tender,
    source_key,
    actor=None,
    transaction_at=None,
    discount_amount=ZERO,
    currency="IDR",
    notes="",
):
    """Create a DRAFT POS document using only explicit canonical Item lines."""

    existing = PosSale.objects.filter(source_key=source_key).first()
    if existing:
        return existing
    transaction_at = _transaction_at(transaction_at)
    transaction_date = transaction_at.date()
    _validate_store(store, legal_entity, transaction_date)
    _validate_warehouse(warehouse, legal_entity)
    if not lines:
        raise ValidationError("POS sale requires at least one line.")
    normalized_lines = []
    subtotal = ZERO
    for sequence, line in enumerate(lines, 1):
        item = line.get("item")
        _validate_item(item, legal_entity, transaction_date)
        quantity = _decimal(line.get("quantity"), "quantity", positive=True)
        unit_price = _decimal(line.get("unit_price_amount"), "unit_price_amount", nonnegative=True)
        amount = quantity * unit_price
        normalized_lines.append((sequence, item, quantity, unit_price, amount))
        subtotal += amount
    discount_amount = _decimal(discount_amount, "discount_amount", nonnegative=True)
    if discount_amount > subtotal:
        raise ValidationError("POS discount cannot exceed the sale subtotal.")
    grand_total = subtotal - discount_amount
    tender = dict(tender or {})
    method = str(tender.get("method") or "").upper()
    if method not in PosTenderMethod.values:
        raise ValidationError({"tender": "POS tender method is not configured."})
    if method == PosTenderMethod.OTHER and not str(tender.get("reference") or "").strip():
        raise ValidationError(
            {"tender": "Other POS tender requires its configured method reference."}
        )
    tender_amount = _decimal(tender.get("amount"), "tender_amount", nonnegative=True)
    if tender_amount != grand_total:
        raise ValidationError("The single POS tender must equal the payable grand total.")
    document_number = f"POS-{uuid4().hex[:12].upper()}"
    sale = PosSale.objects.create(
        legal_entity=legal_entity,
        document_number=document_number,
        store=store,
        warehouse=warehouse,
        transaction_at=transaction_at,
        transaction_date=transaction_date,
        currency=str(currency or "IDR").upper(),
        subtotal_amount=subtotal,
        discount_amount=discount_amount,
        grand_total_amount=grand_total,
        source_key=source_key,
        created_by=actor,
        notes=str(notes or "").strip(),
    )
    for sequence, item, quantity, unit_price, amount in normalized_lines:
        PosSaleLine.objects.create(
            sale=sale,
            item=item,
            item_code_snapshot=item.code,
            item_name_snapshot=item.name,
            uom_code_snapshot=item.uom.code,
            quantity=quantity,
            unit_price_amount=unit_price,
            line_amount=amount,
            source_key=f"POS_LINE|{sale.pk}|{sequence}",
            sequence=sequence,
        )
    PosTender.objects.create(
        sale=sale,
        method=method,
        method_reference=str(tender.get("reference") or "").strip(),
        amount=tender_amount,
        currency=sale.currency,
        transaction_at=transaction_at,
        cash_session=tender.get("cash_session"),
        source_key=f"POS_TENDER|{sale.pk}",
    )
    _audit(sale, "omnichannel.pos_sale.draft_created", actor, key=source_key)
    return sale


@transaction.atomic
def post_pos_sale(sale, *, actor=None, idempotency_key):
    """Atomically issue Warehouse stock and finalize POS source candidates."""

    sale = (
        PosSale.objects.select_for_update()
        .select_related("legal_entity", "store", "warehouse", "tender", "tender__cash_session")
        .get(pk=sale.pk)
    )
    if sale.state == PosSaleState.POSTED:
        if sale.idempotency_key == idempotency_key:
            return sale
        raise ValidationError("POS sale is already posted.")
    if sale.state != PosSaleState.DRAFT:
        raise ValidationError("Only DRAFT POS sales can be posted.")
    if not idempotency_key:
        raise ValidationError("Idempotency key is required to post a POS sale.")
    _validate_store(sale.store, sale.legal_entity, sale.transaction_date)
    _validate_warehouse(sale.warehouse, sale.legal_entity)
    tender = sale.tender
    if tender.amount != sale.grand_total_amount:
        raise ValidationError("POS tender no longer reconciles to the sale grand total.")
    if tender.method == PosTenderMethod.CASH:
        if tender.cash_session_id is None:
            raise ValidationError("Cash POS tender requires an open cash session.")
        session = PosCashSession.objects.select_for_update().get(pk=tender.cash_session_id)
        if (
            session.state != PosCashSessionState.OPEN
            or session.legal_entity_id != sale.legal_entity_id
            or session.store_id != sale.store_id
        ):
            raise ValidationError("Cash POS tender requires the Store's active open cash session.")
    elif tender.cash_session_id:
        raise ValidationError("Only cash POS tender may reference a cash session.")
    lines = list(
        sale.lines.select_for_update().select_related("item", "item__uom").order_by("sequence")
    )
    if not lines:
        raise ValidationError("POS sale requires at least one line.")
    movements = []
    for line in lines:
        _validate_item(line.item, sale.legal_entity, sale.transaction_date)
        movement = post_stock_movement(
            legal_entity=sale.legal_entity,
            warehouse=sale.warehouse,
            item=line.item,
            direction=MovementDirection.OUT,
            movement_type=MovementType.POS_SALE_ISSUE,
            quantity=line.quantity,
            source_module="omnichannel",
            source_type="POS_SALE",
            source_document_id=sale.pk,
            source_line_id=line.pk,
            source_key=f"POS_OUT|{line.pk}",
            transaction_date=sale.transaction_date,
            actor=actor,
            idempotency_key=f"{idempotency_key}|LINE|{line.pk}",
        )
        line.warehouse_movement = movement
        line.warehouse_unit_cost = movement.unit_cost
        line.cogs_amount = movement.total_value
        line.valuation_status = movement.valuation_status
        line.save(
            update_fields=(
                "warehouse_movement",
                "warehouse_unit_cost",
                "cogs_amount",
                "valuation_status",
                "updated_at",
            )
        )
        movements.append(movement)
    _candidate(
        legal_entity=sale.legal_entity,
        store=sale.store,
        sale=sale,
        event_code=POS_REVENUE_EVENT,
        transaction_date=sale.transaction_date,
        amount=sale.grand_total_amount,
        source_key=f"POS_REVENUE|{sale.pk}",
        metadata={"document_number": sale.document_number},
    )
    for line, movement in zip(lines, movements, strict=True):
        _candidate(
            legal_entity=sale.legal_entity,
            store=sale.store,
            sale=sale,
            sale_line=line,
            event_code=POS_COGS_EVENT,
            transaction_date=sale.transaction_date,
            amount=movement.total_value,
            source_key=f"POS_COGS|{line.pk}",
            state=(
                PosFinanceSourceState.ACTIVE
                if movement.valuation_status == ValuationStatus.READY
                else PosFinanceSourceState.PENDING_VALUATION
            ),
            metadata={
                "warehouse_movement_id": str(movement.pk),
                "unit_cost": str(movement.unit_cost),
            },
        )
    _candidate(
        legal_entity=sale.legal_entity,
        store=sale.store,
        sale=sale,
        cash_session=tender.cash_session,
        event_code=POS_TENDER_EVENT,
        transaction_date=sale.transaction_date,
        amount=tender.amount,
        source_key=f"POS_TENDER_CANDIDATE|{tender.pk}",
        metadata={"method": tender.method, "reference": tender.method_reference},
    )
    sale.state = PosSaleState.POSTED
    sale.idempotency_key = idempotency_key
    sale.posted_by = actor
    sale.posted_at = timezone.now()
    sale.save(update_fields=("state", "idempotency_key", "posted_by", "posted_at", "updated_at"))
    _audit(sale, "omnichannel.pos_sale.posted", actor, key=idempotency_key)
    return sale


@transaction.atomic
def cancel_pos_sale(sale, *, actor=None):
    sale = PosSale.objects.select_for_update().get(pk=sale.pk)
    if sale.state != PosSaleState.DRAFT:
        raise ValidationError("Only DRAFT POS sales can be cancelled.")
    sale.state = PosSaleState.CANCELLED
    sale.cancelled_by = actor
    sale.cancelled_at = timezone.now()
    sale.save(update_fields=("state", "cancelled_by", "cancelled_at", "updated_at"))
    _audit(sale, "omnichannel.pos_sale.cancelled", actor)
    return sale


@transaction.atomic
def reverse_pos_sale(sale, *, reason, actor=None, idempotency_key):
    if not str(reason or "").strip():
        raise ValidationError("A reason is required to reverse a POS sale.")
    if not idempotency_key:
        raise ValidationError("Idempotency key is required to reverse a POS sale.")
    sale = (
        PosSale.objects.select_for_update()
        .select_related("legal_entity", "store", "warehouse", "tender")
        .get(pk=sale.pk)
    )
    existing = PosSaleReversal.objects.filter(original_sale=sale).first()
    if existing:
        return existing
    if sale.state != PosSaleState.POSTED:
        raise ValidationError("Only POSTED POS sales can be reversed.")
    reversal = PosSaleReversal.objects.create(
        original_sale=sale,
        reversal_date=timezone.localdate(),
        reason=str(reason).strip(),
        source_key=f"POS_REVERSAL|{sale.pk}",
        idempotency_key=idempotency_key,
        created_by=actor,
    )
    for line in sale.lines.select_for_update().select_related("warehouse_movement", "item"):
        original = line.warehouse_movement
        if original is None:
            raise ValidationError("A posted POS line is missing its Warehouse issue lineage.")
        post_stock_movement(
            legal_entity=sale.legal_entity,
            warehouse=sale.warehouse,
            item=line.item,
            direction=MovementDirection.IN,
            movement_type=MovementType.POS_SALE_REVERSAL,
            quantity=line.quantity,
            source_module="omnichannel",
            source_type="POS_SALE_REVERSAL",
            source_document_id=reversal.pk,
            source_line_id=line.pk,
            source_key=f"POS_REVERSAL_IN|{reversal.pk}|{line.pk}",
            transaction_date=reversal.reversal_date,
            actor=actor,
            unit_cost=original.unit_cost,
            total_value=original.total_value,
            valuation_status=original.valuation_status,
            idempotency_key=f"{idempotency_key}|LINE|{line.pk}",
        )
    originals = list(
        sale.finance_sources.select_for_update().filter(state=PosFinanceSourceState.ACTIVE)
    )
    for original in originals:
        original.state = PosFinanceSourceState.REVERSED
        original.save(update_fields=("state", "updated_at"))
        _candidate(
            legal_entity=sale.legal_entity,
            store=sale.store,
            sale=sale,
            sale_line=original.sale_line,
            cash_session=original.cash_session,
            event_code=POS_REVERSAL_EVENT,
            transaction_date=reversal.reversal_date,
            amount=-original.amount if original.amount is not None else None,
            source_key=f"POS_REVERSAL_CANDIDATE|{reversal.pk}|{original.pk}",
            reversal_of=original,
            metadata={"original_event_code": original.event_code, "reversal_id": str(reversal.pk)},
        )
    sale.state = PosSaleState.REVERSED
    sale.save(update_fields=("state", "updated_at"))
    _audit(reversal, "omnichannel.pos_sale.reversed", actor, key=idempotency_key)
    return reversal


@transaction.atomic
def close_pos_cash_session(session, *, counted_cash_amount, actor, idempotency_key):
    session = PosCashSession.objects.select_for_update().get(pk=session.pk)
    if session.state == PosCashSessionState.CLOSED:
        if session.close_idempotency_key == idempotency_key:
            return session
        raise ValidationError("POS cash session is already closed.")
    if not idempotency_key:
        raise ValidationError("Idempotency key is required to close a cash session.")
    counted = _decimal(counted_cash_amount, "counted_cash_amount", nonnegative=True)
    cash_sales = PosTender.objects.filter(
        cash_session=session,
        method=PosTenderMethod.CASH,
        sale__state=PosSaleState.POSTED,
    )
    cash_sales_total = sum((tender.amount for tender in cash_sales), ZERO)
    cash_refunds_total = sum(
        (
            pos_return.refunded_amount
            for pos_return in PosReturn.objects.filter(
                cash_session=session, state=PosReturnState.RECORDED
            )
        ),
        ZERO,
    )
    expected = session.opening_cash_amount + cash_sales_total - cash_refunds_total
    session.state = PosCashSessionState.CLOSED
    session.closed_by = actor
    session.closed_at = timezone.now()
    session.expected_cash_amount = expected
    session.counted_cash_amount = counted
    session.variance_amount = counted - expected
    session.close_idempotency_key = idempotency_key
    session.save(
        update_fields=(
            "state",
            "closed_by",
            "closed_at",
            "expected_cash_amount",
            "counted_cash_amount",
            "variance_amount",
            "close_idempotency_key",
            "updated_at",
        )
    )
    _candidate(
        legal_entity=session.legal_entity,
        store=session.store,
        cash_session=session,
        event_code=POS_CASH_VARIANCE_EVENT,
        transaction_date=session.closed_at.date(),
        amount=session.variance_amount,
        source_key=f"POS_CASH_VARIANCE|{session.pk}",
        metadata={"expected": str(expected), "counted": str(counted)},
    )
    _audit(session, "omnichannel.pos_cash_session.closed", actor, key=idempotency_key)
    return session


@transaction.atomic
def create_pos_return(
    *,
    original_sale,
    lines,
    source_key,
    actor=None,
    return_at=None,
    refund_amount=None,
    cash_session=None,
    notes="",
):
    """Record a distinct POS return source without restoring stock."""

    existing = PosReturn.objects.filter(source_key=source_key).first()
    if existing:
        return existing
    sale = (
        PosSale.objects.select_for_update()
        .select_related("legal_entity", "store", "warehouse")
        .get(pk=original_sale.pk)
    )
    if sale.state != PosSaleState.POSTED:
        raise ValidationError("POS returns require an active POSTED original sale.")
    if not lines:
        raise ValidationError("POS return requires at least one original sale line.")
    return_at = _transaction_at(return_at)
    normalized = []
    for sequence, data in enumerate(lines, 1):
        sale_line = data.get("original_sale_line")
        if not isinstance(sale_line, PosSaleLine) or sale_line.sale_id != sale.pk:
            raise ValidationError(
                "POS return line must reference an original line of the posted sale."
            )
        quantity = _decimal(data.get("quantity"), "quantity", positive=True)
        already_returned = sum(
            (
                row.quantity
                for row in PosReturnLine.objects.select_for_update().filter(
                    original_sale_line=sale_line,
                    pos_return__state=PosReturnState.RECORDED,
                )
            ),
            ZERO,
        )
        if already_returned + quantity > sale_line.quantity:
            raise ValidationError("POS return quantity exceeds the original sold quantity.")
        normalized.append((sequence, sale_line, quantity, data.get("refund_amount")))
    if cash_session is not None:
        session = PosCashSession.objects.select_for_update().get(pk=cash_session.pk)
        if (
            session.state != PosCashSessionState.OPEN
            or session.store_id != sale.store_id
            or session.legal_entity_id != sale.legal_entity_id
        ):
            raise ValidationError("Cash refund source requires the Store's open cash session.")
    pos_return = PosReturn.objects.create(
        legal_entity=sale.legal_entity,
        document_number=f"POS-RET-{uuid4().hex[:12].upper()}",
        original_sale=sale,
        store=sale.store,
        warehouse=sale.warehouse,
        return_at=return_at,
        return_date=return_at.date(),
        refund_amount=(
            _decimal(refund_amount, "refund_amount", nonnegative=True)
            if refund_amount is not None
            else None
        ),
        cash_session=cash_session,
        source_key=source_key,
        created_by=actor,
        notes=str(notes or "").strip(),
    )
    for sequence, sale_line, quantity, line_refund in normalized:
        PosReturnLine.objects.create(
            pos_return=pos_return,
            original_sale_line=sale_line,
            item=sale_line.item,
            quantity=quantity,
            refund_amount=(
                _decimal(line_refund, "refund_amount", nonnegative=True)
                if line_refund is not None
                else None
            ),
            source_key=f"POS_RETURN_LINE|{pos_return.pk}|{sequence}",
            sequence=sequence,
        )
    _candidate(
        legal_entity=sale.legal_entity,
        store=sale.store,
        pos_return=pos_return,
        event_code=POS_RETURN_EVENT,
        transaction_date=pos_return.return_date,
        amount=None,
        source_key=f"POS_RETURN_CANDIDATE|{pos_return.pk}",
        metadata={"original_sale_id": str(sale.pk)},
    )
    _audit(pos_return, "omnichannel.pos_return.recorded", actor, key=source_key)
    return pos_return


@transaction.atomic
def create_pos_return_quality_candidate(return_line, *, actor=None):
    """Create a draft Quality candidate; it does not choose a disposition."""

    from apps.quality.models import InspectionType
    from apps.quality.services.quality import add_inspection_line, create_inspection

    line = (
        PosReturnLine.objects.select_for_update()
        .select_related("pos_return", "pos_return__legal_entity", "item")
        .get(pk=return_line.pk)
    )
    if line.pos_return.state != PosReturnState.RECORDED:
        raise ValidationError("Only recorded POS return lines can enter Quality.")
    if line.quality_inspection_line_id:
        return line.quality_inspection_line.inspection
    inspection = create_inspection(
        legal_entity=line.pos_return.legal_entity,
        inspection_type=InspectionType.CUSTOMER_RETURN,
        source_module="omnichannel",
        source_type="POS_RETURN",
        source_document_id=line.pos_return_id,
        source_key=f"QUALITY|POS_RETURN|{line.pk}",
        inspection_date=line.pos_return.return_date,
        warehouse=line.pos_return.warehouse,
        evidence_reference=line.source_key,
        evidence_metadata={"pos_return_line_id": str(line.pk)},
        actor=actor,
    )
    quality_line = add_inspection_line(
        inspection,
        source_line_id=str(line.pk),
        item=line.item,
        qty_presented=line.quantity,
        actor=actor,
    )
    line.quality_inspection_line = quality_line
    line.save(update_fields=("quality_inspection_line", "updated_at"))
    _audit(line, "omnichannel.pos_return_quality_candidate.created", actor)
    return inspection


@transaction.atomic
def record_pos_return_refund(
    pos_return, *, amount, line_quantities=None, actor=None, idempotency_key
):
    pos_return = (
        PosReturn.objects.select_for_update().select_related("cash_session").get(pk=pos_return.pk)
    )
    if pos_return.state != PosReturnState.RECORDED:
        raise ValidationError("Only recorded POS returns can have a refund source.")
    if not idempotency_key:
        raise ValidationError("Idempotency key is required for a POS refund source.")
    existing = PosFinanceSource.objects.filter(
        source_key=f"POS_REFUND|{pos_return.pk}|{idempotency_key}"
    ).first()
    if existing:
        return existing
    amount = _decimal(amount, "refund_amount", positive=True)
    if (
        pos_return.refund_amount is not None
        and pos_return.refunded_amount + amount > pos_return.refund_amount
    ):
        raise ValidationError("POS refund exceeds the authoritative return refund amount.")
    if pos_return.cash_session_id and pos_return.cash_session.state != PosCashSessionState.OPEN:
        raise ValidationError("Cash refund source requires an open cash session.")
    line_quantities = line_quantities or {}
    for line_id, quantity in line_quantities.items():
        line = PosReturnLine.objects.select_for_update().get(pk=line_id, pos_return=pos_return)
        quantity = _decimal(quantity, "refunded_quantity", positive=True)
        if line.refunded_quantity + quantity > line.quantity:
            raise ValidationError("POS refunded quantity exceeds source returned quantity.")
        line.refunded_quantity += quantity
        line.save(update_fields=("refunded_quantity", "updated_at"))
    pos_return.refunded_amount += amount
    pos_return.save(update_fields=("refunded_amount", "updated_at"))
    candidate = _candidate(
        legal_entity=pos_return.legal_entity,
        store=pos_return.store,
        pos_return=pos_return,
        cash_session=pos_return.cash_session,
        event_code=POS_REFUND_EVENT,
        transaction_date=pos_return.return_date,
        amount=amount,
        source_key=f"POS_REFUND|{pos_return.pk}|{idempotency_key}",
        metadata={
            "refund_source": "POS_RETURN",
            "line_quantities": {
                str(line_id): str(quantity) for line_id, quantity in line_quantities.items()
            },
        },
    )
    _audit(pos_return, "omnichannel.pos_return.refund_recorded", actor, key=idempotency_key)
    return candidate


def pos_finance_candidates(sale):
    return PosFinanceSource.objects.filter(sale=sale).order_by("created_at", "source_key")
