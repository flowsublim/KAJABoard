from django import forms

from apps.catalog.models import Item
from apps.organizations.models import CostCenter
from apps.organizations.selectors import accessible_legal_entities
from apps.partners.models import BusinessPartner
from apps.projects.models import Project
from apps.purchasing.models import (
    PurchaseCategory,
    PurchaseOrder,
    PurchaseOrderLine,
    WorkOrder,
    WorkOrderMaterialAllocation,
    WorkOrderOutput,
)
from apps.sales.models import SalesOrder


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = (
            "legal_entity",
            "vendor",
            "vendor_reference",
            "project",
            "document_date",
            "expected_date",
            "currency",
            "freight_amount",
            "notes",
        )


class PurchaseOrderLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrderLine
        fields = (
            "item",
            "purchase_category",
            "quantity",
            "unit_price",
            "discount_amount",
            "tax_rate",
            "notes",
        )


class PurchaseCategoryForm(forms.ModelForm):
    change_reason = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when editing an existing master record.",
    )

    class Meta:
        model = PurchaseCategory
        fields = (
            "legal_entity",
            "code",
            "name",
            "accounting_treatment",
            "cost_center",
            "inventory_classification",
            "asset_class_reference",
            "snapshot_production",
            "default_accounting_mapping_key",
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
            entities = accessible_legal_entities(user)
            self.fields["legal_entity"].queryset = entities
            self.fields["cost_center"].queryset = CostCenter.objects.filter(
                legal_entity__in=entities
            )
        if self.instance.pk:
            self.fields["change_reason"].required = True
            self.fields["legal_entity"].disabled = True
            self.fields["code"].disabled = True


class LifecycleReasonForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))


class WorkOrderForm(forms.ModelForm):
    class Meta:
        model = WorkOrder
        fields = (
            "legal_entity",
            "document_date",
            "work_order_type",
            "vendor",
            "sales_order",
            "project",
            "due_date",
            "instructions",
            "notes",
        )
        widgets = {
            "document_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "instructions": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        entities = accessible_legal_entities(user) if user else None
        if entities is not None:
            self.fields["legal_entity"].queryset = entities
            self.fields["vendor"].queryset = BusinessPartner.objects.filter(
                legal_entity__in=entities
            )
            self.fields["sales_order"].queryset = SalesOrder.objects.filter(
                legal_entity__in=entities
            )
            self.fields["project"].queryset = Project.objects.filter(legal_entity__in=entities)
        if self.instance.pk:
            self.fields["legal_entity"].disabled = True
            self.fields["document_date"].disabled = True


class WorkOrderOutputForm(forms.ModelForm):
    class Meta:
        model = WorkOrderOutput
        fields = ("item", "target_quantity", "due_date", "notes")
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, work_order=None, **kwargs):
        super().__init__(*args, **kwargs)
        if work_order:
            self.fields["item"].queryset = Item.objects.filter(legal_entity=work_order.legal_entity)
        if self.instance.pk:
            self.fields["item"].disabled = True


class WorkOrderMaterialAllocationForm(forms.ModelForm):
    class Meta:
        model = WorkOrderMaterialAllocation
        fields = ("output", "material_item", "planned_quantity", "reference_cost", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, work_order=None, **kwargs):
        super().__init__(*args, **kwargs)
        if work_order:
            self.fields["output"].queryset = work_order.outputs.all()
            self.fields["material_item"].queryset = Item.objects.filter(
                legal_entity=work_order.legal_entity
            )
        if self.instance.pk:
            self.fields["output"].disabled = True
            self.fields["material_item"].disabled = True
