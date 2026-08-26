from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.catalog.models import UOM, Item
from apps.core.models import AuditEvent, SequenceResetMode
from apps.core.services.numbering import create_document_sequence
from apps.organizations.models import LegalEntity, OrganizationMembership
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.sales.models import (
    DiscountType,
    InvoiceSourceMode,
    SalesDeliveryState,
    SalesInvoiceDocumentKind,
    SalesInvoiceState,
)
from apps.sales.selectors import (
    delivery_lines_with_remaining,
    finance_invoice_candidates,
    posted_delivery_lines_for_invoice,
    warehouse_goods_issue_candidates,
    warehouse_goods_issue_correction_candidates,
)
from apps.sales.services import (
    add_draft_delivery_invoice_line,
    add_draft_delivery_line,
    add_draft_sales_order_invoice_line,
    cancel_delivery,
    cancel_invoice,
    confirm_invoice,
    confirm_sales_order,
    create_draft_delivery,
    create_draft_delivery_invoice,
    create_draft_sales_order,
    create_draft_sales_order_invoice,
    create_proforma,
    post_delivery,
)

User = get_user_model()


@pytest.fixture
def entity():
    return LegalEntity.objects.create(code="KAJA", name="PT KAJA", reporting_currency="IDR")


@pytest.fixture
def user(entity):
    person = User.objects.create_user("phase3b@example.com", "password")
    OrganizationMembership.objects.create(user=person, legal_entity=entity)
    return person


@pytest.fixture
def customer(entity):
    partner = BusinessPartner.objects.create(
        legal_entity=entity, code="CUST-3B", display_name="Customer 3B"
    )
    PartnerRole.objects.create(partner=partner, role_type=PartnerRoleType.CUSTOMER)
    return partner


@pytest.fixture
def item(entity):
    uom = UOM.objects.create(code="PCS-3B", name="Pieces", dimension="COUNT")
    return Item.objects.create(
        legal_entity=entity,
        code="SKU-3B",
        name="Delivery Item",
        uom=uom,
        sales_eligible=True,
        tax_classification="STANDARD",
    )


@pytest.fixture
def sequences(entity):
    for document_type, prefix in (
        ("SALES_ORDER", "SO"),
        ("SALES_DELIVERY", "SJ"),
        ("SALES_INVOICE", "INV"),
        ("PROFORMA", "PF"),
    ):
        create_document_sequence(
            legal_entity=entity,
            document_type=document_type,
            name=document_type,
            prefix=prefix,
            format_template="{prefix}-{yyyy}-{seq}",
            padding=4,
            reset_mode=SequenceResetMode.YEARLY,
        )


def confirmed_order(entity, customer, item, user, quantity=Decimal("10")):
    order = create_draft_sales_order(
        legal_entity=entity,
        customer=customer,
        document_date=timezone.localdate(),
        lines=[
            {
                "item": item,
                "quantity": quantity,
                "unit_price": Decimal("100"),
                "discount_type": DiscountType.PERCENT,
                "discount_value": Decimal("10"),
                "tax_rate": Decimal("11"),
            }
        ],
        actor=user,
    )
    return confirm_sales_order(order, actor=user)


def draft_delivery(entity, customer, user):
    return create_draft_delivery(
        legal_entity=entity, customer=customer, delivery_date=timezone.localdate(), actor=user
    )


