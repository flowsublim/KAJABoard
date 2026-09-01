from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.catalog.models import UOM, Item
from apps.channels.models import Store
from apps.core.models import SequenceResetMode
from apps.core.services.numbering import allocate_document_number, create_document_sequence
from apps.finance.models import (
    AccountType,
    DCDirection,
    JournalEntry,
    JournalLine,
    MappingDimensionType,
    NormalBalance,
    PayableEntry,
    ReceivableEntry,
)
from apps.finance.selectors import (
    coa_accounts,
    coa_mappings,
    general_ledger,
    payables,
    receivables,
    reconciliation,
)
from apps.finance.services import (
    create_coa_account,
    create_coa_mapping,
    pos_candidate_readiness,
    post_journal,
    post_omni_completion,
    post_sales_invoice,
    post_warehouse_valuation,
    reverse_journal,
    warehouse_valuation_readiness,
)
from apps.omnichannel.models import OmniOperationalStatus, OmniOrder, OmniRevenueEvent
from apps.organizations.models import LegalEntity, OrganizationMembership, Warehouse
from apps.partners.models import BusinessPartner, PartnerRole, PartnerRoleType
from apps.purchasing.models import PurchaseOrder, PurchaseOrderState
from apps.sales.models import (
    InvoiceSourceMode,
    SalesInvoice,
    SalesInvoiceDocumentKind,
    SalesInvoiceState,
)
from apps.sales.selectors import finance_invoice_candidates
from apps.warehouse.models import (
    MovementDirection,
    MovementType,
    StockMovement,
    ValuationStatus,
)

pytestmark = pytest.mark.django_db

BUSINESS_DATE = date(2026, 9, 1)


@pytest.fixture
def foundation():
    entity = LegalEntity.objects.create(
        code="8A2", name="Finance Phase 8A2", reporting_currency="IDR"
    )
    user = get_user_model().objects.create_user("phase8a2@example.com", "password")
    OrganizationMembership.objects.create(user=user, legal_entity=entity)
    customer = BusinessPartner.objects.create(
        legal_entity=entity, code="CUST-8A2", display_name="Customer 8A2"
    )
    PartnerRole.objects.create(
        partner=customer,
        role_type=PartnerRoleType.CUSTOMER,
        effective_from=date(2026, 1, 1),
    )
    vendor = BusinessPartner.objects.create(
        legal_entity=entity, code="VEND-8A2", display_name="Vendor 8A2"
    )
    PartnerRole.objects.create(
        partner=vendor,
        role_type=PartnerRoleType.VENDOR,
        effective_from=date(2026, 1, 1),
    )
    store = Store.objects.create(
        legal_entity=entity,
        code="STORE-8A2",
        name="Store 8A2",
        channel="SHOPEE",
        finance_dimension="STORE-8A2",
        effective_from=date(2026, 1, 1),
    )
    uom = UOM.objects.create(code="PCS-8A2", name="Pieces 8A2", dimension="COUNT")
    item = Item.objects.create(
        legal_entity=entity,
        code="ITEM-8A2",
        name="Item 8A2",
        uom=uom,
        sales_eligible=True,
        purchase_eligible=True,
        inventory_eligible=True,
        effective_from=date(2026, 1, 1),
    )
    warehouse = Warehouse.objects.create(
        legal_entity=entity,
        code="WH-8A2",
        name="Warehouse 8A2",
        effective_from=date(2026, 1, 1),
    )
    return {
        "entity": entity,
        "user": user,
        "customer": customer,
        "vendor": vendor,
        "store": store,
        "item": item,
        "warehouse": warehouse,
    }


def add_mappings(foundation, module, event, roles):
    mappings = {}
    for index, (role, dc) in enumerate(roles, 1):
        account = create_coa_account(
            legal_entity=foundation["entity"],
            account_code=f"{module[:2]}-{event[:8]}-{index}",
            account_name=f"{event} {role}",
            account_type=(AccountType.REVENUE if dc == DCDirection.CREDIT else AccountType.ASSET),
            normal_balance=(
                NormalBalance.CREDIT if dc == DCDirection.CREDIT else NormalBalance.DEBIT
            ),
            is_control_account=role in {"AR_CONTROL", "RECEIVABLE", "INVENTORY"},
            effective_from=date(2026, 1, 1),
        )
        mappings[role] = create_coa_mapping(
            legal_entity=foundation["entity"],
            module_code=module,
            event_code=event,
            dimension_type=MappingDimensionType.DEFAULT,
            dimension_value="DEFAULT",
            line_role=role,
            dc=dc,
            account=account,
            effective_from=date(2026, 1, 1),
        )
    return mappings


