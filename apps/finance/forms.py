from django import forms

from apps.finance.models import COAAccount, COAMapping
from apps.organizations.selectors import accessible_legal_entities


class AuditedFinanceForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when editing an existing master record.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["change_reason"].required = True


class COAAccountForm(AuditedFinanceForm):
    class Meta:
        model = COAAccount
        fields = (
            "legal_entity",
            "account_code",
            "account_name",
            "account_type",
            "report_group",
            "report_subgroup",
            "normal_balance",
            "parent",
            "is_header",
            "is_posting_allowed",
            "manual_journal_allowed",
            "is_cash_bank",
            "is_control_account",
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
            self.fields["parent"].queryset = COAAccount.objects.filter(legal_entity__in=entities)
        if self.instance.pk:
            self.fields["legal_entity"].disabled = True
            self.fields["account_code"].disabled = True


class COAMappingForm(AuditedFinanceForm):
    class Meta:
        model = COAMapping
        fields = (
            "legal_entity",
            "module_code",
            "event_code",
            "dimension_type",
            "dimension_value",
            "line_role",
            "dc",
            "account",
            "priority",
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
            self.fields["account"].queryset = COAAccount.objects.filter(legal_entity__in=entities)


class LifecycleReasonForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
