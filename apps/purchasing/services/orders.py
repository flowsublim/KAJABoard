from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.services.audit import record_audit_event
from apps.core.services.numbering import allocate_document_number
from apps.partners.models import BusinessPartner, PartnerRoleType
from apps.purchasing.models import (
    AccountingTreatment,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderState,
)

MONEY = Decimal("0.01")


def _money(value):
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _audit(obj, action, actor=None, reason=""):
    record_audit_event(
        action=action,
        target_type=obj._meta.label_lower,
        target_id=obj.pk,
        actor=actor,
        source="purchasing.service",
        reason=reason,
    )


def _effective(obj, day):
    return (
        obj.effective_from <= day
        and (obj.effective_to is None or obj.effective_to >= day)
        and (day < timezone.localdate() or obj.is_active)
    )


def _draft(order):
    if order.state != PurchaseOrderState.DRAFT:
        raise ValidationError("Only DRAFT Purchase Orders can be edited.")


def _vendor(vendor, entity, day):
    if vendor.legal_entity_id != entity.id or not _effective(vendor, day):
        raise ValidationError({"vendor": "Vendor is not effective."})
    roles = vendor.roles.filter(role_type=PartnerRoleType.VENDOR, effective_from__lte=day).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=day)
    )
    if day >= timezone.localdate():
        roles = roles.filter(is_active=True)
    if not roles.exists():
        raise ValidationError({"vendor": "Vendor requires an effective VENDOR role."})


def _totals(order):
    sums = order.lines.aggregate(
        a=Sum("line_amount"), d=Sum("discount_amount"), t=Sum("line_tax_amount")
    )
    order.subtotal = _money(sums["a"])
    order.discount_total = _money(sums["d"])
    order.tax_total = _money(sums["t"])
    order.freight_amount = _money(order.freight_amount)
    order.grand_total = _money(
        order.subtotal - order.discount_total + order.tax_total + order.freight_amount
    )


@transaction.atomic
def create_draft_purchase_order(*, actor=None, idempotency_key="", **values):
    entity = (
        values["legal_entity"]
        .__class__.objects.select_for_update()
        .get(pk=values["legal_entity"].pk)
    )
    vendor = BusinessPartner.objects.prefetch_related("roles").get(pk=values["vendor"].pk)
    day = values["document_date"]
    _vendor(vendor, entity, day)
    project = values.get("project")
    if project and (
        project.legal_entity_id != entity.id or project.state not in {"DRAFT", "ACTIVE", "ON_HOLD"}
    ):
        raise ValidationError({"project": "Project is not eligible."})
    allocation = allocate_document_number(
        entity,
        "PURCHASE_ORDER",
        business_date=day,
        request_key=f"purchase:{idempotency_key}" if idempotency_key else "",
        actor=actor,
    )
    order = PurchaseOrder(
        legal_entity=entity,
        document_allocation=allocation,
        document_number=allocation.number,
        document_date=day,
        vendor=vendor,
        vendor_code_snapshot=vendor.code,
        vendor_name_snapshot=vendor.display_name,
        vendor_reference=str(values.get("vendor_reference", "") or "").strip(),
        project=project,
        expected_date=values.get("expected_date"),
        currency=str(values.get("currency", entity.reporting_currency)).upper(),
        freight_amount=_money(values.get("freight_amount")),
        notes=str(values.get("notes", "") or "").strip(),
        created_by=actor,
    )
    order.full_clean()
    order.save()
    _audit(order, "purchasing.purchaseorder.created", actor)
    return order


@transaction.atomic
def add_purchase_order_line(
    order,
    *,
    purchase_category,
    quantity,
    unit_price,
    item=None,
    discount_amount=0,
    tax_rate=0,
    notes="",
    actor=None,
):
    order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    _draft(order)
    category = purchase_category.__class__.objects.select_related("cost_center").get(
        pk=purchase_category.pk
    )
    if category.legal_entity_id != order.legal_entity_id or not _effective(
        category, order.document_date
    ):
        raise ValidationError({"purchase_category": "Purchase Category is not effective."})
    if (
        category.accounting_treatment in {AccountingTreatment.EXPENSE, AccountingTreatment.SERVICE}
        and not category.cost_center
    ):
        raise ValidationError({"purchase_category": "EXPENSE/SERVICE requires Cost Center."})
    if item and (
        item.legal_entity_id != order.legal_entity_id
        or not _effective(item, order.document_date)
        or not item.purchase_eligible
    ):
        raise ValidationError({"item": "Item is not purchase eligible."})
    qty = Decimal(str(quantity))
    price = Decimal(str(unit_price))
    discount = _money(discount_amount)
    rate = Decimal(str(tax_rate))
    if qty <= 0 or price < 0 or discount < 0 or rate < 0:
        raise ValidationError("Quantity must be positive and values cannot be negative.")
    amount = _money(qty * price)
    if discount > amount:
        raise ValidationError({"discount_amount": "Discount cannot exceed line amount."})
    tax = _money((amount - discount) * rate / Decimal("100"))
    line = PurchaseOrderLine(
        purchase_order=order,
        line_number=order.lines.count() + 1,
        item=item,
        purchase_category=category,
        item_code_snapshot=item.code if item else "",
        item_name_snapshot=item.name if item else "",
        uom_code_snapshot=item.uom.code if item else "",
        category_code_snapshot=category.code,
        category_name_snapshot=category.name,
        accounting_treatment_snapshot=category.accounting_treatment,
        cost_center_snapshot=category.cost_center,
        inventory_classification_snapshot=category.inventory_classification,
        asset_class_reference_snapshot=category.asset_class_reference,
        snapshot_production=category.snapshot_production,
        accounting_mapping_key_snapshot=category.default_accounting_mapping_key,
        quantity=qty,
        unit_price=price,
        discount_amount=discount,
        tax_rate=rate,
        line_amount=amount,
        line_tax_amount=tax,
        line_total=_money(amount - discount + tax),
        notes=str(notes or "").strip(),
    )
    line.full_clean()
    line.save()
    _totals(order)
    order.save()
    _audit(line, "purchasing.purchaseorderline.added", actor)
    return line


@transaction.atomic
def confirm_purchase_order(order, *, actor=None):
    order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    _draft(order)
    if not order.lines.exists():
        raise ValidationError("A Purchase Order needs at least one line.")
    order.state = PurchaseOrderState.CONFIRMED
    order.confirmed_by = actor
    order.confirmed_at = timezone.now()
    order.save()
    _audit(order, "purchasing.purchaseorder.confirmed", actor)
    return order


@transaction.atomic
def cancel_purchase_order(order, *, actor=None, reason=""):
    if not str(reason).strip():
        raise ValidationError({"reason": "Cancellation reason is required."})
    order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if order.state not in {PurchaseOrderState.DRAFT, PurchaseOrderState.CONFIRMED}:
        raise ValidationError("This Purchase Order cannot be cancelled.")
    order.state = PurchaseOrderState.CANCELLED
    order.cancelled_by = actor
    order.cancelled_at = timezone.now()
    order.save()
    _audit(order, "purchasing.purchaseorder.cancelled", actor, reason)
    return order
