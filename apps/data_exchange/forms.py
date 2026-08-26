from django import forms

from apps.organizations.selectors import accessible_legal_entities


class COAImportUploadForm(forms.Form):
    legal_entity = forms.ModelChoiceField(queryset=None)
    source_file = forms.FileField(help_text="CSV only, max 2 MB.")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["legal_entity"].queryset = accessible_legal_entities(user)


class ConfirmImportForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
