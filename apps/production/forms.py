from django import forms

from apps.production.models import (
    ProductionDirectExtraCost,
    ProductionRejectEntry,
    ProductionRejectLine,
    ProductionTariff,
    ProductionWarehouseHandover,
    ProductionWarehouseHandoverLine,
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
        fields = _EntryForm.Meta.fields + ("stage", "employee", "wage_method")


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


class ConfirmationForm(forms.Form):
    pass


class ProductionWarehouseHandoverForm(_EntryForm):
    class Meta(_EntryForm.Meta):
        model = ProductionWarehouseHandover
        fields = ("legal_entity", "work_order", "handover_date", "cpo_beneficiary", "notes")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["cpo_beneficiary"].required = False
        self.fields["cpo_beneficiary"].label = "CPO Beneficiary / SPV"
        self.fields[
            "cpo_beneficiary"
        ].help_text = (
            "Beneficiary for CPO Finished Goods Fee after Warehouse accepts posted finished goods."
        )
        from apps.accounts.models import Employee

        qs = Employee.objects.filter(is_active=True)
        if self.instance and self.instance.pk and self.instance.legal_entity_id:
            qs = qs.filter(legal_entity_id=self.instance.legal_entity_id)
        self.fields["cpo_beneficiary"].queryset = qs

        if self.instance and self.instance.pk:
            from apps.incentives.models import IncentiveAccrual, IncentiveType
            from apps.warehouse.models import WarehouseReceiptLine

            rcp_line_ids = WarehouseReceiptLine.objects.filter(
                receipt__handover=self.instance
            ).values_list("id", flat=True)
            has_accrual = IncentiveAccrual.objects.filter(
                incentive_type=IncentiveType.CPO_FEE,
                source_type="WAREHOUSE_RECEIPT_LINE",
                source_line_id__in=[str(lid) for lid in rcp_line_ids],
            ).exists()
            if has_accrual:
                self.fields["cpo_beneficiary"].disabled = True


class ProductionWarehouseHandoverLineForm(forms.ModelForm):
    class Meta:
        model = ProductionWarehouseHandoverLine
        fields = ("output", "quantity", "notes")


class ProductionTariffForm(forms.ModelForm):
    class Meta:
        model = ProductionTariff
        fields = (
            "legal_entity",
            "stage",
            "item",
            "wage_method",
            "rate_per_unit",
            "currency",
            "effective_from",
            "effective_to",
            "is_active",
            "notes",
        )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            from apps.organizations.selectors import accessible_legal_entities

            self.fields["legal_entity"].queryset = accessible_legal_entities(user)


class ProductionDirectExtraCostForm(forms.ModelForm):
    class Meta:
        model = ProductionDirectExtraCost
        fields = (
            "legal_entity",
            "work_order",
            "output",
            "cost_date",
            "category",
            "employee",
            "description",
            "amount",
            "notes",
        )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["work_order"].queryset = eligible_internal_work_orders(user)
            from apps.organizations.selectors import accessible_legal_entities

            self.fields["legal_entity"].queryset = accessible_legal_entities(user)


class CostSnapshotBuildForm(forms.Form):
    as_of_date = forms.DateField(required=False)
    idempotency_key = forms.CharField(widget=forms.HiddenInput, required=False)
