from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.catalog.forms import ItemCategoryForm, ItemForm, LifecycleReasonForm, UOMForm
from apps.catalog.models import UOM, Item, ItemCategory
from apps.catalog.selectors import catalog_items, item_categories, units_of_measure
from apps.catalog.services import (
    create_item,
    create_item_category,
    create_uom,
    deactivate_catalog_master,
    reactivate_catalog_master,
    update_item,
    update_item_category,
    update_uom,
)


@dataclass(frozen=True)
class CatalogConfig:
    model: type
    form: type
    create_service: object
    update_service: object
    title: str


CONFIGS = {
    "uoms": CatalogConfig(UOM, UOMForm, create_uom, update_uom, "Units of Measure"),
    "categories": CatalogConfig(
        ItemCategory,
        ItemCategoryForm,
        create_item_category,
        update_item_category,
        "Item Categories",
    ),
    "items": CatalogConfig(Item, ItemForm, create_item, update_item, "Items"),
}


def _config(master_type):
    try:
        return CONFIGS[master_type]
    except KeyError as exc:
        raise Http404 from exc


def _require(user, action, model):
    permission = f"{model._meta.app_label}.{action}_{model._meta.model_name}"
    if not user.has_perm(permission):
        raise PermissionDenied


def _queryset(user, model, include_inactive):
    if model is Item:
        return catalog_items(user, include_inactive=include_inactive)
    if model is UOM:
        return units_of_measure(include_inactive=include_inactive)
    return item_categories(include_inactive=include_inactive)


def _values(form):
    fields = {field.name for field in form._meta.model._meta.fields}
    values = {key: value for key, value in form.cleaned_data.items() if key in fields}
    if isinstance(form, ItemForm):
        values["variant_attributes"] = form.cleaned_data["variant_attributes_text"]
    return values


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
def catalog_list(request, master_type):
    config = _config(master_type)
    _require(request.user, "view", config.model)
    include_inactive = request.GET.get("inactive") == "1"
    search = request.GET.get("q", "").strip()
    queryset = _queryset(request.user, config.model, include_inactive)
    if search:
        queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
    page = Paginator(queryset.order_by("code"), 25).get_page(request.GET.get("page"))
    return render(
        request,
        "catalog/catalog_list.html",
        {
            "page": page,
            "title": config.title,
            "master_type": master_type,
            "search": search,
            "include_inactive": include_inactive,
            "model_name": config.model._meta.model_name,
            "can_add": request.user.has_perm(
                f"{config.model._meta.app_label}.add_{config.model._meta.model_name}"
            ),
            "can_change": request.user.has_perm(
                f"{config.model._meta.app_label}.change_{config.model._meta.model_name}"
            ),
        },
    )


@login_required
def catalog_create(request, master_type):
    config = _config(master_type)
    _require(request.user, "add", config.model)
    form = config.form(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            instance = config.create_service(
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{instance} created.")
            return redirect("catalog:list", master_type=master_type)
    return render(
        request,
        "catalog/catalog_form.html",
        {"form": form, "title": f"New {config.title.rstrip('s')}", "master_type": master_type},
    )


@login_required
def catalog_edit(request, master_type, pk):
    config = _config(master_type)
    _require(request.user, "change", config.model)
    instance = get_object_or_404(_queryset(request.user, config.model, True), pk=pk)
    form = config.form(request.POST or None, instance=instance, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            instance = config.update_service(
                instance,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{instance} updated.")
            return redirect("catalog:list", master_type=master_type)
    return render(
        request,
        "catalog/catalog_form.html",
        {"form": form, "title": f"Edit {instance}", "master_type": master_type},
    )


@login_required
def catalog_lifecycle(request, master_type, pk):
    config = _config(master_type)
    _require(request.user, "change", config.model)
    instance = get_object_or_404(_queryset(request.user, config.model, True), pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = deactivate_catalog_master if instance.is_active else reactivate_catalog_master
        instance = service(instance, actor=request.user, reason=form.cleaned_data["reason"])
        messages.success(
            request, f"{instance} {'activated' if instance.is_active else 'deactivated'}."
        )
        return redirect("catalog:list", master_type=master_type)
    return render(request, "master/lifecycle_form.html", {"form": form, "object": instance})
