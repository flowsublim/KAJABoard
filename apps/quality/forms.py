from django import forms

from apps.accounts.models import Employee
from apps.organizations.selectors import accessible_legal_entities
from apps.quality.models import QualityInspection, QualityInspectionLine


class QualityInspectionForm(forms.ModelForm):
    class Meta:
        model = QualityInspection
        fields = (
            "legal_entity",
            "inspection_type",
            "source_module",
            "source_type",
            "source_document_id",
            "source_key",
            "inspection_date",
            "inspector",
            "warehouse",
            "notes",
            "evidence_reference",
        )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            entities = accessible_legal_entities(user)
            self.fields["legal_entity"].queryset = entities
            self.fields["inspector"].queryset = Employee.objects.filter(
                legal_entity__in=entities, is_active=True
            ).order_by("display_name")
            self.fields["warehouse"].queryset = self.fields["warehouse"].queryset.filter(
                legal_entity__in=entities, is_active=True
            )


class QualityInspectionLineForm(forms.ModelForm):
    class Meta:
        model = QualityInspectionLine
        fields = (
            "source_line_id",
            "item",
            "qty_presented",
            "qty_inspected",
            "qty_pass",
            "qty_hold",
            "qty_reject",
            "qty_rework",
            "reason_code_snapshot",
            "reason_text",
            "notes",
        )


class QualityCorrectionForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea)
    idempotency_key = forms.CharField(widget=forms.HiddenInput)
