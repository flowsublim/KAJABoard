from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.models import Employee
from apps.catalog.models import UOM, Item
from apps.core.services.numbering import create_document_sequence
from apps.organizations.models import LegalEntity, OrganizationMembership, Warehouse
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.purchasing.models import AccountingTreatment, WorkOrderType
from apps.purchasing.services import (
    accept_subcontract_receipt,
    add_purchase_order_line,
    add_receipt_output_line,
    add_work_order_output,
    approve_work_order,
    confirm_purchase_order,
    create_draft_purchase_order,
    create_draft_subcontract_receipt,
    create_draft_work_order,
    submit_work_order,
)
from apps.purchasing.services.categories import create_purchase_category
from apps.quality.models import InspectionType
from apps.quality.selectors import subcontract_pass_authorization
from apps.quality.services import add_inspection_line, create_inspection, post_inspection
from apps.sales.models import DiscountType
from apps.sales.services import (
    add_draft_delivery_line,
    confirm_sales_order,
    create_draft_delivery,
    create_draft_sales_order,
    post_delivery,
)
from apps.warehouse.models import (
    InventoryValuationState,
    MovementDirection,
    MovementType,
    StockMovement,
    ValuationStatus,
)
from apps.warehouse.services import (
    add_internal_consumption_line,
    add_purchase_receipt_line,
    add_sales_issue_line,
    add_stock_count_line,
    add_subcontract_warehouse_receipt_line,
    add_supplier_return_line,
    approve_stock_count,
    create_internal_consumption,
    create_purchase_receipt,
    create_sales_issue,
    create_stock_count,
    create_subcontract_warehouse_receipt,
    create_supplier_return,
    mark_stock_count_counted,
    post_internal_consumption,
    post_purchase_receipt,
    post_sales_issue,
    post_stock_count,
    post_stock_movement,
    post_subcontract_warehouse_receipt,
    post_supplier_return,
)


@pytest.fixture
def foundation():
    historical_effective_from = date(2026, 1, 1)
    entity = LegalEntity.objects.create(
        code="6C", name="6C Entity", effective_from=historical_effective_from
    )
    user = (
        __import__("django.contrib.auth", fromlist=["get_user_model"])
        .get_user_model()
        .objects.create_user("6c@example.com", "password")
    )
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    user.user_permissions.add(
        Permission.objects.get(codename="approve_stockcount"),
        Permission.objects.get(codename="post_stockcount"),
    )
    vendor = BusinessPartner.objects.create(
        legal_entity=entity,
        code="V6C",
        display_name="Vendor",
        effective_from=historical_effective_from,
    )
    PartnerRole.objects.create(
        partner=vendor,
        role_type=PartnerRoleType.VENDOR,
        effective_from=historical_effective_from,
    )
    customer = BusinessPartner.objects.create(
        legal_entity=entity,
        code="C6C",
        display_name="Customer",
        effective_from=historical_effective_from,
    )
    PartnerRole.objects.create(
        partner=customer,
        role_type=PartnerRoleType.CUSTOMER,
        effective_from=historical_effective_from,
    )
    uom = UOM.objects.create(
        code="PCS6C",
        name="Pieces",
        dimension="COUNT",
        effective_from=historical_effective_from,
    )
    item = Item.objects.create(
        legal_entity=entity,
        code="ITEM6C",
        name="Inventory",
        uom=uom,
        purchase_eligible=True,
        sales_eligible=True,
        inventory_eligible=True,
        effective_from=historical_effective_from,
    )
    warehouse = Warehouse.objects.create(
        legal_entity=entity,
        code="WH6C",
        name="Warehouse",
        effective_from=historical_effective_from,
    )
    create_document_sequence(
        legal_entity=entity,
        document_type="PURCHASE_ORDER",
        name="PO",
        prefix="PO",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
        effective_from=historical_effective_from,
    )
    create_document_sequence(
        legal_entity=entity,
        document_type="SALES_ORDER",
        name="SO",
        prefix="SO",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
        effective_from=historical_effective_from,
    )
    create_document_sequence(
        legal_entity=entity,
        document_type="SALES_DELIVERY",
        name="SJ",
        prefix="SJ",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
        effective_from=historical_effective_from,
    )
    category = create_purchase_category(
        legal_entity=entity,
        code="INV6C",
        name="Inventory",
        accounting_treatment=AccountingTreatment.INVENTORY,
        effective_from=historical_effective_from,
    )
    return entity, user, vendor, customer, item, warehouse, category


