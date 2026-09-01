from datetime import date, datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Employee
from apps.catalog.models import UOM, Item
from apps.channels.models import Store
from apps.omnichannel.models import (
    OmniMappingStatus,
    OmniOperationalStatus,
    OmniOrder,
    OmniOrderLine,
    OmniRevenueEvent,
    OmniRevenueState,
    PosCashSessionState,
    PosFinanceSource,
    PosSaleState,
)
from apps.omnichannel.selectors import store_channel_sku_analytics
from apps.omnichannel.services import (
    close_pos_cash_session,
    create_pos_return,
    create_pos_return_quality_candidate,
    create_pos_sale,
    open_pos_cash_session,
    post_pos_sale,
    reverse_pos_sale,
)
from apps.organizations.models import LegalEntity, OrganizationMembership, Warehouse
from apps.quality.services.quality import post_inspection, update_draft_line
from apps.warehouse.models import (
    InventoryValuationState,
    MovementDirection,
    MovementType,
    StockMovement,
)
from apps.warehouse.services import post_pos_return_in, post_stock_movement

pytestmark = pytest.mark.django_db


@pytest.fixture
def foundation():
    entity = LegalEntity.objects.create(code="7C", name="POS Phase 7C")
    user = get_user_model().objects.create_user("phase7c@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    Employee.objects.create(
        legal_entity=entity,
        employee_code="POS-7C",
        display_name="POS inspector",
        user=user,
    )
    uom = UOM.objects.create(
        code="PCS7C", name="Pieces", dimension="COUNT", effective_from=date(2026, 1, 1)
    )
    item = Item.objects.create(
        legal_entity=entity,
        code="ITEM7C",
        name="POS item",
        uom=uom,
        sales_eligible=True,
        inventory_eligible=True,
        effective_from=date(2026, 1, 1),
    )
    inactive_item = Item.objects.create(
        legal_entity=entity,
        code="INACTIVE7C",
        name="Inactive POS item",
        uom=uom,
        sales_eligible=True,
        inventory_eligible=True,
        effective_from=date(2026, 1, 1),
        is_active=False,
    )
    store = Store.objects.create(
        legal_entity=entity,
        code="POS7C",
        name="POS Store",
        channel="POS",
        finance_dimension="POS-7C",
        effective_from=date(2026, 1, 1),
    )
    warehouse = Warehouse.objects.create(legal_entity=entity, code="WHPOS7C", name="POS WH")
    return {
        "entity": entity,
        "user": user,
        "uom": uom,
        "item": item,
        "inactive_item": inactive_item,
        "store": store,
        "warehouse": warehouse,
    }


def transaction_at():
    return timezone.make_aware(datetime(2026, 8, 3, 10, 30))


def add_stock(foundation, quantity=10, *, unit_cost=5000):
    return post_stock_movement(
        legal_entity=foundation["entity"],
        warehouse=foundation["warehouse"],
        item=foundation["item"],
        direction=MovementDirection.IN,
        movement_type=MovementType.PURCHASE_RECEIPT,
        quantity=quantity,
        source_module="test",
        source_type="OPENING",
        source_document_id="opening-7c",
        source_line_id=f"{quantity}-{unit_cost}",
        source_key=f"OPENING|7C|{quantity}|{unit_cost}",
        transaction_date=date(2026, 8, 1),
        actor=foundation["user"],
        unit_cost=Decimal(str(unit_cost)),
        total_value=Decimal(str(quantity * unit_cost)),
        idempotency_key=f"OPENING|7C|{quantity}|{unit_cost}",
    )


def cash_session(foundation, *, key="SESSION|7C"):
    return open_pos_cash_session(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        opening_cash_amount=10000,
        actor=foundation["user"],
        source_key=key,
    )


def draft_sale(foundation, *, quantity=2, price=10000, session=None, key="SALE|7C"):
    return create_pos_sale(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        warehouse=foundation["warehouse"],
        transaction_at=transaction_at(),
        lines=[{"item": foundation["item"], "quantity": quantity, "unit_price_amount": price}],
        tender={
            "method": "CASH",
            "amount": Decimal(str(quantity * price)),
            "cash_session": session,
        },
        source_key=key,
        actor=foundation["user"],
    )


def test_pos_requires_actual_effective_sales_inventory_item(foundation):
    session = cash_session(foundation)
    with pytest.raises(ValidationError):
        create_pos_sale(
            legal_entity=foundation["entity"],
            store=foundation["store"],
            warehouse=foundation["warehouse"],
            transaction_at=transaction_at(),
            lines=[{"item": "category", "quantity": 1, "unit_price_amount": 10}],
            tender={"method": "CASH", "amount": 10, "cash_session": session},
            source_key="BAD|CATEGORY",
        )
    with pytest.raises(ValidationError):
        create_pos_sale(
            legal_entity=foundation["entity"],
            store=foundation["store"],
            warehouse=foundation["warehouse"],
            transaction_at=transaction_at(),
            lines=[{"item": foundation["inactive_item"], "quantity": 1, "unit_price_amount": 10}],
            tender={"method": "CASH", "amount": 10, "cash_session": session},
            source_key="BAD|INACTIVE",
        )
    with pytest.raises(ValidationError):
        draft_sale(foundation, quantity=0, session=session, key="BAD|QTY")