def post_basic_journal(foundation, *, source_key="TEST|1", ar=False):
    add_mappings(
        foundation,
        "FINANCE_TEST",
        "TEST_EVENT",
        (("TEST_DEBIT", DCDirection.DEBIT), ("TEST_CREDIT", DCDirection.CREDIT)),
    )
    return post_journal(
        legal_entity=foundation["entity"],
        source_key=source_key,
        source_module="FINANCE_TEST",
        source_document_type="TestSource",
        source_document_id="SOURCE-1",
        event_code="TEST_EVENT",
        accounting_date=BUSINESS_DATE,
        lines=(
            {"line_role": "TEST_DEBIT", "dc": "DEBIT", "amount": Decimal("100000")},
            {"line_role": "TEST_CREDIT", "dc": "CREDIT", "amount": Decimal("100000")},
        ),
        actor=foundation["user"],
        source_reference={"source": "SOURCE-1"},
        ar=(
            {
                "amount": Decimal("100000"),
                "currency": "IDR",
                "partner": foundation["customer"],
            }
            if ar
            else None
        ),
    )


def create_sales_invoice_source(foundation):
    create_document_sequence(
        legal_entity=foundation["entity"],
        document_type="SALES_INVOICE",
        name="Sales Invoice 8A2",
        prefix="INV8A2",
        format_template="{prefix}-{yyyy}-{seq}",
        padding=4,
        reset_mode=SequenceResetMode.YEARLY,
        effective_from=date(2026, 1, 1),
    )
    allocation = allocate_document_number(
        foundation["entity"], "SALES_INVOICE", business_date=BUSINESS_DATE
    )
    return SalesInvoice.objects.create(
        legal_entity=foundation["entity"],
        document_allocation=allocation,
        document_number=allocation.number,
        invoice_date=BUSINESS_DATE,
        customer=foundation["customer"],
        customer_code_snapshot=foundation["customer"].code,
        customer_name_snapshot=foundation["customer"].display_name,
        source_mode=InvoiceSourceMode.SALES_ORDER,
        document_kind=SalesInvoiceDocumentKind.INVOICE,
        state=SalesInvoiceState.CONFIRMED,
        subtotal=Decimal("125000"),
        grand_total=Decimal("125000"),
        confirmed_by=foundation["user"],
        confirmed_at=timezone.now(),
    )


def create_omni_revenue_source(foundation):
    order = OmniOrder.objects.create(
        legal_entity=foundation["entity"],
        marketplace="SHOPEE",
        external_store_name="Store 8A2",
        store=foundation["store"],
        external_order_number="ORDER-8A2",
        source_identity_key="8A2|ORDER-8A2",
        order_date=date(2026, 8, 31),
        completion_date=BUSINESS_DATE,
        raw_status="Selesai",
        normalized_status=OmniOperationalStatus.COMPLETED,
    )
    return OmniRevenueEvent.objects.create(
        legal_entity=foundation["entity"],
        store=foundation["store"],
        marketplace="SHOPEE",
        order=order,
        external_order_number=order.external_order_number,
        completion_date=BUSINESS_DATE,
        gross_eligible_amount=Decimal("200000"),
        source_lineage={"order_id": str(order.pk), "source_hash": "8A2"},
        event_key=f"OMNI_REV|{foundation['store'].pk}|{order.external_order_number}",
        created_by=foundation["user"],
    )


def create_stock_movement(foundation, *, valued=True):
    return StockMovement.objects.create(
        legal_entity=foundation["entity"],
        item=foundation["item"],
        warehouse=foundation["warehouse"],
        direction=MovementDirection.IN,
        movement_type=MovementType.PURCHASE_RECEIPT,
        quantity=Decimal("2"),
        uom_code_snapshot="PCS-8A2",
        unit_cost=Decimal("50000") if valued else None,
        total_value=Decimal("100000") if valued else None,
        valuation_status=(ValuationStatus.READY if valued else ValuationStatus.PENDING_VALUATION),
        source_module="purchasing",
        source_type="PURCHASE_RECEIPT",
        source_document_id="RECEIPT-8A2",
        source_line_id="LINE-1",
        source_key="WH|8A2|1",
        transaction_date=BUSINESS_DATE,
        posting_sequence=1,
        posted_at=timezone.now(),
        created_by=foundation["user"],
        posted_by=foundation["user"],
    )


