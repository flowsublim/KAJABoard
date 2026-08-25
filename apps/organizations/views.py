from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.organizations.forms import (
    BusinessUnitForm,
    CostCenterForm,
    DepartmentForm,
    LegalEntityForm,
    LifecycleReasonForm,
    WarehouseForm,
)
from apps.organizations.models import BusinessUnit, CostCenter, Department, LegalEntity, Warehouse
from apps.organizations.selectors import accessible_legal_entities, organization_master_counts
from apps.organizations.services import (
    create_business_unit,
    create_cost_center,
    create_department,
    create_legal_entity,
    create_warehouse,
    deactivate_master,
    reactivate_master,
    update_business_unit,
    update_cost_center,
    update_department,
    update_legal_entity,
    update_warehouse,
)


@dataclass(frozen=True)
class MasterConfig:
    model: type
    form: type
    create_service: object
    update_service: object
    title: str


MASTER_CONFIGS = {
    "legal-entities": MasterConfig(
        LegalEntity, LegalEntityForm, create_legal_entity, update_legal_entity, "Legal Entities"
    ),
    "business-units": MasterConfig(
        BusinessUnit, BusinessUnitForm, create_business_unit, update_business_unit, "Business Units"
    ),
    "departments": MasterConfig(
        Department, DepartmentForm, create_department, update_department, "Departments"
    ),
    "cost-centers": MasterConfig(
        CostCenter, CostCenterForm, create_cost_center, update_cost_center, "Cost Centers"
    ),
    "warehouses": MasterConfig(
        Warehouse, WarehouseForm, create_warehouse, update_warehouse, "Warehouses"
    ),
}


def _config(master_type: str) -> MasterConfig:
    try:
        return MASTER_CONFIGS[master_type]
    except KeyError as exc:
        raise Http404 from exc


def _queryset(user, config: MasterConfig):
    if config.model is LegalEntity:
        return accessible_legal_entities(user)
    queryset = config.model.objects.filter(legal_entity__in=accessible_legal_entities(user))
    related = [
        field.name for field in config.model._meta.fields if field.is_relation and field.many_to_one
    ]
    return queryset.select_related(*related)


def _require_model_permission(user, action: str, model) -> None:
    permission = f"{model._meta.app_label}.{action}_{model._meta.model_name}"
    if not user.has_perm(permission):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied


def _service_values(form) -> dict:
    model_fields = {field.name for field in form._meta.model._meta.fields}
    return {key: value for key, value in form.cleaned_data.items() if key in model_fields}


def _add_service_errors(form, error: ValidationError) -> None:
    if hasattr(error, "message_dict"):
        for field, errors in error.message_dict.items():
            target = field if field in form.fields else None
            for message in errors:
                form.add_error(target, message)
    else:
        for message in error.messages:
            form.add_error(None, message)


@login_required
def workspace(request):
    return render(
        request,
        "master/workspace.html",
        {"counts": organization_master_counts(request.user)},
    )


@login_required
def master_list(request, master_type):
    config = _config(master_type)
    _require_model_permission(request.user, "view", config.model)
    queryset = _queryset(request.user, config)
    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
    include_inactive = request.GET.get("inactive") == "1"
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    page = Paginator(queryset.order_by("code"), 25).get_page(request.GET.get("page"))
    return render(
        request,
        "master/master_list.html",
        {
            "page": page,
            "title": config.title,
            "master_type": master_type,
            "search": search,
            "include_inactive": include_inactive,
            "model_name": config.model._meta.model_name,
            "app_label": config.model._meta.app_label,
            "can_add": request.user.has_perm(
                f"{config.model._meta.app_label}.add_{config.model._meta.model_name}"
            ),
            "can_change": request.user.has_perm(
                f"{config.model._meta.app_label}.change_{config.model._meta.model_name}"
            ),
        },
    )


@login_required
def master_create(request, master_type):
    config = _config(master_type)
    _require_model_permission(request.user, "add", config.model)
    form = config.form(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            instance = config.create_service(
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_service_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{instance} created.")
            return redirect("organizations:master-list", master_type=master_type)
    return render(
        request,
        "master/master_form.html",
        {
            "form": form,
            "title": f"New {config.title.rstrip('s')}",
            "cancel_url": "organizations:master-list",
            "master_type": master_type,
        },
    )


@login_required
def master_edit(request, master_type, pk):
    config = _config(master_type)
    _require_model_permission(request.user, "change", config.model)
    instance = get_object_or_404(_queryset(request.user, config), pk=pk)
    form = config.form(request.POST or None, instance=instance, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            instance = config.update_service(
                instance,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_service_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{instance} updated.")
            return redirect("organizations:master-list", master_type=master_type)
    return render(
        request,
        "master/master_form.html",
        {
            "form": form,
            "title": f"Edit {instance}",
            "cancel_url": "organizations:master-list",
            "master_type": master_type,
        },
    )


@login_required
def master_lifecycle(request, master_type, pk):
    config = _config(master_type)
    _require_model_permission(request.user, "change", config.model)
    instance = get_object_or_404(_queryset(request.user, config), pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = deactivate_master if instance.is_active else reactivate_master
        instance = service(instance, actor=request.user, reason=form.cleaned_data["reason"])
        messages.success(
            request, f"{instance} {'activated' if instance.is_active else 'deactivated'}."
        )
        return redirect("organizations:master-list", master_type=master_type)
    return render(
        request,
        "master/lifecycle_form.html",
        {"form": form, "object": instance, "master_type": master_type},
    )
