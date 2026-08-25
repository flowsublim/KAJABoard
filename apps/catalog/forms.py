import json

from django import forms
from django.core.exceptions import ValidationError

from apps.catalog.models import UOM, Item, ItemCategory
from apps.organizations.selectors import accessible_legal_entities
from apps.partners.models import BusinessPartner, PartnerRoleType


class AuditedCatalogForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["change_reason"].required = True


class UOMForm(AuditedCatalogForm):
    class Meta:
        model = UOM
        fields = ("code", "name", "dimension", "decimal_places", "effective_from", "effective_to")
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }


class ItemCategoryForm(AuditedCatalogForm):
    class Meta:
        model = ItemCategory
        fields = ("code", "name", "parent", "effective_from", "effective_to")
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }


class ItemForm(AuditedCatalogForm):
    variant_attributes_text = forms.CharField(
        required=False,
        label="Variant attributes (JSON)",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": '{"color": "Black"}'}),
    )

    class Meta:
        model = Item
        fields = (
            "legal_entity",
            "code",
            "name",
            "item_kind",
            "category",
            "subcategory",
            "uom",
            "parent_item",
            "sales_eligible",
            "purchase_eligible",
            "production_eligible",
            "inventory_eligible",
            "tax_classification",
            "valuation_policy",
            "minimum_stock",
            "lead_time_days",
            "preferred_vendor",
            "reference_cost",
            "reference_selling_price",
            "notes",
            "effective_from",
            "effective_to",
        )
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        if self.instance.pk:
            self.fields["variant_attributes_text"].initial = json.dumps(
                self.instance.variant_attributes, ensure_ascii=False
            )
        if user is not None:
            entities = accessible_legal_entities(user)
            self.fields["legal_entity"].queryset = entities
            self.fields["parent_item"].queryset = Item.objects.filter(legal_entity__in=entities)
            self.fields["preferred_vendor"].queryset = BusinessPartner.objects.filter(
                legal_entity__in=entities,
                is_active=True,
                roles__role_type=PartnerRoleType.VENDOR,
                roles__is_active=True,
            ).distinct()

    def clean_variant_attributes_text(self):
        value = self.cleaned_data["variant_attributes_text"].strip()
        if not value:
            return {}
        try:
            result = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError("Enter a valid JSON object.") from exc
        if not isinstance(result, dict):
            raise ValidationError("Variant attributes must be a JSON object.")
        return result


class LifecycleReasonForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
