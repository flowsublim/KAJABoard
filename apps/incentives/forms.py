"""Incentives UI forms enforcing service-layer validation."""

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.catalog.models import Item
from apps.incentives.models import (
    IncentiveCalculationMethod,
    IncentiveRule,
)
from apps.incentives.services.rules import create_incentive_rule, update_incentive_rule
from apps.organizations.selectors import accessible_legal_entities

EXECUTABLE_CALCULATION_METHODS = {
    IncentiveCalculationMethod.PER_UNIT,
    IncentiveCalculationMethod.FIXED,
}


class IncentiveRuleForm(forms.ModelForm):
    class Meta:
        model = IncentiveRule
        fields = (
            "legal_entity",
            "code",
            "name",
            "incentive_type",
            "trigger_type",
            "calculation_method",
            "item",
            "rate_value",
            "currency",
            "effective_from",
            "effective_to",
            "is_active",
            "notes",
        )
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            self.fields["legal_entity"].queryset = accessible_legal_entities(user)
        self.fields["item"].queryset = Item.objects.filter(is_active=True).order_by("code")
        self.fields["item"].required = False
        self.fields["effective_to"].required = False
        self.fields["notes"].required = False
        self.fields["currency"].initial = "IDR"

        self.fields["calculation_method"].help_text = (
            "Currently executable: Per Unit (PER_UNIT), Fixed (FIXED). "
            "Deferred to later phases: Percent Revenue, Percent Margin, Tiered, Formula."
        )

    def clean_rate_value(self):
        rate = self.cleaned_data.get("rate_value")
        if rate is not None and rate < Decimal("0"):
            raise forms.ValidationError("Rate value cannot be negative.")
        return rate

    def save(self, *, actor=None, commit=True):
        actor = actor or self.user
        data = dict(self.cleaned_data)
        legal_entity = data.pop("legal_entity")

        try:
            if self.instance and self.instance.pk:
                return update_incentive_rule(self.instance, actor=actor, **data)
            else:
                return create_incentive_rule(legal_entity=legal_entity, actor=actor, **data)
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                for field, msgs in exc.message_dict.items():
                    target_field = field if field in self.fields else None
                    for m in msgs:
                        self.add_error(target_field, m)
            else:
                for m in exc.messages:
                    self.add_error(None, m)
            raise exc
