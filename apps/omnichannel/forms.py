from decimal import Decimal

from django import forms

from apps.catalog.models import Item
from apps.channels.models import Store
from apps.omnichannel.models import OmniOrderLine, PosCashSession
from apps.organizations.selectors import accessible_legal_entities, effective_warehouses


class OmniImportUploadForm(forms.Form):
    legal_entity = forms.ModelChoiceField(queryset=None)
    source_file = forms.FileField(help_text="XLSX or CSV, max 10 MB.")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["legal_entity"].queryset = accessible_legal_entities(user)


class OmniPackingForm(forms.Form):
    warehouse = forms.ModelChoiceField(queryset=None)
    order_line = forms.ModelChoiceField(queryset=OmniOrderLine.objects.none())
    quantity = forms.DecimalField(min_value=Decimal("0.000001"), decimal_places=6, max_digits=18)
    packing_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        entities = accessible_legal_entities(user)
        self.fields["warehouse"].queryset = effective_warehouses(user)
        self.fields["order_line"].queryset = OmniOrderLine.objects.filter(
            order__legal_entity__in=entities, item__isnull=False
        ).select_related("order", "item")


class PosSaleEntryForm(forms.Form):
    legal_entity = forms.ModelChoiceField(queryset=None)
    store = forms.ModelChoiceField(queryset=None)
    warehouse = forms.ModelChoiceField(queryset=None)
    item = forms.ModelChoiceField(queryset=None)
    quantity = forms.DecimalField(min_value=0, decimal_places=6, max_digits=18)
    unit_price_amount = forms.DecimalField(min_value=0, decimal_places=2, max_digits=18)
    tender_method = forms.ChoiceField(
        choices=(("CASH", "Cash"), ("QRIS", "QRIS"), ("OTHER", "Other"))
    )
    tender_reference = forms.CharField(required=False)
    cash_session = forms.ModelChoiceField(queryset=PosCashSession.objects.none(), required=False)
    transaction_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"})
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        entities = accessible_legal_entities(user)
        self.fields["legal_entity"].queryset = entities
        self.fields["store"].queryset = Store.objects.filter(
            legal_entity__in=entities, is_active=True
        )
        self.fields["warehouse"].queryset = effective_warehouses(user)
        self.fields["item"].queryset = Item.objects.filter(
            legal_entity__in=entities, is_active=True, sales_eligible=True, inventory_eligible=True
        ).select_related("uom")
        self.fields["cash_session"].queryset = PosCashSession.objects.filter(
            legal_entity__in=entities, state="OPEN"
        ).select_related("store")


class PosCashSessionOpenForm(forms.Form):
    legal_entity = forms.ModelChoiceField(queryset=None)
    store = forms.ModelChoiceField(queryset=None)
    opening_cash_amount = forms.DecimalField(min_value=0, decimal_places=2, max_digits=18)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        entities = accessible_legal_entities(user)
        self.fields["legal_entity"].queryset = entities
        self.fields["store"].queryset = Store.objects.filter(
            legal_entity__in=entities, is_active=True
        )


class PosCashSessionCloseForm(forms.Form):
    counted_cash_amount = forms.DecimalField(min_value=0, decimal_places=2, max_digits=18)