@pytest.mark.django_db
def test_multi_order_partial_delivery_lineage_and_warehouse_candidate(
    entity, customer, item, user, sequences
):
    first = confirmed_order(entity, customer, item, user, Decimal("5"))
    second = confirmed_order(entity, customer, item, user, Decimal("7"))
    delivery = draft_delivery(entity, customer, user)
    first_line = add_draft_delivery_line(
        delivery, source_sales_order_line=first.lines.get(), quantity=Decimal("2"), actor=user
    )
    second_line = add_draft_delivery_line(
        delivery, source_sales_order_line=second.lines.get(), quantity=Decimal("3"), actor=user
    )

    post_delivery(delivery, actor=user, idempotency_key="post-multi")
    delivery.refresh_from_db()
    assert delivery.state == SalesDeliveryState.POSTED
    candidates = warehouse_goods_issue_candidates(user, delivery=delivery)
    assert {candidate.sales_order_line_id for candidate in candidates} == {
        str(first_line.source_sales_order_line_id),
        str(second_line.source_sales_order_line_id),
    }
    assert candidates[0].identity.startswith("SALES_DELIVERY_LINE:")

    follow_up = draft_delivery(entity, customer, user)
    add_draft_delivery_line(
        follow_up, source_sales_order_line=first.lines.get(), quantity=Decimal("3"), actor=user
    )
    post_delivery(follow_up, actor=user)
    with pytest.raises(ValidationError, match="exceeds remaining"):
        excessive = draft_delivery(entity, customer, user)
        add_draft_delivery_line(
            excessive, source_sales_order_line=second.lines.get(), quantity=Decimal("5"), actor=user
        )
        post_delivery(excessive, actor=user)


@pytest.mark.django_db
def test_delivery_rejects_mixed_customer_and_cancel_restores_derived_remaining(
    entity, customer, item, user, sequences
):
    order = confirmed_order(entity, customer, item, user)
    other = BusinessPartner.objects.create(
        legal_entity=entity, code="CUST-OTHER", display_name="Other Customer"
    )
    PartnerRole.objects.create(partner=other, role_type=PartnerRoleType.CUSTOMER)
    other_order = confirmed_order(entity, other, item, user)
    delivery = draft_delivery(entity, customer, user)
    with pytest.raises(ValidationError, match="selected customer"):
        add_draft_delivery_line(
            delivery,
            source_sales_order_line=other_order.lines.get(),
            quantity=Decimal("1"),
            actor=user,
        )
    add_draft_delivery_line(
        delivery, source_sales_order_line=order.lines.get(), quantity=Decimal("4"), actor=user
    )
    post_delivery(delivery, actor=user)
    cancel_delivery(delivery, actor=user, reason="Customer rescheduled")
    delivery.refresh_from_db()
    assert delivery.state == SalesDeliveryState.CANCELLED
    correction = warehouse_goods_issue_correction_candidates(user, delivery=delivery)
    assert correction[0].is_correction is True
    assert correction[0].identity.startswith("SALES_DELIVERY_REVERSAL:")
    remaining = delivery_lines_with_remaining(user=user, customer=customer).get()
    assert remaining.remaining_delivery_quantity == Decimal("10")


@pytest.mark.django_db
def test_delivery_rejects_cross_entity_source(entity, customer, item, user, sequences):
    other_entity = LegalEntity.objects.create(code="OTHER-3B", name="Other Entity")
    other_customer = BusinessPartner.objects.create(
        legal_entity=other_entity, code="OTHER-3B", display_name="Other Customer"
    )
    PartnerRole.objects.create(partner=other_customer, role_type=PartnerRoleType.CUSTOMER)
    other_uom = UOM.objects.create(code="OTH-3B", name="Other Pieces", dimension="COUNT")
    other_item = Item.objects.create(
        legal_entity=other_entity,
        code="OTHER-SKU-3B",
        name="Other Item",
        uom=other_uom,
        sales_eligible=True,
    )
    create_document_sequence(
        legal_entity=other_entity,
        document_type="SALES_ORDER",
        name="Other Sales Order",
        prefix="OSO",
        format_template="{prefix}-{yyyy}-{seq}",
        padding=4,
        reset_mode=SequenceResetMode.YEARLY,
    )
    other_order = confirmed_order(other_entity, other_customer, other_item, user, Decimal("2"))
    delivery = draft_delivery(entity, customer, user)
    with pytest.raises(ValidationError, match="legal entity"):
        add_draft_delivery_line(
            delivery,
            source_sales_order_line=other_order.lines.get(),
            quantity=Decimal("1"),
            actor=user,
        )


