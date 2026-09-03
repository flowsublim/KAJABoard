from django import forms

from apps.catalog.selectors import effective_items
from apps.organizations.selectors import accessible_legal_entities, effective_cost_centers
from apps.partners.models import PartnerRoleType
from apps.partners.selectors import effective_business_partners
from apps.projects.models import Project, ProjectBudgetLine, ProjectForecastLine
from apps.purchasing.selectors import effective_purchase_categories
from apps.sales.models import SalesOrderState
from apps.sales.selectors import sales_orders


class ProjectForm(forms.ModelForm):
    change_reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    class Meta:
        model = Project
        fields = (
            "legal_entity",
            "name",
            "customer",
            "project_type",
            "contract_reference",
            "owner",
            "start_date",
            "target_date",
            "currency",
            "target_margin_percent",
            "notes",
        )
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "target_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["legal_entity"].queryset = accessible_legal_entities(user)
        self.fields["customer"].queryset = effective_business_partners(
            user, role_type=PartnerRoleType.CUSTOMER
        )


class ProjectBudgetLineForm(forms.ModelForm):
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    class Meta:
        model = ProjectBudgetLine
        fields = (
            "category",
            "description",
            "amount",
            "cost_center",
            "purchase_category",
            "item",
            "notes",
            "is_active",
        )
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, user, project, **kwargs):
        super().__init__(*args, **kwargs)
        entity = project.legal_entity
        self.fields["cost_center"].queryset = effective_cost_centers(user).filter(
            legal_entity=entity
        )
        self.fields["purchase_category"].queryset = effective_purchase_categories(user).filter(
            legal_entity=entity
        )
        self.fields["item"].queryset = effective_items(user).filter(legal_entity=entity)


class ProjectForecastLineForm(forms.ModelForm):
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    class Meta:
        model = ProjectForecastLine
        fields = (
            "category",
            "description",
            "amount",
            "cost_center",
            "purchase_category",
            "item",
            "notes",
            "is_active",
        )
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, user, project, **kwargs):
        super().__init__(*args, **kwargs)
        entity = project.legal_entity
        self.fields["cost_center"].queryset = effective_cost_centers(user).filter(
            legal_entity=entity
        )
        self.fields["purchase_category"].queryset = effective_purchase_categories(user).filter(
            legal_entity=entity
        )
        self.fields["item"].queryset = effective_items(user).filter(legal_entity=entity)


class ProjectSalesOrderLinkForm(forms.Form):
    sales_order = forms.ModelChoiceField(queryset=None)
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, user, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sales_order"].queryset = (
            sales_orders(user, legal_entity=project.legal_entity)
            .filter(
                customer=project.customer,
                state__in=(
                    SalesOrderState.DRAFT,
                    SalesOrderState.CONFIRMED,
                    SalesOrderState.ON_HOLD,
                ),
            )
            .filter(project_link__isnull=True)
        )


class ProjectReasonForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
