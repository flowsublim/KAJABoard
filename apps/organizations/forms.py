from django import forms

from apps.organizations.models import BusinessUnit, CostCenter, Department, LegalEntity, Warehouse
from apps.organizations.selectors import accessible_legal_entities


class AuditedMasterForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when editing an existing master record.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if self.instance.pk:
            self.fields["change_reason"].required = True


class LegalEntityForm(AuditedMasterForm):
    class Meta:
        model = LegalEntity
        fields = (
            "code",
            "name",
            "display_name",
            "address_line_1",
            "address_line_2",
            "city",
            "province",
            "postal_code",
            "country_code",
            "email",
            "phone",
            "npwp",
            "nitku",
            "is_pkp",
            "reporting_currency",
            "timezone",
            "effective_from",
            "effective_to",
        )
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }


class OrganizationScopedForm(AuditedMasterForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        if user is None:
            return
        entities = accessible_legal_entities(user)
        if "legal_entity" in self.fields:
            self.fields["legal_entity"].queryset = entities
        if "business_unit" in self.fields:
            self.fields["business_unit"].queryset = BusinessUnit.objects.filter(
                legal_entity__in=entities
            )
        if "department" in self.fields:
            self.fields["department"].queryset = Department.objects.filter(
                legal_entity__in=entities
            )
        if "parent" in self.fields:
            self.fields["parent"].queryset = Department.objects.filter(legal_entity__in=entities)


class BusinessUnitForm(OrganizationScopedForm):
    class Meta:
        model = BusinessUnit
        fields = ("legal_entity", "code", "name", "document_name", "effective_from", "effective_to")
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }


class DepartmentForm(OrganizationScopedForm):
    class Meta:
        model = Department
        fields = (
            "legal_entity",
            "business_unit",
            "parent",
            "code",
            "name",
            "effective_from",
            "effective_to",
        )
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }


class CostCenterForm(OrganizationScopedForm):
    class Meta:
        model = CostCenter
        fields = (
            "legal_entity",
            "business_unit",
            "department",
            "code",
            "name",
            "category",
            "is_production_overhead_eligible",
            "effective_from",
            "effective_to",
        )
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }


class WarehouseForm(OrganizationScopedForm):
    class Meta:
        model = Warehouse
        fields = (
            "legal_entity",
            "business_unit",
            "code",
            "name",
            "address_line_1",
            "address_line_2",
            "city",
            "province",
            "postal_code",
            "phone",
            "email",
            "is_default",
            "effective_from",
            "effective_to",
        )
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }


class LifecycleReasonForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