def test_pos_post_is_atomic_for_stock_failure(foundation):
    add_stock(foundation, quantity=1)
    sale = draft_sale(foundation, quantity=2, session=cash_session(foundation))
    with pytest.raises(ValidationError):
        post_pos_sale(sale, actor=foundation["user"], idempotency_key="POST|FAIL")
    sale.refresh_from_db()
    assert sale.state == PosSaleState.DRAFT
    assert not StockMovement.objects.filter(movement_type=MovementType.POS_SALE_ISSUE).exists()
    assert not PosFinanceSource.objects.filter(sale=sale).exists()


def test_successful_pos_sale_uses_warehouse_cost_and_is_idempotent(foundation):
    add_stock(foundation, quantity=10, unit_cost=5000)
    sale = draft_sale(foundation, quantity=2, session=cash_session(foundation))
    posted = post_pos_sale(sale, actor=foundation["user"], idempotency_key="POST|SUCCESS")
    replay = post_pos_sale(sale, actor=foundation["user"], idempotency_key="POST|SUCCESS")
    line = posted.lines.get()
    state = InventoryValuationState.objects.get(
        item=foundation["item"], warehouse=foundation["warehouse"]
    )
    assert posted.pk == replay.pk
    assert posted.state == PosSaleState.POSTED
    assert state.quantity_on_hand == Decimal("8")
    assert line.unit_price_amount == Decimal("10000")
    assert line.warehouse_unit_cost == Decimal("5000")
    assert line.cogs_amount == Decimal("10000")
    assert StockMovement.objects.filter(movement_type=MovementType.POS_SALE_ISSUE).count() == 1
    assert set(posted.finance_sources.values_list("event_code", flat=True)) == {
        "POS_SALE_REVENUE",
        "POS_COGS",
        "POS_TENDER",
    }


def test_cash_session_closes_operationally_and_blocks_later_cash_posting(foundation):
    add_stock(foundation, quantity=10)
    session = cash_session(foundation)
    sale = draft_sale(foundation, quantity=1, session=session)
    post_pos_sale(sale, actor=foundation["user"], idempotency_key="POST|CASH")
    closed = close_pos_cash_session(
        session,
        counted_cash_amount=20000,
        actor=foundation["user"],
        idempotency_key="CLOSE|CASH",
    )
    assert closed.state == PosCashSessionState.CLOSED
    assert closed.expected_cash_amount == Decimal("20000")
    assert closed.variance_amount == Decimal("0")
    assert (
        close_pos_cash_session(
            session,
            counted_cash_amount=20000,
            actor=foundation["user"],
            idempotency_key="CLOSE|CASH",
        ).pk
        == closed.pk
    )
    later = draft_sale(foundation, quantity=1, session=session, key="SALE|CLOSED")
    with pytest.raises(ValidationError):
        post_pos_sale(later, actor=foundation["user"], idempotency_key="POST|CLOSED")
    later.refresh_from_db()
    assert later.state == PosSaleState.DRAFT


def test_pos_reversal_preserves_original_and_posts_compensating_warehouse_lineage(foundation):
    add_stock(foundation, quantity=10)
    sale = draft_sale(foundation, quantity=2, session=cash_session(foundation))
    post_pos_sale(sale, actor=foundation["user"], idempotency_key="POST|REV")
    reversal = reverse_pos_sale(
        sale, reason="customer correction", actor=foundation["user"], idempotency_key="REV|1"
    )
    replay = reverse_pos_sale(
        sale, reason="customer correction", actor=foundation["user"], idempotency_key="REV|1"
    )
    sale.refresh_from_db()
    assert reversal.pk == replay.pk
    assert sale.state == PosSaleState.REVERSED
    assert StockMovement.objects.filter(movement_type=MovementType.POS_SALE_REVERSAL).count() == 1
    assert PosFinanceSource.objects.filter(sale=sale, event_code="POS_REVERSAL").count() == 3


