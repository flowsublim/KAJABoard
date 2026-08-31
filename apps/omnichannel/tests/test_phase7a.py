from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.catalog.models import UOM, Item
from apps.channels.models import ExternalSKUMap, Store
from apps.omnichannel.models import (
    OmniException,
    OmniImportBatch,
    OmniMappingStatus,
    OmniOrder,
    OmniOrderLine,
    OmniPacking,
)
from apps.omnichannel.selectors import order_daily_store_summary, warehouse_demand
from apps.omnichannel.services import (
    commit_bigseller_import,
    create_packing,
    post_packing,
    preview_bigseller_import,
)
from apps.omnichannel.services.imports import (
    HEADER_ALIASES,
    REQUIRED_FIELDS,
    _key,
    _read_xlsx,
    read_bigseller_rows,
)
from apps.organizations.models import LegalEntity, OrganizationMembership, Warehouse
from apps.warehouse.models import InventoryValuationState, MovementType, StockMovement
from apps.warehouse.services import post_stock_movement

pytestmark = pytest.mark.django_db


@pytest.fixture
def foundation():
    entity = LegalEntity.objects.create(code="7A", name="Omni Entity")
    user = get_user_model().objects.create_user("omni@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(Permission.objects.get(codename="post_omnipacking"))
    uom = UOM.objects.create(code="PCS7A", name="Pieces", dimension="COUNT")
    item = Item.objects.create(
        legal_entity=entity,
        code="ITEM7A",
        name="Mapped item",
        uom=uom,
        sales_eligible=True,
        inventory_eligible=True,
    )
    other_item = Item.objects.create(
        legal_entity=entity,
        code="ITEM7B",
        name="Blue item",
        uom=uom,
        sales_eligible=True,
        inventory_eligible=True,
    )
    store = Store.objects.create(
        legal_entity=entity,
        code="STORE7A",
        name="Store A",
        channel="SHOPEE",
        external_aliases=["BigSeller A"],
        effective_from=date(2026, 1, 1),
    )
    warehouse = Warehouse.objects.create(legal_entity=entity, code="WH7A", name="Omni warehouse")
    red = ExternalSKUMap.objects.create(
        store=store,
        item=item,
        external_sku="ABC",
        external_sku_normalized="abc",
        external_variation="RED",
        external_variation_normalized="red",
        conversion_quantity=Decimal("2"),
        effective_from=date(2026, 1, 1),
    )
    blue = ExternalSKUMap.objects.create(
        store=store,
        item=other_item,
        external_sku="ABC",
        external_sku_normalized="abc",
        external_variation="BLUE",
        external_variation_normalized="blue",
        conversion_quantity=Decimal("1"),
        effective_from=date(2026, 1, 1),
    )
    return {
        "entity": entity,
        "user": user,
        "item": item,
        "other_item": other_item,
        "store": store,
        "warehouse": warehouse,
        "red": red,
        "blue": blue,
    }


def source(
    order="ORDER-1",
    variation="RED",
    qty="3",
    status="Processing",
    order_date="2026-07-31",
    completion="2026-08-03",
    store="BigSeller A",
    sku="ABC",
):
    return {
        "Waktu Pesanan Dibuat": order_date,
        "Waktu Selesai": completion,
        "Nomor Pesanan": order,
        "Status Pesanan": status,
        "Nama Panggilan Toko BigSeller": store,
        "Marketplace": "SHOPEE",
        "SKU": sku,
        "Nama Produk": "Product",
        "Nama Variasi": variation,
        "Jumlah": qty,
        "Subtotal Produk": "120000",
        "Nomor Resi": "RESI-1",
    }


def import_rows(foundation, rows):
    batch = preview_bigseller_import(
        legal_entity=foundation["entity"],
        payload=rows,
        source_filename="bigseller.csv",
        actor=foundation["user"],
    )
    commit_bigseller_import(
        batch=batch, actor=foundation["user"], idempotency_key=f"IMPORT|{batch.pk}"
    )
    return batch


def test_bigseller_import_preserves_exact_variations_and_quantity_snapshots(foundation):
    import_rows(
        foundation,
        [
            source(order="ORDER-V", variation="RED"),
            source(order="ORDER-V", variation="BLUE", qty="1"),
        ],
    )
    order = OmniOrder.objects.get(external_order_number="ORDER-V")
    lines = {line.variation: line for line in order.lines.all()}
    assert set(lines) == {"RED", "BLUE"}
    assert lines["RED"].marketplace_quantity == Decimal("3")
    assert lines["RED"].conversion_quantity == Decimal("2")
    assert lines["RED"].internal_quantity == Decimal("6")
    assert lines["RED"].mapping_snapshot["item_id"] == str(foundation["item"].pk)

    tomorrow = date.today() + timedelta(days=1)
    ExternalSKUMap.objects.create(
        store=foundation["store"],
        item=foundation["item"],
        external_sku="ABC",
        external_sku_normalized="abc",
        external_variation="RED",
        external_variation_normalized="red",
        conversion_quantity=Decimal("4"),
        effective_from=tomorrow,
    )
    assert OmniOrderLine.objects.get(order=order, variation="RED").internal_quantity == Decimal("6")


def test_order_and_completion_dates_are_separate_and_import_is_idempotent(foundation):
    rows = [source(order="ORDER-IDEMP")]
    first = preview_bigseller_import(
        legal_entity=foundation["entity"],
        payload=rows,
        source_filename="same.csv",
        actor=foundation["user"],
    )
    second = preview_bigseller_import(
        legal_entity=foundation["entity"],
        payload=rows,
        source_filename="same.csv",
        actor=foundation["user"],
    )
    assert first.pk == second.pk
    commit_bigseller_import(
        batch=first, actor=foundation["user"], idempotency_key=f"IMPORT|{first.pk}"
    )
    commit_bigseller_import(
        batch=first, actor=foundation["user"], idempotency_key=f"IMPORT|{first.pk}"
    )
    order = OmniOrder.objects.get(external_order_number="ORDER-IDEMP")
    assert order.order_date == date(2026, 7, 31)
    assert order.completion_date == date(2026, 8, 3)
    assert order.store_mapping_snapshot["external_identifier"] == "BigSeller A"
    assert order_daily_store_summary(foundation["user"])[0]["order_date"] == date(2026, 7, 31)
    assert OmniOrder.objects.count() == 1
    assert StockMovement.objects.count() == 0


def test_unmapped_store_and_sku_are_retained_but_never_become_demand(foundation):
    batch = preview_bigseller_import(
        legal_entity=foundation["entity"],
        payload=[source(order="UNMAPPED-STORE", store="Unknown")],
        source_filename="unmapped.csv",
        actor=foundation["user"],
    )
    assert batch.rows.first().mapping_status == OmniMappingStatus.UNMAPPED_STORE
    commit_bigseller_import(
        batch=batch, actor=foundation["user"], idempotency_key=f"IMPORT|{batch.pk}"
    )
    assert OmniOrder.objects.get(external_order_number="UNMAPPED-STORE").store is None

    batch = preview_bigseller_import(
        legal_entity=foundation["entity"],
        payload=[source(order="UNMAPPED-SKU", sku="UNKNOWN")],
        source_filename="unmapped-sku.csv",
        actor=foundation["user"],
    )
    assert batch.rows.first().mapping_status == OmniMappingStatus.UNMAPPED_SKU
    commit_bigseller_import(
        batch=batch, actor=foundation["user"], idempotency_key=f"IMPORT|{batch.pk}"
    )
    assert not warehouse_demand(foundation["user"])
    assert StockMovement.objects.count() == 0


def test_xlsx_header_parser_and_invalid_rows_are_explicit(foundation):
    payload = BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
        xml = (
            "<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
            "<sheetData><row r='1'>"
            "<c r='A1' t='inlineStr'><is><t>Nomor Pesanan</t></is></c>"
            "<c r='B1' t='inlineStr'><is><t>Waktu Pesanan Dibuat</t></is></c>"
            "<c r='C1' t='inlineStr'><is><t>Nama Panggilan Toko BigSeller</t></is></c>"
            "<c r='D1' t='inlineStr'><is><t>SKU</t></is></c>"
            "<c r='E1' t='inlineStr'><is><t>Jumlah</t></is></c>"
            "</row><row r='2'>"
            "<c r='A2' t='inlineStr'><is><t>XLSX-1</t></is></c>"
            "<c r='B2' t='inlineStr'><is><t>31/07/2026</t></is></c>"
            "<c r='C2' t='inlineStr'><is><t>BigSeller A</t></is></c>"
            "<c r='D2' t='inlineStr'><is><t>ABC</t></is></c>"
            "<c r='E2' t='n'><v>3</v></c>"
            "</row></sheetData></worksheet>"
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            xml,
        )
    batch = preview_bigseller_import(
        legal_entity=foundation["entity"],
        payload=payload.getvalue(),
        source_filename="orders.xlsx",
        actor=foundation["user"],
    )
    assert batch.row_count == 1
    assert batch.rows.first().marketplace_quantity == Decimal("3")


def _sanitized_bigseller_fixture(filename):
    path = (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "fixtures"
        / "omnichannel"
        / "bigseller"
        / filename
    )
    if not path.exists():
        pytest.fail(f"Sanitized BigSeller fixture is missing: {filename}")
    return path


def test_sanitized_bigseller_order_goods_fixture_is_compatible_and_idempotent(foundation):
    path = _sanitized_bigseller_fixture("order_goods_sample_sanitized.xlsx")
    payload = path.read_bytes()
    rows = read_bigseller_rows(payload, path.name)
    assert len(rows) == 6
    header_keys = {_key(header) for header in rows[0]}
    assert all(
        any(_key(alias) in header_keys for alias in HEADER_ALIASES[field])
        for field in REQUIRED_FIELDS
    )
    first = rows[0]
    assert first["Waktu Pesanan Dibuat"] == "01 Agu 2026 00:00"
    assert first["Waktu Selesai"] == "04 Agu 2026 22:16"
    assert first["Status Pesanan"] == "Selesai"
    assert first["Jumlah"] == "1"
    assert first["SKU"] == "SKU-SAMPLE-RED"
    assert first["Nama Variasi"] == "RED"
    assert rows[1]["SKU"] == first["SKU"]
    assert rows[1]["Nama Variasi"] == "BLUE"
    assert {rows[0]["Nama Variasi"], rows[1]["Nama Variasi"]} == {"RED", "BLUE"}
    assert sum(not row["Nama Variasi"] for row in rows) == 1
    assert {row["Jumlah"] for row in rows[:3]} == {"1", "2", "10"}
    logical_keys = {(row["Nomor Pesanan"], row["SKU"], row["Nama Variasi"]) for row in rows}
    assert len(logical_keys) == len(rows)
    placeholder_row_number = next(
        number for number, row in enumerate(rows, start=2) if row["Subtotal Produk"] == "--"
    )

    real_store = Store.objects.create(
        legal_entity=foundation["entity"],
        code="SAN-STORE-7A",
        name="STORE-SAMPLE-A",
        channel="TIKTOK",
        effective_from=date(2026, 1, 1),
    )
    ExternalSKUMap.objects.create(
        store=real_store,
        item=foundation["item"],
        external_sku="SKU-SAMPLE-RED",
        external_sku_normalized="sku-sample-red",
        external_variation="RED",
        external_variation_normalized="red",
        conversion_quantity=Decimal("1"),
        effective_from=date(2026, 1, 1),
    )
    batch = preview_bigseller_import(
        legal_entity=foundation["entity"],
        payload=payload,
        source_filename=path.name,
        actor=foundation["user"],
    )
    imported = batch.rows.get(row_number=2)
    assert imported.mapping_status == OmniMappingStatus.READY
    assert imported.resolved_store_id == real_store.pk
    assert imported.resolved_item_id == foundation["item"].pk
    assert imported.marketplace_quantity == Decimal("1")
    assert imported.conversion_quantity == Decimal("1")
    assert imported.order_date == date(2026, 8, 1)
    assert imported.completion_date == date(2026, 8, 4)
    assert imported.raw_status == "Selesai"
    assert imported.normalized_status == "COMPLETED"
    assert imported.tracking_number == "SAN-RESI-001"
    assert imported.product == ""
    assert imported.marketplace == ""
    assert imported.raw_data["Harga Satuan"] == "100000"
    assert imported.raw_data["Waktu Pesanan Dikirim"] == "01 Agu 2026 15:25"
    assert imported.raw_data["Voucher"] == "1000"
    assert imported.raw_data["Biaya Pengelolaan"] == "--"
    assert batch.rows.get(row_number=3).source_subtotal is None
    assert batch.rows.get(row_number=3).raw_data["Subtotal Produk"] == "-"
    assert batch.rows.get(row_number=4).source_subtotal is None
    assert batch.rows.get(row_number=4).raw_data["Subtotal Produk"] == "N/A"
    assert batch.rows.get(row_number=placeholder_row_number).source_subtotal is None
    assert batch.rows.get(row_number=3).completion_date is None
    assert batch.rows.get(row_number=7).normalized_status == "RETURNED"
    assert not batch.rows.filter(
        mapping_status__in=[
            OmniMappingStatus.INVALID_QTY,
            OmniMappingStatus.INVALID_ORDER_DATE,
            OmniMappingStatus.INVALID_COMPLETION_DATE,
        ]
    ).exists()

    commit_bigseller_import(
        batch=batch, actor=foundation["user"], idempotency_key=f"SANITIZED|{batch.pk}"
    )
    replay = preview_bigseller_import(
        legal_entity=foundation["entity"],
        payload=payload,
        source_filename=path.name,
        actor=foundation["user"],
    )
    commit_bigseller_import(
        batch=replay, actor=foundation["user"], idempotency_key=f"SANITIZED|{batch.pk}"
    )
    assert replay.pk == batch.pk
    assert StockMovement.objects.count() == 0
    order = OmniOrder.objects.get(external_order_number=first["Nomor Pesanan"])
    assert order.marketplace == "TIKTOK"
    assert order.lines.count() == 3
    mapped_line = order.lines.get(external_sku="SKU-SAMPLE-RED", variation="RED")
    assert mapped_line.conversion_quantity == Decimal("1")
    assert mapped_line.internal_quantity == Decimal("1")


def test_sanitized_bigseller_return_fixture_preserves_real_schema_without_importing_returns():
    path = _sanitized_bigseller_fixture("order_return_sample_sanitized.xlsx")
    payload = path.read_bytes()
    rows = _read_xlsx(payload)
    assert len(rows) == 3
    assert len(rows[0]) == 42
    assert {row["Marketplace"] for row in rows} == {"TikTok", "Shopee"}
    assert rows[0]["Toko BigSeller"] == "STORE-SAMPLE-A"
    assert rows[0]["Nomor Pesanan"] == "ORDER-SAMPLE-001"
    assert rows[0]["Nomor Paket"] == rows[1]["Nomor Paket"]
    assert {rows[0]["SKU Toko"], rows[1]["SKU Toko"]} == {
        "SKU-SAMPLE-RED",
        "SKU-SAMPLE-BLUE",
    }
    assert [row["Jumlah"] for row in rows] == ["1", "2", "1"]
    assert "Nama Variasi" not in rows[0]
    assert all(not row["ID Purna Jual"] for row in rows)
    assert all(not row["Dana Pengembalian"] for row in rows)
    assert all(not row["Alasan Retur"] for row in rows)
    assert all(not row["Waktu Penambahan Stok"] for row in rows)
    assert len({row["Nomor Paket"] for row in rows}) < len(rows)

    with ZipFile(BytesIO(payload)) as archive:
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    quantity_cells = [
        cell
        for cell in sheet.findall(".//{*}c")
        if cell.attrib.get("r", "").startswith("U") and cell.attrib.get("t") == "n"
    ]
    assert len(quantity_cells) == 3
    assert all(cell.attrib.get("t") == "n" for cell in quantity_cells)


def test_packing_posts_only_through_warehouse_and_caps_repeated_issue(foundation):
    post_stock_movement(
        legal_entity=foundation["entity"],
        warehouse=foundation["warehouse"],
        item=foundation["item"],
        direction="IN",
        movement_type="PURCHASE_RECEIPT",
        quantity=Decimal("10"),
        source_module="test",
        source_type="OPENING",
        source_document_id="opening",
        source_line_id="1",
        source_key="OPENING|7A",
        transaction_date=date.today(),
        unit_cost=Decimal("5000"),
        total_value=Decimal("50000"),
        actor=foundation["user"],
        idempotency_key="OPENING|7A",
    )
    import_rows(foundation, [source(order="PACK-1")])
    demand = warehouse_demand(foundation["user"], warehouse=foundation["warehouse"])[0]
    first = create_packing(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        warehouse=foundation["warehouse"],
        packing_date=date.today(),
        lines=[{"order_line": demand["order_line"], "quantity": Decimal("4")}],
        actor=foundation["user"],
    )
    post_packing(first, actor=foundation["user"], idempotency_key="PACK|1")
    second = create_packing(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        warehouse=foundation["warehouse"],
        packing_date=date.today(),
        lines=[{"order_line": demand["order_line"], "quantity": Decimal("2")}],
        actor=foundation["user"],
    )
    post_packing(second, actor=foundation["user"], idempotency_key="PACK|2")
    with pytest.raises(ValidationError):
        create_packing(
            legal_entity=foundation["entity"],
            store=foundation["store"],
            warehouse=foundation["warehouse"],
            packing_date=date.today(),
            lines=[{"order_line": demand["order_line"], "quantity": Decimal("1")}],
            actor=foundation["user"],
        )
    movement = StockMovement.objects.filter(movement_type=MovementType.OMNI_PACKING)
    assert movement.count() == 2
    assert InventoryValuationState.objects.get(
        item=foundation["item"], warehouse=foundation["warehouse"]
    ).quantity_on_hand == Decimal("4")
    assert not warehouse_demand(foundation["user"], warehouse=foundation["warehouse"])


def test_packing_shortage_is_visible_and_cancellation_after_pack_is_exception(foundation):
    post_stock_movement(
        legal_entity=foundation["entity"],
        warehouse=foundation["warehouse"],
        item=foundation["item"],
        direction="IN",
        movement_type="PURCHASE_RECEIPT",
        quantity=Decimal("6"),
        source_module="test",
        source_type="OPENING",
        source_document_id="opening-2",
        source_line_id="1",
        source_key="OPENING|7A|2",
        transaction_date=date.today(),
        unit_cost=Decimal("5000"),
        total_value=Decimal("30000"),
        actor=foundation["user"],
        idempotency_key="OPENING|7A|2",
    )
    import_rows(foundation, [source(order="PACK-CANCEL", qty="5")])
    demand = warehouse_demand(foundation["user"], warehouse=foundation["warehouse"])[0]
    assert demand["shortage_quantity"] == Decimal("4")
    packing = create_packing(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        warehouse=foundation["warehouse"],
        packing_date=date.today(),
        lines=[{"order_line": demand["order_line"], "quantity": Decimal("5")}],
        actor=foundation["user"],
    )
    post_packing(packing, actor=foundation["user"], idempotency_key="PACK|CANCEL")
    changed = source(order="PACK-CANCEL", qty="5", status="Cancelled")
    batch = preview_bigseller_import(
        legal_entity=foundation["entity"],
        payload=[changed],
        source_filename="changed.csv",
        actor=foundation["user"],
    )
    commit_bigseller_import(
        batch=batch, actor=foundation["user"], idempotency_key=f"IMPORT|{batch.pk}"
    )
    assert OmniException.objects.filter(code=OmniMappingStatus.SOURCE_CHANGED).exists()
    assert not warehouse_demand(foundation["user"], warehouse=foundation["warehouse"])
    assert StockMovement.objects.filter(movement_type=MovementType.OMNI_PACKING).count() == 1


def test_omni_routes_are_permission_aware_and_get_read_only(client, foundation):
    client.force_login(foundation["user"])
    assert client.get(reverse("omnichannel:dashboard")).status_code == 403
    foundation["user"].is_superuser = True
    foundation["user"].save(update_fields=("is_superuser",))
    for name in (
        "omnichannel:dashboard",
        "omnichannel:import",
        "omnichannel:order-list",
        "omnichannel:warehouse-queue",
        "omnichannel:packing-list",
        "omnichannel:exception-list",
    ):
        response = client.get(reverse(name))
        assert response.status_code == 200
    assert OmniImportBatch.objects.count() == 0
    assert OmniPacking.objects.count() == 0
    assert StockMovement.objects.count() == 0
