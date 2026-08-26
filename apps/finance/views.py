from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.finance.forms import COAAccountForm, COAMappingForm, LifecycleReasonForm
from apps.finance.models import COAAccount, COAMapping, MappingDimensionType
from apps.finance.selectors import coa_accounts, coa_mappings
from apps.finance.services import (
    create_coa_account,
    create_coa_mapping,
    deactivate_coa_account,
    deactivate_coa_mapping,
    reactivate_coa_account,
    reactivate_coa_mapping,
    update_coa_account,
    update_coa_mapping,
)


def _require(user, action, model):
    permission = f"{model._meta.app_label}.{action}_{model._meta.model_name}"
    if not user.has_perm(permission):
        raise PermissionDenied


def _model_values(form):
    fields = {field.name for field in form._meta.model._meta.fields}
    return {key: value for key, value in form.cleaned_data.items() if key in fields}


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
def account_list(request):
    _require(request.user, "view", COAAccount)
    include_inactive = request.GET.get("inactive") == "1"
    search = request.GET.get("q", "").strip()
    page = Paginator(
        coa_accounts(request.user, include_inactive=include_inactive, search=search),
        25,
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "finance/account_list.html",
        {
            "page": page,
            "search": search,
            "include_inactive": include_inactive,
            "can_add": request.user.has_perm("finance.add_coaaccount"),
            "can_change": request.user.has_perm("finance.change_coaaccount"),
        },
    )


@login_required
def account_create(request):
    _require(request.user, "add", COAAccount)
    form = COAAccountForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            account = create_coa_account(
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{account} created.")
            return redirect("finance:account-list")
    return render(
        request,
        "master/master_form.html",
        {"form": form, "title": "New COA Account", "cancel_url": "finance:account-list"},
    )


@login_required
def account_edit(request, pk):
    _require(request.user, "change", COAAccount)
    account = get_object_or_404(coa_accounts(request.user, include_inactive=True), pk=pk)
    form = COAAccountForm(request.POST or None, instance=account, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            account = update_coa_account(
                account,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{account} updated.")
            return redirect("finance:account-list")
    return render(
        request,
        "master/master_form.html",
        {"form": form, "title": f"Edit {account}", "cancel_url": "finance:account-list"},
    )


@login_required
def account_lifecycle(request, pk):
    _require(request.user, "change", COAAccount)
    account = get_object_or_404(coa_accounts(request.user, include_inactive=True), pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = deactivate_coa_account if account.is_active else reactivate_coa_account
        account = service(account, actor=request.user, reason=form.cleaned_data["reason"])
        messages.success(
            request, f"{account} {'activated' if account.is_active else 'deactivated'}."
        )
        return redirect("finance:account-list")
    return render(
        request,
        "master/lifecycle_form.html",
        {"form": form, "object": account, "cancel_url": "finance:account-list"},
    )


@login_required
def mapping_list(request):
    _require(request.user, "view", COAMapping)
    include_inactive = request.GET.get("inactive") == "1"
    search = request.GET.get("q", "").strip()
    dimension = request.GET.get("dimension", "").strip()
    queryset = coa_mappings(request.user, include_inactive=include_inactive, search=search)
    if dimension:
        queryset = queryset.filter(dimension_type=dimension)
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "finance/mapping_list.html",
        {
            "page": page,
            "search": search,
            "dimension": dimension,
            "dimensions": MappingDimensionType.choices,
            "include_inactive": include_inactive,
            "can_add": request.user.has_perm("finance.add_coamapping"),
            "can_change": request.user.has_perm("finance.change_coamapping"),
        },
    )


@login_required
def mapping_create(request):
    _require(request.user, "add", COAMapping)
    form = COAMappingForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            mapping = create_coa_mapping(
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{mapping} created.")
            return redirect("finance:mapping-list")
    return render(
        request,
        "master/master_form.html",
        {"form": form, "title": "New COA Mapping", "cancel_url": "finance:mapping-list"},
    )


@login_required
def mapping_edit(request, pk):
    _require(request.user, "change", COAMapping)
    mapping = get_object_or_404(coa_mappings(request.user, include_inactive=True), pk=pk)
    form = COAMappingForm(request.POST or None, instance=mapping, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            mapping = update_coa_mapping(
                mapping,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{mapping} updated.")
            return redirect("finance:mapping-list")
    return render(
        request,
        "master/master_form.html",
        {"form": form, "title": f"Edit {mapping}", "cancel_url": "finance:mapping-list"},
    )


@login_required
def mapping_lifecycle(request, pk):
    _require(request.user, "change", COAMapping)
    mapping = get_object_or_404(coa_mappings(request.user, include_inactive=True), pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = deactivate_coa_mapping if mapping.is_active else reactivate_coa_mapping
        mapping = service(mapping, actor=request.user, reason=form.cleaned_data["reason"])
        messages.success(
            request, f"{mapping} {'activated' if mapping.is_active else 'deactivated'}."
        )
        return redirect("finance:mapping-list")
    return render(
        request,
        "master/lifecycle_form.html",
        {"form": form, "object": mapping, "cancel_url": "finance:mapping-list"},
    )
