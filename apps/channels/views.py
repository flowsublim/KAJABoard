from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.channels.forms import ExternalSKUMapForm, LifecycleReasonForm, StoreForm
from apps.channels.models import ExternalSKUMap, Store
from apps.channels.selectors import sku_mappings, stores
from apps.channels.services import (
    create_external_sku_mapping,
    create_store,
    deactivate_channel_master,
    reactivate_channel_master,
    update_external_sku_mapping,
    update_store,
)


def _require(user, action, model):
    permission = f"{model._meta.app_label}.{action}_{model._meta.model_name}"
    if not user.has_perm(permission):
        raise PermissionDenied


def _model_values(form):
    fields = {field.name for field in form._meta.model._meta.fields}
    values = {key: value for key, value in form.cleaned_data.items() if key in fields}
    if isinstance(form, StoreForm):
        values["external_aliases"] = form.cleaned_data["external_aliases_text"]
    return values


def _add_service_errors(form, error):
    if hasattr(error, "message_dict"):
        for field, errors in error.message_dict.items():
            target = field if field in form.fields else None
            for message in errors:
                form.add_error(target, message)
    else:
        for message in error.messages:
            form.add_error(None, message)


@login_required
def store_list(request):
    _require(request.user, "view", Store)
    include_inactive = request.GET.get("inactive") == "1"
    search = request.GET.get("q", "").strip()
    channel = request.GET.get("channel", "").strip()
    page = Paginator(
        stores(
            request.user,
            include_inactive=include_inactive,
            search=search,
            channel=channel,
        ),
        25,
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "channels/store_list.html",
        {
            "page": page,
            "search": search,
            "channel": channel,
            "include_inactive": include_inactive,
            "can_add": request.user.has_perm("channels.add_store"),
            "can_change": request.user.has_perm("channels.change_store"),
        },
    )


@login_required
def store_create(request):
    _require(request.user, "add", Store)
    form = StoreForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            store = create_store(
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{store} created.")
            return redirect("channels:store-list")
    return render(request, "channels/store_form.html", {"form": form, "title": "New Store"})


@login_required
def store_edit(request, pk):
    _require(request.user, "change", Store)
    store = get_object_or_404(stores(request.user, include_inactive=True), pk=pk)
    form = StoreForm(request.POST or None, instance=store, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            store = update_store(
                store,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{store} updated.")
            return redirect("channels:store-list")
    return render(
        request,
        "channels/store_form.html",
        {"form": form, "title": f"Edit {store}"},
    )


@login_required
def mapping_list(request):
    _require(request.user, "view", ExternalSKUMap)
    include_inactive = request.GET.get("inactive") == "1"
    search = request.GET.get("q", "").strip()
    store_id = request.GET.get("store", "").strip()
    selected_store = None
    if store_id:
        selected_store = get_object_or_404(stores(request.user, include_inactive=True), pk=store_id)
    page = Paginator(
        sku_mappings(
            request.user,
            include_inactive=include_inactive,
            search=search,
            store=selected_store,
        ),
        25,
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "channels/mapping_list.html",
        {
            "page": page,
            "search": search,
            "store_id": store_id,
            "store_options": stores(request.user, include_inactive=True),
            "include_inactive": include_inactive,
            "can_add": request.user.has_perm("channels.add_externalskumap"),
            "can_change": request.user.has_perm("channels.change_externalskumap"),
        },
    )


@login_required
def mapping_create(request):
    _require(request.user, "add", ExternalSKUMap)
    form = ExternalSKUMapForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            mapping = create_external_sku_mapping(
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{mapping} created.")
            return redirect("channels:mapping-list")
    return render(
        request,
        "channels/mapping_form.html",
        {"form": form, "title": "New External SKU Mapping"},
    )


@login_required
def mapping_edit(request, pk):
    _require(request.user, "change", ExternalSKUMap)
    mapping = get_object_or_404(sku_mappings(request.user, include_inactive=True), pk=pk)
    form = ExternalSKUMapForm(request.POST or None, instance=mapping, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            mapping = update_external_sku_mapping(
                mapping,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{mapping} updated.")
            return redirect("channels:mapping-list")
    return render(
        request,
        "channels/mapping_form.html",
        {"form": form, "title": f"Edit {mapping}"},
    )


@login_required
def lifecycle(request, master_type, pk):
    model = Store if master_type == "stores" else ExternalSKUMap
    queryset = (
        stores(request.user, include_inactive=True)
        if model is Store
        else sku_mappings(request.user, include_inactive=True)
    )
    _require(request.user, "change", model)
    instance = get_object_or_404(queryset, pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = deactivate_channel_master if instance.is_active else reactivate_channel_master
        try:
            instance = service(instance, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"{instance} {'activated' if instance.is_active else 'deactivated'}.",
            )
            destination = "channels:store-list" if model is Store else "channels:mapping-list"
            return redirect(destination)
    cancel_url = "channels:store-list" if model is Store else "channels:mapping-list"
    return render(
        request,
        "master/lifecycle_form.html",
        {"form": form, "object": instance, "cancel_url": cancel_url},
    )
