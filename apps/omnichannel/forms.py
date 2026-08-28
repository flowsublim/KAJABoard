from django import forms

from apps.omnichannel.models import OmniOrderLine
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
    quantity = forms.DecimalField(min_value=0, decimal_places=6, max_digits=18)
    packing_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        entities = accessible_legal_entities(user)
        self.fields["warehouse"].queryset = effective_warehouses(user)
        self.fields["order_line"].queryset = OmniOrderLine.objects.filter(
            order__legal_entity__in=entities, item__isnull=False
        ).select_related("order", "item")