def _opening(entity, user, item, warehouse, qty, cost, key):
    return post_stock_movement(
        legal_entity=entity,
        warehouse=warehouse,
        item=item,
        direction=MovementDirection.IN,
        movement_type=MovementType.PURCHASE_RECEIPT,
        quantity=qty,
        source_module="test",
        source_type="OPENING",
        source_document_id=key,
        source_line_id=key,
        source_key=key,
        transaction_date=date(2026, 8, 28),
        actor=user,
        unit_cost=cost,
        total_value=qty * cost,
        idempotency_key=f"idem-{key}",
    )


@pytest.mark.django_db
def test_purchase_receipt_is_partial_snapshot_costed_and_treatment_scoped(foundation):
    entity, user, vendor, _, item, warehouse, category = foundation
    order = create_draft_purchase_order(
        legal_entity=entity, vendor=vendor, document_date=date(2026, 8, 28), actor=user
    )
    line = add_purchase_order_line(
        order,
        purchase_category=category,
        item=item,
        quantity=10,
        unit_price=Decimal("20000"),
        actor=user,
    )
    confirm_purchase_order(order, actor=user)
    receipt = create_purchase_receipt(
        legal_entity=entity,
        warehouse=warehouse,
        purchase_order=order,
        receipt_date=date(2026, 8, 28),
        actor=user,
    )
    add_purchase_receipt_line(receipt, purchase_order_line=line, quantity=6, actor=user)
    post_purchase_receipt(receipt, actor=user, idempotency_key="po-rec-1")
    assert InventoryValuationState.objects.get(
        item=item, warehouse=warehouse
    ).inventory_value == Decimal("120000")
    second = create_purchase_receipt(
        legal_entity=entity,
        warehouse=warehouse,
        purchase_order=order,
        receipt_date=date(2026, 8, 28),
        actor=user,
    )
    add_purchase_receipt_line(second, purchase_order_line=line, quantity=4, actor=user)
    post_purchase_receipt(second, actor=user, idempotency_key="po-rec-2")
    assert InventoryValuationState.objects.get(
        item=item, warehouse=warehouse
    ).quantity_on_hand == Decimal("10")
    with pytest.raises(ValidationError):
        third = create_purchase_receipt(
            legal_entity=entity,
            warehouse=warehouse,
            purchase_order=order,
            receipt_date=date(2026, 8, 28),
            actor=user,
        )
        add_purchase_receipt_line(third, purchase_order_line=line, quantity=1, actor=user)


@pytest.mark.django_db
def test_sales_issue_owns_out_and_preserves_delivery_history(foundation):
    entity, user, _, customer, item, warehouse, _ = foundation
    _opening(entity, user, item, warehouse, Decimal("10"), Decimal("15000"), "sales-open")
    order = create_draft_sales_order(
        legal_entity=entity,
        customer=customer,
        document_date=date(2026, 8, 28),
        lines=[
            {
                "item": item,
                "quantity": 6,
                "unit_price": 100,
                "discount_type": DiscountType.PERCENT,
                "discount_value": 0,
            }
        ],
        actor=user,
    )
    confirm_sales_order(order, actor=user)
    delivery = create_draft_delivery(
        legal_entity=entity, customer=customer, delivery_date=date(2026, 8, 28), actor=user
    )
    delivery_line = add_draft_delivery_line(
        delivery, source_sales_order_line=order.lines.get(), quantity=6, actor=user
    )
    post_delivery(delivery, actor=user, idempotency_key="delivery-6c")
    issue = create_sales_issue(
        legal_entity=entity, warehouse=warehouse, sales_delivery=delivery, actor=user
    )
    add_sales_issue_line(issue, sales_delivery_line=delivery_line, quantity=4, actor=user)
    post_sales_issue(issue, actor=user, idempotency_key="issue-6c-1")
    assert issue.lines.get().unit_cost == Decimal("15000")
    assert delivery_line.quantity == Decimal("6")
    assert InventoryValuationState.objects.get(
        item=item, warehouse=warehouse
    ).quantity_on_hand == Decimal("6")
    followup = create_sales_issue(
        legal_entity=entity, warehouse=warehouse, sales_delivery=delivery, actor=user
    )
    add_sales_issue_line(followup, sales_delivery_line=delivery_line, quantity=2, actor=user)
    post_sales_issue(followup, actor=user, idempotency_key="issue-6c-2")
    with pytest.raises(ValidationError):
        excess = create_sales_issue(
            legal_entity=entity, warehouse=warehouse, sales_delivery=delivery, actor=user
        )
        add_sales_issue_line(excess, sales_delivery_line=delivery_line, quantity=1, actor=user)