@pytest.mark.django_db
def test_delivery_invoice_quantity_controls_snapshots_and_finance_candidate(
    entity, customer, item, user, sequences
):
    order = confirmed_order(entity, customer, item, user, Decimal("8"))
    delivery = draft_delivery(entity, customer, user)
    delivery_line = add_draft_delivery_line(
        delivery, source_sales_order_line=order.lines.get(), quantity=Decimal("6"), actor=user
    )
    post_delivery(delivery, actor=user)
    invoice = create_draft_delivery_invoice(
        legal_entity=entity, customer=customer, invoice_date=timezone.localdate(), actor=user
    )
    invoice_line = add_draft_delivery_invoice_line(
        invoice, source_sales_delivery_line=delivery_line, quantity=Decimal("2"), actor=user
    )
    assert invoice_line.line_total == Decimal("199.80")
    confirm_invoice(invoice, actor=user, idempotency_key="invoice-confirm")
    item.name = "Renamed later"
    item.save(update_fields=("name", "updated_at"))
    invoice.refresh_from_db()
    assert invoice.lines.get().item_name_snapshot == "Delivery Item"
    source = posted_delivery_lines_for_invoice(user, customer=customer).get()
    assert source.remaining_invoice_quantity == Decimal("4")
    assert list(finance_invoice_candidates(user, invoice=invoice)) == [invoice]
    assert AuditEvent.objects.filter(
        target_id=str(invoice.pk), action="sales.salesinvoice.confirmed"
    ).exists()


@pytest.mark.django_db
def test_overinvoice_cancel_proforma_and_sales_order_exception(
    entity, customer, item, user, sequences
):
    order = confirmed_order(entity, customer, item, user, Decimal("5"))
    delivery = draft_delivery(entity, customer, user)
    delivery_line = add_draft_delivery_line(
        delivery, source_sales_order_line=order.lines.get(), quantity=Decimal("3"), actor=user
    )
    post_delivery(delivery, actor=user)
    invoice = create_draft_delivery_invoice(
        legal_entity=entity, customer=customer, invoice_date=timezone.localdate(), actor=user
    )
    add_draft_delivery_invoice_line(
        invoice, source_sales_delivery_line=delivery_line, quantity=Decimal("3"), actor=user
    )
    confirm_invoice(invoice, actor=user)
    excessive = create_draft_delivery_invoice(
        legal_entity=entity, customer=customer, invoice_date=timezone.localdate(), actor=user
    )
    add_draft_delivery_invoice_line(
        excessive, source_sales_delivery_line=delivery_line, quantity=Decimal("1"), actor=user
    )
    with pytest.raises(ValidationError, match="exceeds"):
        confirm_invoice(excessive, actor=user)
    cancel_invoice(invoice, actor=user, reason="Commercial correction")

    proforma = create_proforma(
        legal_entity=entity, customer=customer, invoice_date=timezone.localdate(), actor=user
    )
    add_draft_sales_order_invoice_line(
        proforma, source_sales_order_line=order.lines.get(), quantity=Decimal("5"), actor=user
    )
    confirm_invoice(proforma, actor=user)
    proforma.refresh_from_db()
    assert proforma.document_kind == SalesInvoiceDocumentKind.PROFORMA
    assert proforma.state == SalesInvoiceState.CONFIRMED
    assert not finance_invoice_candidates(user, invoice=proforma).exists()

    exception = create_draft_sales_order_invoice(
        legal_entity=entity,
        customer=customer,
        invoice_date=timezone.localdate(),
        source_exception_reason="Approved advance billing",
        actor=user,
    )
    add_draft_sales_order_invoice_line(
        exception, source_sales_order_line=order.lines.get(), quantity=Decimal("2"), actor=user
    )
    confirm_invoice(exception, actor=user)
    assert exception.source_mode == InvoiceSourceMode.SALES_ORDER
