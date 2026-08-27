from django import forms

from apps.production.models import (
    ProductionRejectEntry,
    ProductionRejectLine,
    ProductionWorkEntry,
    ProductionWorkLine,
)
from apps.production.selectors.wip import eligible_internal_work_orders


class _EntryForm(forms.ModelForm):
    class Meta:
        fields = ("legal_entity", "work_order", "production_date", "notes")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["work_order"].queryset = eligible_internal_work_orders(user)


class ProductionWorkEntryForm(_EntryForm):
    class Meta(_EntryForm.Meta):
        model = ProductionWorkEntry
        fields = _EntryForm.Meta.fields + ("stage",)


class ProductionWorkLineForm(forms.ModelForm):
    class Meta:
        model = ProductionWorkLine
        fields = ("output", "quantity", "notes")


class ProductionRejectEntryForm(_EntryForm):
    class Meta(_EntryForm.Meta):
        model = ProductionRejectEntry
        fields = _EntryForm.Meta.fields


class ProductionRejectLineForm(forms.ModelForm):
    class Meta:
        model = ProductionRejectLine
        fields = ("output", "stage", "quantity", "reason", "notes")


class CorrectionForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea)
    idempotency_key = forms.CharField(widget=forms.HiddenInput)
