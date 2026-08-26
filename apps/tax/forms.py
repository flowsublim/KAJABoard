from django import forms

from apps.organizations.selectors import accessible_legal_entities
from apps.partners.models import BusinessPartner
from apps.tax.models import TaxRegistration


class TaxRegistrationForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when editing an existing master record.",
    )

    class Meta:
        model = TaxRegistration
        fields = (
            "legal_entity",
            "business_partner",
            "registration_status",
            "tax_classification_key",
            "registration_reference",
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
            self.fields["business_partner"].queryset = BusinessPartner.objects.filter(
                legal_entity__in=entities
            )
        if self.instance.pk:
            self.fields["change_reason"].required = True
            self.fields["legal_entity"].disabled = True
            self.fields["business_partner"].disabled = True


class LifecycleReasonForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
