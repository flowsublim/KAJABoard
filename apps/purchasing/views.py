from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.purchasing.forms import LifecycleReasonForm, PurchaseCategoryForm
from apps.purchasing.models import AccountingTreatment, PurchaseCategory
from apps.purchasing.selectors import purchase_categories
from apps.purchasing.services import (
    create_purchase_category,
    deactivate_purchase_category,
    reactivate_purchase_category,
    update_purchase_category,
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
def category_list(request):
    _require(request.user, "view", PurchaseCategory)
    include_inactive = request.GET.get("inactive") == "1"
    search = request.GET.get("q", "").strip()
    treatment = request.GET.get("treatment", "").strip()
    page = Paginator(
        purchase_categories(
            request.user,
            include_inactive=include_inactive,
            search=search,
            accounting_treatment=treatment,
        ),
        25,
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "purchasing/category_list.html",
        {
            "page": page,
            "search": search,
            "treatment": treatment,
            "treatments": AccountingTreatment.choices,
            "include_inactive": include_inactive,
            "can_add": request.user.has_perm("purchasing.add_purchasecategory"),
            "can_change": request.user.has_perm("purchasing.change_purchasecategory"),
        },
    )


@login_required
def category_create(request):
    _require(request.user, "add", PurchaseCategory)
    form = PurchaseCategoryForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            category = create_purchase_category(
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{category} created.")
            return redirect("purchasing:category-list")
    return render(
        request,
        "master/master_form.html",
        {"form": form, "title": "New Purchase Category", "cancel_url": "purchasing:category-list"},
    )


@login_required
def category_edit(request, pk):
    _require(request.user, "change", PurchaseCategory)
    category = get_object_or_404(purchase_categories(request.user, include_inactive=True), pk=pk)
    form = PurchaseCategoryForm(request.POST or None, instance=category, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            category = update_purchase_category(
                category,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{category} updated.")
            return redirect("purchasing:category-list")
    return render(
        request,
        "master/master_form.html",
        {"form": form, "title": f"Edit {category}", "cancel_url": "purchasing:category-list"},
    )


@login_required
def category_lifecycle(request, pk):
    _require(request.user, "change", PurchaseCategory)
    category = get_object_or_404(purchase_categories(request.user, include_inactive=True), pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = (
            deactivate_purchase_category if category.is_active else reactivate_purchase_category
        )
        try:
            category = service(category, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"{category} {'activated' if category.is_active else 'deactivated'}.",
            )
            return redirect("purchasing:category-list")
    return render(
        request,
        "master/lifecycle_form.html",
        {"form": form, "object": category, "cancel_url": "purchasing:category-list"},
    )