def test_pos_return_is_separate_quality_gated_and_capped(foundation):
    add_stock(foundation, quantity=10)
    sale = draft_sale(foundation, quantity=3, session=cash_session(foundation))
    post_pos_sale(sale, actor=foundation["user"], idempotency_key="POST|RETURN")
    line = sale.lines.get()
    return_source = create_pos_return(
        original_sale=sale,
        lines=[{"original_sale_line": line, "quantity": 2}],
        source_key="RETURN|7C|1",
        actor=foundation["user"],
        return_at=timezone.make_aware(datetime(2026, 8, 5, 12)),
    )
    return_line = return_source.lines.get()
    assert StockMovement.objects.filter(movement_type=MovementType.POS_RETURN_RECEIPT).count() == 0
    inspection = create_pos_return_quality_candidate(return_line, actor=foundation["user"])
    quality_line = inspection.lines.get()
    update_draft_line(quality_line, qty_inspected=1, qty_pass=1, actor=foundation["user"])
    post_inspection(inspection, actor=foundation["user"], idempotency_key="QUALITY|POS|1")
    movement = post_pos_return_in(
        return_line,
        quantity=1,
        warehouse=foundation["warehouse"],
        actor=foundation["user"],
        idempotency_key="RETURN_IN|POS|1",
    )
    assert movement.quantity == Decimal("1")
    with pytest.raises(ValidationError):
        post_pos_return_in(
            return_line,
            quantity=2,
            warehouse=foundation["warehouse"],
            actor=foundation["user"],
            idempotency_key="RETURN_IN|POS|2",
        )
    sale.refresh_from_db()
    assert sale.state == PosSaleState.POSTED
    assert PosFinanceSource.objects.filter(sale=sale, event_code="POS_SALE_REVENUE").exists()


def test_pos_return_cumulative_source_quantity_cannot_exceed_sold_quantity(foundation):
    add_stock(foundation, quantity=5)
    sale = draft_sale(foundation, quantity=2, session=cash_session(foundation))
    post_pos_sale(sale, actor=foundation["user"], idempotency_key="POST|RETURN-LIMIT")
    line = sale.lines.get()
    create_pos_return(
        original_sale=sale,
        lines=[{"original_sale_line": line, "quantity": 1}],
        source_key="RETURN|LIMIT|1",
    )
    with pytest.raises(ValidationError):
        create_pos_return(
            original_sale=sale,
            lines=[{"original_sale_line": line, "quantity": 2}],
            source_key="RETURN|LIMIT|2",
        )


def test_store_sku_analytics_counts_pos_revenue_and_authoritative_cogs_once(foundation):
    add_stock(foundation, quantity=10, unit_cost=5000)
    sale = draft_sale(foundation, quantity=2, session=cash_session(foundation))
    post_pos_sale(sale, actor=foundation["user"], idempotency_key="POST|ANALYTICS")
    rows = store_channel_sku_analytics(
        foundation["user"], start=date(2026, 8, 1), end=date(2026, 8, 31)
    )
    store_row = next(row for row in rows if row["item_id"] is None)
    sku_row = next(row for row in rows if row["item_id"] == foundation["item"].pk)
    assert store_row["pos_revenue"] == Decimal("20000")
    assert store_row["revenue_source"] == Decimal("20000")
    assert store_row["warehouse_cogs"] == Decimal("10000")
    assert store_row["gross_profit_source"] == Decimal("10000")
    assert sku_row["pos_revenue"] == Decimal("20000")
    assert str(sale.pk) in store_row["drilldown"]["pos_sales"]


def test_analytics_keeps_marketplace_order_and_completion_dates_separate(foundation):
    order = OmniOrder.objects.create(
        legal_entity=foundation["entity"],
        marketplace="Shopee",
        external_store_name=foundation["store"].name,
        store=foundation["store"],
        store_code_snapshot=foundation["store"].code,
        store_name_snapshot=foundation["store"].name,
        store_channel_snapshot=foundation["store"].channel,
        external_order_number="ORDER-7C-DATE",
        source_identity_key="ORDER-7C-DATE",
        order_date=date(2026, 7, 31),
        completion_date=date(2026, 8, 3),
        normalized_status=OmniOperationalStatus.COMPLETED,
        mapping_status=OmniMappingStatus.READY,
    )
    OmniOrderLine.objects.create(
        order=order,
        external_sku="ITEM7C",
        external_sku_normalized="ITEM7C",
        variation="",
        variation_normalized="",
        item=foundation["item"],
        marketplace_quantity=Decimal("1"),
        conversion_quantity=Decimal("1"),
        internal_quantity=Decimal("1"),
        source_subtotal=Decimal("12000"),
        normalized_status=OmniOperationalStatus.COMPLETED,
        mapping_status=OmniMappingStatus.READY,
    )
    OmniRevenueEvent.objects.create(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        marketplace="Shopee",
        order=order,
        external_order_number=order.external_order_number,
        completion_date=date(2026, 8, 3),
        gross_eligible_amount=Decimal("12000"),
        state=OmniRevenueState.ELIGIBLE,
        event_key="OMNI_REV|7C|ORDER-7C-DATE",
    )
    july = store_channel_sku_analytics(
        foundation["user"], start=date(2026, 7, 1), end=date(2026, 7, 31)
    )
    august = store_channel_sku_analytics(
        foundation["user"], start=date(2026, 8, 1), end=date(2026, 8, 31)
    )
    july_store = next(row for row in july if row["item_id"] is None)
    august_store = next(row for row in august if row["item_id"] is None)
    assert july_store["marketplace_order_count"] == 1
    assert july_store["marketplace_completed_revenue"] == Decimal("0")
    assert august_store["marketplace_order_count"] == 0
    assert august_store["marketplace_completed_revenue"] == Decimal("12000")