@pytest.mark.django_db
def test_internal_consumption_and_supplier_return_are_warehouse_only(foundation):
    entity, user, vendor, _, item, warehouse, category = foundation
    _opening(entity, user, item, warehouse, Decimal("20"), Decimal("5000"), "internal-open")
    consumption = create_internal_consumption(
        legal_entity=entity,
        warehouse=warehouse,
        transaction_date=date(2026, 8, 28),
        purpose="Packaging",
        reason="Documented use",
        actor=user,
    )
    add_internal_consumption_line(consumption, item=item, quantity=3, actor=user)
    post_internal_consumption(consumption, actor=user, idempotency_key="internal-6c")
    assert (
        StockMovement.objects.filter(movement_type=MovementType.INTERNAL_CONSUMPTION).count() == 1
    )
    order = create_draft_purchase_order(
        legal_entity=entity, vendor=vendor, document_date=date(2026, 8, 28), actor=user
    )
    line = add_purchase_order_line(
        order, purchase_category=category, item=item, quantity=10, unit_price=5000, actor=user
    )
    confirm_purchase_order(order, actor=user)
    supplier_return = create_supplier_return(
        legal_entity=entity,
        warehouse=warehouse,
        supplier=vendor,
        transaction_date=date(2026, 8, 28),
        reason="Damaged",
        actor=user,
        purchase_order=order,
    )
    add_supplier_return_line(
        supplier_return, item=item, quantity=4, purchase_order_line=line, actor=user
    )
    post_supplier_return(supplier_return, actor=user, idempotency_key="return-6c")
    assert InventoryValuationState.objects.get(
        item=item, warehouse=warehouse
    ).quantity_on_hand == Decimal("13")
    assert StockMovement.objects.filter(movement_type=MovementType.SUPPLIER_RETURN).count() == 1


@pytest.mark.django_db
def test_stock_count_posts_variance_and_blocks_stale_snapshot(foundation):
    entity, user, _, _, item, warehouse, _ = foundation
    _opening(entity, user, item, warehouse, Decimal("10"), Decimal("15000"), "count-open")
    count = create_stock_count(
        legal_entity=entity, warehouse=warehouse, count_date=date(2026, 8, 28), actor=user
    )
    add_stock_count_line(count, item=item, actor=user)
    line = count.lines.get()
    from apps.warehouse.services import record_stock_count_line

    record_stock_count_line(line, counted_quantity=8, actor=user)
    mark_stock_count_counted(count, actor=user)
    approve_stock_count(count, actor=user)
    post_stock_count(count, actor=user, idempotency_key="count-6c")
    assert StockMovement.objects.filter(movement_type=MovementType.OPNAME_LOSS).count() == 1
    assert InventoryValuationState.objects.get(
        item=item, warehouse=warehouse
    ).quantity_on_hand == Decimal("8")


