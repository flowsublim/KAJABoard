from django import forms

from apps.organizations.selectors import accessible_legal_entities
from apps.partners.models import BusinessPartner, PartnerRoleType


class BusinessPartnerForm(forms.ModelForm):
    roles = forms.MultipleChoiceField(
        choices=PartnerRoleType.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Roles are assigned through the audited partner role service.",
    )
    change_reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    class Meta:
        model = BusinessPartner
        fields = (
            "legal_entity",
            "code",
            "display_name",
            "legal_name",
            "address_line_1",
            "address_line_2",
            "city",
            "province",
            "postal_code",
            "country_code",
            "pic_name",
            "pic_title",
            "email",
            "phone",
            "pic_email",
            "pic_phone",
            "npwp",
            "nitku",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
            "payment_terms_days",
            "credit_terms_days",
            "credit_limit",
            "notes",
            "effective_from",
            "effective_to",
        )
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, can_manage_roles=True, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["legal_entity"].queryset = accessible_legal_entities(user)
        if self.instance.pk:
            self.fields["roles"].initial = self.instance.roles.filter(is_active=True).values_list(
                "role_type", flat=True
            )
            self.fields["change_reason"].required = True
        if not can_manage_roles:
            self.fields["roles"].disabled = True
            self.fields["roles"].help_text = "Your permissions do not allow role changes."


class PartnerRoleForm(forms.Form):
    role_type = forms.ChoiceField(choices=PartnerRoleType.choices)
    reason = forms.CharField(max_length=500)


class LifecycleReasonForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