def test_journal_posting_idempotency_mapping_block_and_reversal(foundation):
    journal = post_basic_journal(foundation)
    replay = post_journal(
        legal_entity=foundation["entity"],
        source_key="TEST|1",
        source_module="IGNORED_ON_REPLAY",
        source_document_type="Ignored",
        source_document_id="ignored",
        event_code="IGNORED",
        accounting_date=BUSINESS_DATE,
        lines=(),
        actor=foundation["user"],
    )
    assert replay.pk == journal.pk
    assert journal.total_debit == journal.total_credit == Decimal("100000")
    assert JournalEntry.objects.count() == 1
    assert journal.lines.count() == 2
    assert journal.lines.first().mapping_snapshot["business_date"] == "2026-09-01"

    with pytest.raises(ValidationError, match="BLOCKED_MAPPING"):
        post_journal(
            legal_entity=foundation["entity"],
            source_key="MISSING|1",
            source_module="MISSING",
            source_document_type="Missing",
            source_document_id="1",
            event_code="MISSING_EVENT",
            accounting_date=BUSINESS_DATE,
            lines=(
                {"line_role": "ONE", "dc": "DEBIT", "amount": Decimal("1")},
                {"line_role": "TWO", "dc": "CREDIT", "amount": Decimal("1")},
            ),
            actor=foundation["user"],
        )
    assert JournalEntry.objects.count() == 1

    original_lines = list(journal.lines.values_list("debit", "credit", "account_id"))
    reversal = reverse_journal(journal, actor=foundation["user"], source_key="TEST|1|REV")
    replay_reversal = reverse_journal(journal, actor=foundation["user"], source_key="TEST|1|REV")
    assert reversal.pk == replay_reversal.pk
    assert list(reversal.lines.values_list("debit", "credit")) == [
        (credit, debit) for debit, credit, _ in original_lines
    ]
    journal.refresh_from_db()
    assert list(journal.lines.values_list("debit", "credit", "account_id")) == original_lines
    assert JournalEntry.objects.count() == 2


def test_sales_invoice_adapter_posts_ar_on_invoice_date_once(foundation):
    add_mappings(
        foundation,
        "SALES",
        "SALES_INVOICE",
        (("AR_CONTROL", DCDirection.DEBIT), ("REVENUE", DCDirection.CREDIT)),
    )
    invoice = create_sales_invoice_source(foundation)
    assert list(finance_invoice_candidates(foundation["user"], invoice=invoice)) == [invoice]

    journal = post_sales_invoice(invoice, actor=foundation["user"])
    replay = post_sales_invoice(invoice, actor=foundation["user"])

    assert replay.pk == journal.pk
    assert journal.accounting_date == invoice.invoice_date
    assert journal.source_document_id == str(invoice.pk)
    assert journal.source_reference == {"invoice_number": invoice.document_number}
    assert journal.receivable.partner == foundation["customer"]
    assert journal.receivable.original_amount == invoice.grand_total
    assert JournalEntry.objects.count() == 1
    assert ReceivableEntry.objects.count() == 1


def test_omni_completion_adapter_posts_store_ar_on_completion_date_once(foundation):
    add_mappings(
        foundation,
        "OMNI",
        "OMNI_ORDER_COMPLETED",
        (("RECEIVABLE", DCDirection.DEBIT), ("REVENUE", DCDirection.CREDIT)),
    )
    event = create_omni_revenue_source(foundation)

    journal = post_omni_completion(event, actor=foundation["user"])
    replay = post_omni_completion(event, actor=foundation["user"])

    assert replay.pk == journal.pk
    assert journal.accounting_date == event.completion_date == BUSINESS_DATE
    assert journal.accounting_date != event.order.order_date
    assert journal.source_document_id == str(event.pk)
    assert journal.source_reference["order_id"] == str(event.order_id)
    assert journal.receivable.store == foundation["store"]
    assert journal.receivable.partner is None
    assert JournalEntry.objects.count() == 1
    assert ReceivableEntry.objects.count() == 1


def test_confirmed_purchase_order_remains_non_ap_commitment(foundation):
    create_document_sequence(
        legal_entity=foundation["entity"],
        document_type="PURCHASE_ORDER",
        name="Purchase Order 8A2",
        prefix="PO8A2",
        format_template="{prefix}-{yyyy}-{seq}",
        padding=4,
        reset_mode=SequenceResetMode.YEARLY,
        effective_from=date(2026, 1, 1),
    )
    allocation = allocate_document_number(
        foundation["entity"], "PURCHASE_ORDER", business_date=BUSINESS_DATE
    )
    PurchaseOrder.objects.create(
        legal_entity=foundation["entity"],
        document_allocation=allocation,
        document_number=allocation.number,
        document_date=BUSINESS_DATE,
        vendor=foundation["vendor"],
        vendor_code_snapshot=foundation["vendor"].code,
        vendor_name_snapshot=foundation["vendor"].display_name,
        state=PurchaseOrderState.CONFIRMED,
        grand_total=Decimal("500000"),
        confirmed_by=foundation["user"],
        confirmed_at=timezone.now(),
    )

    assert JournalEntry.objects.count() == 0
    assert PayableEntry.objects.count() == 0


