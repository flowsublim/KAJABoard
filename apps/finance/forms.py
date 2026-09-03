from django import forms

from apps.finance.models import (
    AccountingPeriod,
    AssetClass,
    BankStatement,
    BankStatementLine,
    COAAccount,
    COAMapping,
    LiquidityAccount,
    PayableEntry,
    ReceivableEntry,
)
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
        if not self.instance._state.adding:
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
        if not self.instance._state.adding:
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


class LiquidityAccountForm(AuditedFinanceForm):
    """Liquidity master data only; transactional COA stays resolver-mapped."""

    class Meta:
        model = LiquidityAccount
        fields = (
            "legal_entity",
            "code",
            "name",
            "account_type",
            "currency",
            "mapping_key",
            "effective_from",
            "effective_to",
            "bank_name",
            "bank_account_number",
            "account_holder_name",
            "is_active",
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
            self.fields["legal_entity"].queryset = accessible_legal_entities(user)
        if not self.instance._state.adding:
            self.fields["legal_entity"].disabled = True
            self.fields["code"].disabled = True


class PaymentActionForm(forms.Form):
    legal_entity = forms.ModelChoiceField(queryset=None)
    liquidity_account = forms.ModelChoiceField(queryset=LiquidityAccount.objects.none())
    payment_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    source_key = forms.CharField(max_length=255)
    amount = forms.DecimalField(max_digits=20, decimal_places=0, min_value=1)

    def __init__(self, *args, user=None, target="receivable", **kwargs):
        super().__init__(*args, **kwargs)
        entities = accessible_legal_entities(user) if user is not None else None
        self.fields["legal_entity"].queryset = entities
        self.fields["liquidity_account"].queryset = LiquidityAccount.objects.filter(
            legal_entity__in=entities, is_active=True
        )
        model = ReceivableEntry if target == "receivable" else PayableEntry
        self.fields[target] = forms.ModelChoiceField(
            queryset=model.objects.filter(
                legal_entity__in=entities, open_amount__gt=0
            ).select_related("journal"),
            label=target.title(),
        )
        self.target = target


class PaymentReversalForm(forms.Form):
    confirm = forms.BooleanField(required=True, label="Confirm payment reversal")


class AssetClassForm(AuditedFinanceForm):
    class Meta:
        model = AssetClass
        fields = (
            "legal_entity",
            "code",
            "name",
            "mapping_key",
            "default_depreciation_method",
            "default_useful_life_months",
            "effective_from",
            "effective_to",
            "is_active",
            "notes",
        )
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }


class AccountingPeriodForm(forms.ModelForm):
    class Meta:
        model = AccountingPeriod
        fields = ("legal_entity", "fiscal_year", "period_number", "start_date", "end_date", "notes")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class BankStatementForm(forms.ModelForm):
    class Meta:
        model = BankStatement
        fields = (
            "legal_entity",
            "liquidity_account",
            "statement_reference",
            "start_date",
            "end_date",
            "currency",
            "opening_balance",
            "closing_balance",
            "source_reference",
        )
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class BankStatementLineForm(forms.ModelForm):
    class Meta:
        model = BankStatementLine
        fields = (
            "source_identity",
            "transaction_date",
            "value_date",
            "external_reference",
            "description",
            "direction",
            "amount",
            "sequence",
        )
        widgets = {
            "transaction_date": forms.DateInput(attrs={"type": "date"}),
            "value_date": forms.DateInput(attrs={"type": "date"}),
        }


class BankMatchForm(forms.Form):
    liquidity_entry = forms.UUIDField()
    amount = forms.DecimalField(max_digits=20, decimal_places=0, min_value=1)
    source_key = forms.CharField(max_length=255)


class ReasonForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
