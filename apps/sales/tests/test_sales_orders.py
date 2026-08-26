from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.catalog.models import UOM, Item
from apps.core.models import AuditEvent, DocumentNumberAllocation, SequenceResetMode
from apps.core.services.numbering import create_document_sequence
from apps.organizations.models import LegalEntity, OrganizationMembership
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.sales.models import DiscountType, SalesOrder, SalesOrderState
from apps.sales.selectors import confirmed_sales_order_lines, sales_orders
from apps.sales.services import (
    add_draft_line,
    cancel_sales_order,
    confirm_sales_order,
    create_draft_sales_order,
    customer_credit_check_context,
    hold_sales_order,
    release_sales_order,
    update_draft_sales_order,
)

User = get_user_model()


@pytest.fixture
def entity():
    return LegalEntity.objects.create(code="KAJA", name="PT KAJA", reporting_currency="IDR")


@pytest.fixture
def user(entity):
    user = User.objects.create_user("sales@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    return user


@pytest.fixture
def uom():
    return UOM.objects.create(code="PCS", name="Pieces", dimension="COUNT")


@pytest.fixture
def customer(entity):
    partner = BusinessPartner.objects.create(
        legal_entity=entity,
        code="CUST-001",
        display_name="PT Customer",
        legal_name="PT Customer Legal",
        credit_limit=Decimal("5000000"),
    )
    PartnerRole.objects.create(partner=partner, role_type=PartnerRoleType.CUSTOMER)
    return partner


@pytest.fixture
def item(entity, uom):
    return Item.objects.create(
        legal_entity=entity,
        code="SKU-001",
        name="Finished Product",
        uom=uom,
        sales_eligible=True,
        tax_classification="STANDARD",
    )


@pytest.fixture
def numbering(entity):
    return create_document_sequence(
        legal_entity=entity,
        document_type="SALES_ORDER",
        name="Sales Order",
        prefix="SO",
        format_template="{prefix}-{yyyy}-{seq}",
        padding=4,
        reset_mode=SequenceResetMode.YEARLY,
    )


def draft_values(entity, customer, **overrides):
    values = {
        "legal_entity": entity,
        "customer": customer,
        "document_date": timezone.localdate(),
        "currency": "IDR",
    }
    values.update(overrides)
    return values


def line_values(item, **overrides):
    values = {
        "item": item,
        "quantity": Decimal("1"),
        "unit_price": Decimal("10000"),
        "discount_type": DiscountType.AMOUNT,
        "discount_value": Decimal("0"),
        "tax_rate": Decimal("0"),
    }
    values.update(overrides)
    return values


@pytest.mark.django_db
def test_customer_requires_effective_customer_role(entity, customer, numbering):
    customer.roles.all().delete()

    with pytest.raises(ValidationError, match="CUSTOMER role"):
        create_draft_sales_order(**draft_values(entity, customer))

    PartnerRole.objects.create(
        partner=customer,
        role_type=PartnerRoleType.CUSTOMER,
        effective_from=timezone.localdate() + timedelta(days=1),
    )
    with pytest.raises(ValidationError, match="CUSTOMER role"):
        create_draft_sales_order(**draft_values(entity, customer))


@pytest.mark.django_db
def test_sales_item_and_cross_entity_references_are_validated(
    entity, customer, item, uom, numbering
):
    order = create_draft_sales_order(**draft_values(entity, customer))
    item.sales_eligible = False
    item.save(update_fields=("sales_eligible", "updated_at"))
    with pytest.raises(ValidationError, match="sales eligible"):
        add_draft_line(order, **line_values(item))

    other_entity = LegalEntity.objects.create(code="OTHER", name="Other")
    other_customer = BusinessPartner.objects.create(
        legal_entity=other_entity,
        code="OTHER-CUST",
        display_name="Other Customer",
    )
    PartnerRole.objects.create(partner=other_customer, role_type=PartnerRoleType.CUSTOMER)
    with pytest.raises(ValidationError, match="legal entity"):
        create_draft_sales_order(**draft_values(entity, other_customer))

    other_item = Item.objects.create(
        legal_entity=other_entity,
        code="OTHER-SKU",
        name="Other Item",
        uom=uom,
        sales_eligible=True,
    )
    item.sales_eligible = True
    item.save(update_fields=("sales_eligible", "updated_at"))
    with pytest.raises(ValidationError, match="legal entity"):
        add_draft_line(order, **line_values(other_item))


@pytest.mark.django_db
def test_quantity_and_price_validation_and_decimal_rounding(entity, customer, item, numbering):
    with pytest.raises(ValidationError, match="greater than zero"):
        create_draft_sales_order(
            **draft_values(entity, customer), lines=[line_values(item, quantity=Decimal("0"))]
        )
    with pytest.raises(ValidationError, match="cannot be negative"):
        create_draft_sales_order(
            **draft_values(entity, customer), lines=[line_values(item, unit_price=Decimal("-1"))]
        )

    order = create_draft_sales_order(
        **draft_values(entity, customer, freight_amount=Decimal("0.99")),
        lines=[
            line_values(
                item,
                quantity=Decimal("3"),
                unit_price=Decimal("19.99"),
                discount_type=DiscountType.PERCENT,
                discount_value=Decimal("12.5"),
                tax_rate=Decimal("11"),
            )
        ],
    )
    line = order.lines.get()

    assert line.line_amount == Decimal("59.97")
    assert line.line_discount_amount == Decimal("7.50")
    assert line.line_tax_base == Decimal("52.47")
    assert line.line_tax_amount == Decimal("5.77")
    assert line.line_total == Decimal("58.24")
    assert order.grand_total == Decimal("59.23")


@pytest.mark.django_db
def test_numbering_is_configured_unique_and_create_retry_safe(entity, customer, item, numbering):
    values = draft_values(entity, customer)
    first = create_draft_sales_order(
        **values,
        lines=[line_values(item)],
        idempotency_key="sales-create-1",
    )
    replay = create_draft_sales_order(
        **values,
        lines=[line_values(item)],
        idempotency_key="sales-create-1",
    )
    second = create_draft_sales_order(
        **draft_values(entity, customer),
        lines=[line_values(item)],
        idempotency_key="sales-create-2",
    )

    assert replay.pk == first.pk
    assert first.document_number != second.document_number
    assert DocumentNumberAllocation.objects.filter(document_type="SALES_ORDER").count() == 2
    with pytest.raises(IntegrityError):
        SalesOrder.objects.filter(pk=second.pk).update(document_number=first.document_number)


@pytest.mark.django_db
def test_confirmation_snapshots_and_state_machine_protect_commercial_history(
    entity, customer, item, numbering, user
):
    order = create_draft_sales_order(
        **draft_values(entity, customer), lines=[line_values(item, unit_price=Decimal("25000"))]
    )
    with pytest.raises(ValidationError, match="immutable after Sales Order number allocation"):
        update_draft_sales_order(
            order,
            document_date=timezone.localdate() + timedelta(days=1),
            reason="Incorrect date",
        )
    confirmed = confirm_sales_order(order, actor=user, idempotency_key="confirm-1")
    replay = confirm_sales_order(order, actor=user, idempotency_key="confirm-1")

    customer.display_name = "Renamed Customer"
    customer.save(update_fields=("display_name", "updated_at"))
    item.name = "Renamed Item"
    item.save(update_fields=("name", "updated_at"))
    confirmed.refresh_from_db()
    line = confirmed.lines.get()

    assert replay.pk == confirmed.pk
    assert confirmed.state == SalesOrderState.CONFIRMED
    assert confirmed.customer_name_snapshot == "PT Customer"
    assert line.item_name_snapshot == "Finished Product"
    with pytest.raises(ValidationError, match="DRAFT"):
        update_draft_sales_order(confirmed, customer_po_reference="late", reason="Invalid")
    with pytest.raises(ValidationError, match="DRAFT"):
        add_draft_line(confirmed, **line_values(item))

    held = hold_sales_order(confirmed, actor=user, reason="Credit review")
    assert held.state == SalesOrderState.ON_HOLD
    assert (
        release_sales_order(held, actor=user, reason="Review complete").state
        == SalesOrderState.CONFIRMED
    )
    cancelled = cancel_sales_order(confirmed, actor=user, reason="Customer request")
    assert cancelled.state == SalesOrderState.CANCELLED
    with pytest.raises(ValidationError, match="DRAFT"):
        confirm_sales_order(cancelled, actor=user)


@pytest.mark.django_db
def test_confirmed_line_source_contract_scope_audit_and_no_ledger_effects(
    entity, customer, item, numbering, user
):
    order = create_draft_sales_order(
        **draft_values(entity, customer),
        lines=[line_values(item, quantity=Decimal("2"))],
        actor=user,
    )
    confirm_sales_order(order, actor=user)

    source_line = confirmed_sales_order_lines(user).get()
    assert source_line.sales_order_id == order.pk
    assert source_line.remaining_downstream_quantity == Decimal("2")
    assert list(sales_orders(user)) == [order]
    assert AuditEvent.objects.filter(
        target_id=str(order.pk), action="sales.salesorder.confirmed"
    ).exists()
    assert not any(
        model._meta.label_lower in {"warehouse.stockmovement", "finance.journalentry"}
        for model in SalesOrder._meta.apps.get_models()
    )


@pytest.mark.django_db
def test_customer_credit_hook_exposes_only_master_limit(customer):
    context = customer_credit_check_context(customer)

    assert context.credit_limit == Decimal("5000000")
    assert context.finance_exposure_available is False
    assert context.outstanding_exposure is None
