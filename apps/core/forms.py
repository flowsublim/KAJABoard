from django import forms
from django.core.exceptions import ValidationError

from apps.core.models import DocumentSequence
from apps.core.services.numbering import validate_number_template
from apps.organizations.selectors import accessible_legal_entities


class DocumentSequenceForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when editing an existing configuration.",
    )

    class Meta:
        model = DocumentSequence
        fields = (
            "legal_entity",
            "document_type",
            "name",
            "prefix",
            "format_template",
            "padding",
            "starting_number",
            "reset_mode",
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
            self.fields["legal_entity"].queryset = accessible_legal_entities(user)
        if self.instance.pk:
            self.fields["change_reason"].required = True
            self.fields["legal_entity"].disabled = True
            self.fields["document_type"].disabled = True

    def clean(self):
        cleaned = super().clean()
        if {
            "format_template",
            "prefix",
            "padding",
        } <= cleaned.keys():
            try:
                validate_number_template(
                    template=cleaned["format_template"],
                    prefix=cleaned["prefix"],
                    padding=cleaned["padding"],
                )
            except ValidationError as error:
                self.add_error(None, error)
        return cleaned


class NumberPreviewForm(forms.Form):
    business_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))


class LifecycleReasonForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
