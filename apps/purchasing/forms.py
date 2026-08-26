from django import forms

from apps.organizations.models import CostCenter
from apps.organizations.selectors import accessible_legal_entities
from apps.purchasing.models import PurchaseCategory


class PurchaseCategoryForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when editing an existing master record.",
    )

    class Meta:
        model = PurchaseCategory
        fields = (
            "legal_entity",
            "code",
            "name",
            "accounting_treatment",
            "cost_center",
            "inventory_classification",
            "asset_class_reference",
            "snapshot_production",
            "default_accounting_mapping_key",
            "effective_from",
            "effective_to",
            "notes",
        )
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            entities = accessible_legal_entities(user)
            self.fields["legal_entity"].queryset = entities
            self.fields["cost_center"].queryset = CostCenter.objects.filter(
                legal_entity__in=entities
            )
        if self.instance.pk:
            self.fields["change_reason"].required = True
            self.fields["legal_entity"].disabled = True
            self.fields["code"].disabled = True


class LifecycleReasonForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