def test_warehouse_authoritative_valuation_posts_exact_amount_without_stock_write(foundation):
    add_mappings(
        foundation,
        "WAREHOUSE",
        "WAREHOUSE_VALUATION",
        (("INVENTORY", DCDirection.DEBIT), ("INVENTORY_OFFSET", DCDirection.CREDIT)),
    )
    movement = create_stock_movement(foundation, valued=True)
    movement_count = StockMovement.objects.count()

    journal = post_warehouse_valuation(movement, actor=foundation["user"])
    replay = post_warehouse_valuation(movement, actor=foundation["user"])

    assert replay.pk == journal.pk
    assert journal.accounting_date == movement.transaction_date
    assert journal.total_debit == movement.total_value == Decimal("100000")
    assert journal.source_reference["stock_movement_id"] == str(movement.pk)
    assert journal.source_reference["valuation_amount"] == str(movement.total_value)
    assert StockMovement.objects.count() == movement_count
    assert reconciliation(legal_entity=foundation["entity"])["inventory"]["status"] == "MATCH"


def test_pending_warehouse_valuation_does_not_post_zero(foundation):
    movement = create_stock_movement(foundation, valued=False)

    assert warehouse_valuation_readiness(movement)["status"] == "PENDING_SOURCE"
    result = post_warehouse_valuation(movement, actor=foundation["user"])

    assert result["status"] == "PENDING_SOURCE"
    assert JournalEntry.objects.count() == 0
    assert reconciliation(legal_entity=foundation["entity"])["inventory"]["status"] == (
        "PENDING_SOURCE"
    )


def test_pos_boundary_defers_phase_8b_payment_semantics(foundation):
    for event_code in ("POS_SALE_REVENUE", "POS_COGS", "POS_TENDER"):
        result = pos_candidate_readiness(SimpleNamespace(event_code=event_code))
        assert result["status"] == "DEFERRED"

    installed_model_names = {model.__name__ for model in apps.get_models()}
    assert {"CashLedger", "BankLedger", "Payment"}.isdisjoint(installed_model_names)
    assert JournalEntry.objects.count() == 0


def test_existing_coa_exports_and_ledger_subledger_selectors_are_read_only(foundation):
    journal = post_basic_journal(foundation, ar=True)
    draft_like = JournalEntry.objects.create(
        legal_entity=foundation["entity"],
        journal_number="JRN-NONPOSTED",
        accounting_date=BUSINESS_DATE,
        event_code="NONPOSTED",
        source_module="TEST",
        source_document_type="Test",
        source_document_id="2",
        source_key="NONPOSTED|1",
        state="REVERSED",
        total_debit=Decimal("0"),
        total_credit=Decimal("0"),
        posted_at=timezone.now(),
        posted_by=foundation["user"],
    )
    before = JournalEntry.objects.count()

    assert coa_accounts(foundation["user"], legal_entity=foundation["entity"]).count() == 2
    assert coa_mappings(foundation["user"], legal_entity=foundation["entity"]).count() == 2
    rows = list(general_ledger(legal_entity=foundation["entity"]))
    ar_rows = list(receivables(legal_entity=foundation["entity"]))
    ap_rows = list(payables(legal_entity=foundation["entity"]))

    assert len(rows) == 2
    assert {row.journal_id for row in rows} == {journal.pk}
    assert rows[0].journal.source_key == "TEST|1"
    assert ar_rows == [journal.receivable]
    assert ap_rows == []
    assert draft_like.pk not in {row.journal_id for row in rows}
    assert JournalEntry.objects.count() == before


def test_reconciliation_match_difference_and_read_side_effect_safety(foundation):
    add_mappings(
        foundation,
        "SALES",
        "SALES_INVOICE",
        (("AR_CONTROL", DCDirection.DEBIT), ("REVENUE", DCDirection.CREDIT)),
    )
    invoice = create_sales_invoice_source(foundation)
    journal = post_sales_invoice(invoice, actor=foundation["user"])
    before = (JournalEntry.objects.count(), JournalLine.objects.count())

    matched = reconciliation(legal_entity=foundation["entity"])
    assert matched["journal"]["status"] == "MATCH"
    assert matched["ar"]["status"] == "MATCH"
    assert matched["ap"]["status"] == "PENDING_SOURCE"
    assert (JournalEntry.objects.count(), JournalLine.objects.count()) == before

    journal.receivable.open_amount = Decimal("100000")
    journal.receivable.save(update_fields=("open_amount", "updated_at"))
    different = reconciliation(legal_entity=foundation["entity"])
    assert different["ar"]["status"] == "DIFFERENCE"
    assert (JournalEntry.objects.count(), JournalLine.objects.count()) == before