@pytest.mark.django_db
def test_subcontract_receipt_is_quality_pass_limited_and_pending_cost_safe(foundation):
    entity, user, vendor, _, item, warehouse, _ = foundation
    item.production_eligible = True
    item.save(update_fields=("production_eligible",))
    create_document_sequence(
        legal_entity=entity,
        document_type="WORK_ORDER",
        name="SPK",
        prefix="SPK",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
        effective_from=date(2026, 1, 1),
    )
    create_document_sequence(
        legal_entity=entity,
        document_type="SUBCONTRACT_RECEIPT",
        name="TM",
        prefix="TM",
        format_template="{prefix}-{yyyymmdd}-{seq}",
        padding=3,
        effective_from=date(2026, 1, 1),
    )
    order = create_draft_work_order(
        legal_entity=entity,
        document_date=date(2026, 8, 28),
        work_order_type=WorkOrderType.SUBCONTRACT,
        vendor=vendor,
        actor=user,
    )
    output = add_work_order_output(order, item=item, target_quantity=10, actor=user)
    submit_work_order(order, actor=user)
    approve_work_order(order, actor=user)
    source_receipt = create_draft_subcontract_receipt(
        work_order=order, receipt_date=date(2026, 8, 28), actor=user
    )
    add_receipt_output_line(source_receipt, output=output, accepted_quantity=10, actor=user)
    accept_subcontract_receipt(source_receipt, actor=user, idempotency_key="sub-accept-6c")
    source_line = source_receipt.output_lines.get()
    employee = Employee.objects.create(legal_entity=entity, employee_code="QC6C", display_name="QC")
    inspection = create_inspection(
        legal_entity=entity,
        inspection_type=InspectionType.SUBCONTRACT_RECEIPT,
        source_module="purchasing",
        source_type="SUBCONTRACT_RECEIPT",
        source_document_id=source_receipt.pk,
        source_key="QC-SUB-6C",
        inspection_date=date(2026, 8, 28),
        inspector=employee,
        actor=user,
    )
    add_inspection_line(
        inspection,
        source_line_id=str(source_line.pk),
        subcontract_receipt_line=source_line,
        work_order_output=output,
        item=item,
        qty_presented=10,
        qty_inspected=10,
        qty_pass=7,
        qty_reject=3,
        reason_text="Rejected output",
        actor=user,
    )
    post_inspection(inspection, actor=user, idempotency_key="qc-sub-6c")
    assert subcontract_pass_authorization(source_line)["remaining_pass_quantity"] == Decimal("7")
    receipt = create_subcontract_warehouse_receipt(
        legal_entity=entity,
        warehouse=warehouse,
        subcontract_receipt=source_receipt,
        receipt_date=date(2026, 8, 28),
        actor=user,
    )
    add_subcontract_warehouse_receipt_line(
        receipt, subcontract_receipt_line=source_line, quantity=7, actor=user
    )
    post_subcontract_warehouse_receipt(receipt, actor=user, idempotency_key="sub-wh-6c")
    state = InventoryValuationState.objects.get(item=item, warehouse=warehouse)
    assert state.quantity_on_hand == Decimal("7")
    assert state.valuation_status == ValuationStatus.PENDING_VALUATION
    with pytest.raises(ValidationError):
        followup = create_subcontract_warehouse_receipt(
            legal_entity=entity,
            warehouse=warehouse,
            subcontract_receipt=source_receipt,
            receipt_date=date(2026, 8, 28),
            actor=user,
        )
        add_subcontract_warehouse_receipt_line(
            followup, subcontract_receipt_line=source_line, quantity=1, actor=user
        )


@pytest.mark.django_db
def test_phase6c_routes_are_authenticated_permission_aware_and_get_read_only(client, foundation):
    _, user, _, _, _, _, _ = foundation
    client.force_login(user)
    routes = (
        ("warehouse:dashboard", "view_inventoryvaluationstate"),
        ("warehouse:stock-list", "view_inventoryvaluationstate"),
        ("warehouse:movement-list", "view_stockmovement"),
        ("warehouse:purchase-receipt-list", "view_warehousepurchasereceipt"),
        ("warehouse:subcontract-receipt-list", "view_warehousesubcontractreceipt"),
        ("warehouse:sales-issue-list", "view_warehousesalesissue"),
        ("warehouse:stock-opname-list", "view_stockcount"),
        ("warehouse:internal-consumption-list", "view_internalconsumption"),
        ("warehouse:adjustment-list", "view_inventoryadjustment"),
        ("warehouse:supplier-return-list", "view_supplierreturn"),
        ("warehouse:reconciliation", "view_inventoryvaluationstate"),
    )
    before = (StockMovement.objects.count(), InventoryValuationState.objects.count())
    assert client.get(reverse("home:home")).status_code == 200
    for name, codename in routes:
        user.user_permissions.clear()
        assert client.get(reverse(name)).status_code == 403
        user.user_permissions.add(Permission.objects.get(codename=codename))
        assert client.get(reverse(name)).status_code == 200
    assert (StockMovement.objects.count(), InventoryValuationState.objects.count()) == before
