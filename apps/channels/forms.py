import re

from django import forms

from apps.catalog.models import Item
from apps.channels.models import ExternalSKUMap, Store
from apps.organizations.models import BusinessUnit
from apps.organizations.selectors import accessible_legal_entities


class AuditedChannelForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when editing an existing master record.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if self.instance.pk:
            self.fields["change_reason"].required = True


class StoreForm(AuditedChannelForm):
    external_aliases_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="One alias per line; pipe-separated legacy aliases are also accepted.",
    )

    class Meta:
        model = Store
        fields = (
            "legal_entity",
            "business_unit",
            "code",
            "name",
            "channel",
            "external_account_id",
            "finance_dimension",
            "revenue_mapping_key",
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
        super().__init__(*args, user=user, **kwargs)
        if user is not None:
            entities = accessible_legal_entities(user)
            self.fields["legal_entity"].queryset = entities
            self.fields["business_unit"].queryset = BusinessUnit.objects.filter(
                legal_entity__in=entities
            )
        if self.instance.pk:
            self.fields["external_aliases_text"].initial = "\n".join(self.instance.external_aliases)
            for field in ("legal_entity", "code", "channel"):
                self.fields[field].disabled = True

    def clean_external_aliases_text(self):
        value = self.cleaned_data["external_aliases_text"]
        return [part.strip() for part in re.split(r"[\r\n|]+", value) if part.strip()]


class ExternalSKUMapForm(AuditedChannelForm):
    class Meta:
        model = ExternalSKUMap
        fields = (
            "store",
            "item",
            "external_sku",
            "external_product_name",
            "external_variation",
            "conversion_quantity",
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
        super().__init__(*args, user=user, **kwargs)
        if user is not None:
            entities = accessible_legal_entities(user)
            self.fields["store"].queryset = Store.objects.filter(legal_entity__in=entities)
            self.fields["item"].queryset = Item.objects.filter(legal_entity__in=entities)
        if self.instance.pk:
            for field in ("store", "external_sku", "external_variation"):
                self.fields[field].disabled = True


class LifecycleReasonForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
