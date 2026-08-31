from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.models import Employee
from apps.catalog.models import UOM, Item
from apps.channels.models import Store
from apps.omnichannel.models import (
    OmniAdjustmentSource,
    OmniOrder,
    OmniOrderLine,
    OmniPayoutSource,
    OmniReconciliationStatus,
    OmniReturnImportBatch,
    OmniReturnLinkageStatus,
    OmniReturnSource,
    OmniRevenueEvent,
    OmniSettlement,
    OmniSettlementFee,
)
from apps.omnichannel.services import (
    commit_bigseller_import,
    create_adjustment_source,
    create_payout_source,
    create_return_quality_candidate,
    create_revenue_event,
    import_return_source,
    import_settlement_source,
    preview_bigseller_import,
    revenue_finance_candidate,
)
from apps.organizations.models import LegalEntity, OrganizationMembership, Warehouse
from apps.quality.models import QualityInspection
from apps.quality.services.quality import post_inspection, update_draft_line
from apps.warehouse.models import MovementType, StockMovement
from apps.warehouse.services import post_marketplace_return_in

pytestmark = pytest.mark.django_db


@pytest.fixture
def foundation():
    entity = LegalEntity.objects.create(code="7B", name="Omni Phase 7B")
    user = get_user_model().objects.create_user("phase7b@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    uom = UOM.objects.create(code="PCS7B", name="Pieces", dimension="COUNT")
    item = Item.objects.create(
        legal_entity=entity,
        code="ITEM7B",
        name="Phase 7B item",
        uom=uom,
        sales_eligible=True,
        inventory_eligible=True,
    )
    store = Store.objects.create(
        legal_entity=entity,
        code="STORE7B",
        name="Store 7B",
        channel="SHOPEE",
        external_aliases=["Store 7B source"],
        effective_from=date(2026, 1, 1),
    )
    warehouse = Warehouse.objects.create(legal_entity=entity, code="WH7B", name="Phase 7B")
    return {
        "entity": entity,
        "user": user,
        "item": item,
        "store": store,
        "warehouse": warehouse,
    }


def order_source(order="ORDER-7B", *, status="Selesai", completion="03 Agu 2026"):
    return {
        "Waktu Pesanan Dibuat": "31 Jul 2026",
        "Waktu Selesai": completion,
        "Nomor Pesanan": order,
        "Status Pesanan": status,
        "Nama Panggilan Toko BigSeller": "Store 7B source",
        "Marketplace": "SHOPEE",
        "SKU": "SKU-7B",
        "Nama Produk": "Phase 7B product",
        "Nama Variasi": "RED",
        "Jumlah": "1",
        "Subtotal Produk": "100000",
        "Nomor Resi": "RESI-7B",
    }


def import_order(foundation, rows):
    batch = preview_bigseller_import(
        legal_entity=foundation["entity"],
        payload=rows,
        source_filename="phase7b.csv",
        actor=foundation["user"],
    )
    commit_bigseller_import(
        batch=batch, actor=foundation["user"], idempotency_key=f"PHASE7B|{batch.pk}"
    )
    return OmniOrder.objects.get(external_order_number=rows[0]["Nomor Pesanan"])


def return_fixture_path(filename):
    return (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "fixtures"
        / "omnichannel"
        / "bigseller"
        / filename
    )


def test_revenue_uses_completion_date_and_is_one_order_level_source(foundation):
    order = import_order(
        foundation,
        [
            order_source(),
            {**order_source(), "Nama Variasi": "BLUE", "Subtotal Produk": "25000"},
            {**order_source(), "Nama Variasi": "GREEN", "Subtotal Produk": "15000"},
        ],
    )
    event = create_revenue_event(order, actor=foundation["user"])
    replay = create_revenue_event(order, actor=foundation["user"])
    assert event.pk == replay.pk
    assert OmniRevenueEvent.objects.count() == 1
    assert event.completion_date == date(2026, 8, 3)
    assert event.gross_eligible_amount == Decimal("140000")
    assert event.mapping_status == OmniReconciliationStatus.BLOCKED_MAPPING
    candidate = revenue_finance_candidate(event)
    assert candidate["event_code"] == "OMNI_ORDER_COMPLETED"
    assert candidate["completion_date"] == date(2026, 8, 3)
    assert candidate["mapping_status"] == OmniReconciliationStatus.BLOCKED_MAPPING
    assert event.order.order_date == date(2026, 7, 31)
    assert StockMovement.objects.count() == 0


@pytest.mark.parametrize(
    ("status", "completion"),
    [("Diproses", "03 Agu 2026"), ("Selesai", "")],
)
def test_revenue_requires_completed_status_and_completion_date(foundation, status, completion):
    order = import_order(foundation, [order_source(status=status, completion=completion)])
    assert create_revenue_event(order, actor=foundation["user"]) is None
    assert OmniRevenueEvent.objects.count() == 0


def test_revenue_keeps_unknown_amount_blocked_instead_of_zero(foundation):
    order = import_order(foundation, [{**order_source(), "Subtotal Produk": "--"}])
    event = create_revenue_event(order)
    assert event.gross_eligible_amount is None
    assert event.state == "BLOCKED_AMOUNT"


def test_settlement_is_separate_idempotent_and_partial(foundation):
    order = import_order(foundation, [order_source()])
    event = create_revenue_event(order)
    row = {
        "Toko": "Store 7B source",
        "Marketplace": "SHOPEE",
        "No Pesanan": "ORDER-7B",
        "Settlement Reference": "SETTLE-7B-1",
        "Tgl Pencairan": "05 Agu 2026",
        "Pendapatan Bersih": "60000",
        "Biaya Admin": "5000",
    }
    first = import_settlement_source(
        legal_entity=foundation["entity"],
        payload=[row],
        source_filename="settlement.csv",
        actor=foundation["user"],
    )
    second = import_settlement_source(
        legal_entity=foundation["entity"],
        payload=[row],
        source_filename="settlement.csv",
        actor=foundation["user"],
    )
    settlement = OmniSettlement.objects.get()
    assert first.pk == second.pk
    assert settlement.matched_revenue_id == event.pk
    assert settlement.settlement_date == date(2026, 8, 5)
    assert settlement.net_amount == Decimal("60000")
    assert settlement.fee_amount == Decimal("5000")
    assert settlement.reconciliation_status == OmniReconciliationStatus.SETTLEMENT_PARTIAL
    assert OmniSettlementFee.objects.count() == 1
    assert OmniSettlement.objects.count() == 1
    assert event.refresh_from_db() is None
    assert event.completion_date == date(2026, 8, 3)
    assert event.gross_eligible_amount == Decimal("100000")
    assert StockMovement.objects.count() == 0


def test_changed_settlement_source_is_conflict_not_overwrite(foundation):
    import_settlement_source(
        legal_entity=foundation["entity"],
        payload=[
            {
                "Toko": "Store 7B source",
                "No Pesanan": "ORDER-CHANGED",
                "Settlement Reference": "SETTLE-CHANGE",
                "Tgl Pencairan": "05 Agu 2026",
                "Pendapatan Bersih": "100",
            }
        ],
        source_filename="one.csv",
    )
    import_settlement_source(
        legal_entity=foundation["entity"],
        payload=[
            {
                "Toko": "Store 7B source",
                "No Pesanan": "ORDER-CHANGED",
                "Settlement Reference": "SETTLE-CHANGE",
                "Tgl Pencairan": "05 Agu 2026",
                "Pendapatan Bersih": "200",
            }
        ],
        source_filename="two.csv",
    )
    assert OmniSettlement.objects.count() == 2
    assert (
        OmniSettlement.objects.filter(
            reconciliation_status=OmniReconciliationStatus.SOURCE_CHANGED
        ).count()
        == 1
    )
    assert OmniSettlement.objects.filter(net_amount=Decimal("100")).exists()


def test_real_return_fixture_is_source_only_and_row_identity_is_durable(foundation):
    path = return_fixture_path("order_return_sample_sanitized.xlsx")
    batch = import_return_source(
        legal_entity=foundation["entity"],
        payload=path.read_bytes(),
        source_filename=path.name,
        actor=foundation["user"],
    )
    replay = import_return_source(
        legal_entity=foundation["entity"],
        payload=path.read_bytes(),
        source_filename=path.name,
    )
    assert batch.pk == replay.pk
    assert OmniReturnSource.objects.count() == 3
    assert {source.marketplace for source in OmniReturnSource.objects.all()} == {"TIKTOK", "SHOPEE"}
    first_package = OmniReturnSource.objects.order_by("source_row_key").first().package_number
    assert OmniReturnSource.objects.filter(package_number=first_package).count() == 2
    assert all(not source.external_return_id for source in OmniReturnSource.objects.all())
    assert all("variation" not in source.raw_data for source in OmniReturnSource.objects.all())
    assert len(set(OmniReturnSource.objects.values_list("source_identity_key", flat=True))) == 3
    assert all(
        source.linkage_status == OmniReturnLinkageStatus.BLOCKED_MAPPING
        for source in OmniReturnSource.objects.all()
    )
    assert StockMovement.objects.count() == 0


def test_return_without_variation_is_ambiguous_and_cannot_enter_quality(foundation):
    store = foundation["store"]
    order = OmniOrder.objects.create(
        legal_entity=foundation["entity"],
        store=store,
        marketplace="SHOPEE",
        external_store_name=store.name,
        external_order_number="ORDER-AMBIGUOUS",
        source_identity_key="ORDER|ORDER-AMBIGUOUS",
        order_date=date(2026, 7, 31),
        completion_date=date(2026, 8, 3),
        normalized_status="COMPLETED",
    )
    for variation in ("RED", "BLUE"):
        OmniOrderLine.objects.create(
            order=order,
            external_sku="ABC",
            external_sku_normalized="abc",
            variation=variation,
            variation_normalized=variation.casefold(),
            marketplace_quantity=1,
            mapping_status="READY",
        )
    batch = import_return_source(
        legal_entity=foundation["entity"],
        payload=[
            {
                "Marketplace": "SHOPEE",
                "Toko BigSeller": "Store 7B source",
                "Nomor Paket": "PKG-AMBIGUOUS",
                "Nomor Pesanan": "ORDER-AMBIGUOUS",
                "SKU Toko": "ABC",
                "Jumlah": 2,
            }
        ],
        source_filename="return.csv",
    )
    source = batch.returns.get()
    assert source.linkage_status == OmniReturnLinkageStatus.AMBIGUOUS_ORDER_LINE
    with pytest.raises(ValidationError):
        create_return_quality_candidate(source)
    assert StockMovement.objects.count() == 0


def test_quality_pass_is_required_before_warehouse_return_in_and_is_capped(foundation):
    batch = OmniReturnImportBatch.objects.create(
        legal_entity=foundation["entity"],
        source_filename="pass.csv",
        file_hash="pass-batch",
    )
    source = OmniReturnSource.objects.create(
        batch=batch,
        legal_entity=foundation["entity"],
        store=foundation["store"],
        marketplace="SHOPEE",
        package_number="PKG-PASS",
        external_order_number="ORDER-PASS",
        external_sku="SKU-7B",
        quantity=2,
        linkage_status=OmniReturnLinkageStatus.MATCHED,
        resolved_item=foundation["item"],
        source_row_key="ROW:1",
        source_identity_key="OMNI_RETURN|ROW:PASS",
    )
    Employee.objects.create(
        legal_entity=foundation["entity"],
        employee_code="EMP-7B",
        display_name="Phase 7B inspector",
        user=foundation["user"],
    )
    inspection = create_return_quality_candidate(
        source, warehouse=foundation["warehouse"], actor=foundation["user"]
    )
    line = inspection.lines.get()

    update_draft_line(line, qty_inspected=1, qty_pass=1, actor=foundation["user"])
    assert StockMovement.objects.count() == 0
    post_inspection(inspection, actor=foundation["user"], idempotency_key="QUALITY|7B|PASS")
    movement = post_marketplace_return_in(
        source,
        quantity=1,
        idempotency_key="RETURN|7B|IN|1",
        warehouse=foundation["warehouse"],
        actor=foundation["user"],
    )
    assert movement.movement_type == MovementType.MARKETPLACE_RETURN_RECEIPT
    assert movement.quantity == Decimal("1")
    source.refresh_from_db()
    assert source.warehouse_returned_quantity == Decimal("1")
    with pytest.raises(ValidationError):
        post_marketplace_return_in(
            source,
            quantity=2,
            idempotency_key="RETURN|7B|IN|2",
            warehouse=foundation["warehouse"],
        )
    assert StockMovement.objects.count() == 1
    line.refresh_from_db()
    assert line.qty_pass == Decimal("1")


def test_adjustment_types_and_payout_retry_are_distinct_source_records(foundation):
    adjustment_a = create_adjustment_source(
        legal_entity=foundation["entity"],
        data={
            "store_name": "Store 7B source",
            "marketplace": "SHOPEE",
            "external_order_number": "ORDER-ADJ",
            "reference": "ADJ-1",
            "adjustment_type": "FEE",
            "amount": "500",
            "transaction_date": date(2026, 8, 5),
        },
    )
    adjustment_b = create_adjustment_source(
        legal_entity=foundation["entity"],
        data={
            "store_name": "Store 7B source",
            "marketplace": "SHOPEE",
            "external_order_number": "ORDER-ADJ",
            "reference": "ADJ-1",
            "adjustment_type": "REFUND",
            "amount": "700",
            "transaction_date": date(2026, 8, 5),
        },
    )
    assert adjustment_a.pk != adjustment_b.pk
    assert OmniAdjustmentSource.objects.count() == 2
    payout_data = {
        "store_name": "Store 7B source",
        "marketplace": "SHOPEE",
        "payout_reference": "PAYOUT-7B",
        "payout_date": date(2026, 8, 6),
        "amount": "1000",
        "currency": "IDR",
        "source_row_key": "ROW:1",
    }
    first = create_payout_source(legal_entity=foundation["entity"], data=payout_data)
    replay = create_payout_source(legal_entity=foundation["entity"], data=payout_data)
    assert first.pk == replay.pk
    assert OmniPayoutSource.objects.count() == 1
    assert StockMovement.objects.count() == 0


def test_phase7b_get_screens_are_read_only(foundation, client):
    permissions = Permission.objects.filter(
        codename__in={
            "view_omniorder",
            "view_omnirevenueevent",
            "view_omnisettlement",
            "view_omnireturnsource",
            "view_omniadjustmentsource",
            "view_omnipayoutsource",
        }
    )
    foundation["user"].user_permissions.add(*permissions)
    client.force_login(foundation["user"])
    before = {
        "revenue": OmniRevenueEvent.objects.count(),
        "returns": OmniReturnSource.objects.count(),
        "quality": QualityInspection.objects.count(),
        "stock": StockMovement.objects.count(),
    }
    for name in (
        "omnichannel:revenue",
        "omnichannel:settlement",
        "omnichannel:return-list",
        "omnichannel:adjustment-list",
        "omnichannel:reconciliation",
        "omnichannel:payout",
    ):
        assert client.get(reverse(name)).status_code == 200
        assert client.get(reverse(name)).status_code == 200
    assert before == {
        "revenue": OmniRevenueEvent.objects.count(),
        "returns": OmniReturnSource.objects.count(),
        "quality": QualityInspection.objects.count(),
        "stock": StockMovement.objects.count(),
    }
