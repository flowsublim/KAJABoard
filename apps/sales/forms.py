from django import forms

from apps.catalog.models import Item
from apps.organizations.models import BusinessUnit
from apps.organizations.selectors import accessible_legal_entities
from apps.partners.models import BusinessPartner
from apps.sales.models import SalesOrder, SalesOrderLine


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
