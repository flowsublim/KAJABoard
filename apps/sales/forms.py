from django import forms

from apps.catalog.models import Item
from apps.organizations.models import BusinessUnit
from apps.organizations.selectors import accessible_legal_entities
from apps.partners.models import BusinessPartner
from apps.sales.models import (
    InvoiceSourceMode,
    SalesDelivery,
    SalesDeliveryLine,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderLine,
)
from apps.sales.selectors.deliveries import (
    delivery_lines_with_remaining,
    posted_delivery_lines_for_invoice,
    sales_order_lines_for_invoice_exception,
)


class SalesOrderForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required for material commercial changes to a draft.",
    )

    class Meta:
        model = SalesOrder
        fields = (
            "legal_entity",
            "document_date",
            "customer",
            "customer_po_reference",
            "business_unit",
            "requested_delivery_date",
            "currency",
            "freight_amount",
            "notes",
        )
        widgets = {
            "document_date": forms.DateInput(attrs={"type": "date"}),
            "requested_delivery_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        entities = accessible_legal_entities(user)
        self.fields["legal_entity"].queryset = entities
        self.fields["customer"].queryset = BusinessPartner.objects.filter(legal_entity__in=entities)
        self.fields["business_unit"].queryset = BusinessUnit.objects.filter(
            legal_entity__in=entities
        )
        if self.instance.pk:
            self.fields["legal_entity"].disabled = True
            self.fields["document_date"].disabled = True
            self.fields["change_reason"].required = True


class SalesOrderLineForm(forms.ModelForm):
    description = forms.CharField(
        required=False, max_length=1000, widget=forms.Textarea(attrs={"rows": 2})
    )
    change_reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    class Meta:
        model = SalesOrderLine
        fields = (
            "item",
            "quantity",
            "unit_price",
            "discount_type",
            "discount_value",
            "tax_rate",
            "notes",
        )
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        entities = accessible_legal_entities(user)
        self.fields["item"].queryset = Item.objects.select_related("uom").filter(
            legal_entity__in=entities
        )
        if self.instance.pk:
            self.fields["description"].initial = self.instance.description_snapshot


class SalesOrderTransitionForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))


class SalesDeliveryForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2})
    )

    class Meta:
        model = SalesDelivery
        fields = (
            "legal_entity",
            "delivery_date",
            "customer",
            "destination_snapshot",
            "expedition_reference",
            "notes",
        )
        widgets = {
            "delivery_date": forms.DateInput(attrs={"type": "date"}),
            "destination_snapshot": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        entities = accessible_legal_entities(user)
        self.fields["legal_entity"].queryset = entities
        self.fields["customer"].queryset = BusinessPartner.objects.filter(legal_entity__in=entities)
        if self.instance.pk:
            self.fields["legal_entity"].disabled = True
            self.fields["delivery_date"].disabled = True
            self.fields["customer"].disabled = True
            self.fields["change_reason"].required = True


class SalesDeliveryLineForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2})
    )

    class Meta:
        model = SalesDeliveryLine
        fields = ("source_sales_order_line", "quantity", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, user=None, delivery=None, **kwargs):
        super().__init__(*args, **kwargs)
        source_lines = delivery_lines_with_remaining(user=user, customer=delivery.customer)
        self.fields["source_sales_order_line"].queryset = source_lines
        self.fields["source_sales_order_line"].label_from_instance = lambda line: (
            f"{line.sales_order.document_number} / {line.item_code_snapshot} "
            f"(remaining {line.remaining_delivery_quantity} {line.uom_code_snapshot})"
        )
        if self.instance.pk:
            self.fields["source_sales_order_line"].disabled = True
            self.fields["change_reason"].required = True


class SalesInvoiceForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2})
    )

    class Meta:
        model = SalesInvoice
        fields = (
            "legal_entity",
            "invoice_date",
            "customer",
            "currency",
            "freight_amount",
            "notes",
            "source_exception_reason",
        )
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "source_exception_reason": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, user=None, source_mode=None, instance=None, **kwargs):
        super().__init__(*args, instance=instance, **kwargs)
        entities = accessible_legal_entities(user)
        self.fields["legal_entity"].queryset = entities
        self.fields["customer"].queryset = BusinessPartner.objects.filter(legal_entity__in=entities)
        actual_mode = source_mode or (self.instance.source_mode if self.instance.pk else None)
        if actual_mode != InvoiceSourceMode.SALES_ORDER:
            self.fields.pop("source_exception_reason")
        elif not self.instance.pk:
            self.fields["source_exception_reason"].required = True
        if self.instance.pk:
            self.fields["legal_entity"].disabled = True
            self.fields["invoice_date"].disabled = True
            self.fields["customer"].disabled = True
            self.fields["change_reason"].required = True


class SalesInvoiceLineForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2})
    )

    class Meta:
        model = SalesInvoiceLine
        fields = ("quantity", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, user=None, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.invoice = invoice
        if self.instance.pk:
            self.fields["change_reason"].required = True
            return
        if invoice.source_mode == InvoiceSourceMode.DELIVERY:
            self.fields["source_sales_delivery_line"] = forms.ModelChoiceField(
                queryset=posted_delivery_lines_for_invoice(user, customer=invoice.customer),
                label="Posted delivery line",
            )
            self.fields["source_sales_delivery_line"].label_from_instance = lambda line: (
                f"{line.sales_delivery.document_number} / {line.item_code_snapshot} "
                f"(invoiceable {line.remaining_invoice_quantity} {line.uom_code_snapshot})"
            )
        else:
            self.fields["source_sales_order_line"] = forms.ModelChoiceField(
                queryset=sales_order_lines_for_invoice_exception(user, customer=invoice.customer),
                label="Confirmed Sales Order line",
            )
            self.fields["source_sales_order_line"].label_from_instance = lambda line: (
                f"{line.sales_order.document_number} / {line.item_code_snapshot} "
                f"(invoiceable {line.remaining_invoice_quantity} {line.uom_code_snapshot})"
            )
