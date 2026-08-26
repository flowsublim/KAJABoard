from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.tax.forms import LifecycleReasonForm, TaxRegistrationForm
from apps.tax.models import TaxRegistration
from apps.tax.selectors import tax_registrations
from apps.tax.services import (
    create_tax_registration,
    deactivate_tax_registration,
    reactivate_tax_registration,
    update_tax_registration,
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
def registration_list(request):
    _require(request.user, "view", TaxRegistration)
    include_inactive = request.GET.get("inactive") == "1"
    search = request.GET.get("q", "").strip()
    page = Paginator(
        tax_registrations(request.user, include_inactive=include_inactive, search=search),
        25,
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "tax/registration_list.html",
        {
            "page": page,
            "search": search,
            "include_inactive": include_inactive,
            "can_add": request.user.has_perm("tax.add_taxregistration"),
            "can_change": request.user.has_perm("tax.change_taxregistration"),
        },
    )


@login_required
def registration_create(request):
    _require(request.user, "add", TaxRegistration)
    form = TaxRegistrationForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            registration = create_tax_registration(
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{registration} created.")
            return redirect("tax:registration-list")
    return render(
        request,
        "master/master_form.html",
        {"form": form, "title": "New Tax Registration", "cancel_url": "tax:registration-list"},
    )


@login_required
def registration_edit(request, pk):
    _require(request.user, "change", TaxRegistration)
    registration = get_object_or_404(tax_registrations(request.user, include_inactive=True), pk=pk)
    form = TaxRegistrationForm(request.POST or None, instance=registration, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            registration = update_tax_registration(
                registration,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{registration} updated.")
            return redirect("tax:registration-list")
    return render(
        request,
        "master/master_form.html",
        {"form": form, "title": f"Edit {registration}", "cancel_url": "tax:registration-list"},
    )


@login_required
def registration_lifecycle(request, pk):
    _require(request.user, "change", TaxRegistration)
    registration = get_object_or_404(tax_registrations(request.user, include_inactive=True), pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = (
            deactivate_tax_registration if registration.is_active else reactivate_tax_registration
        )
        try:
            registration = service(
                registration,
                actor=request.user,
                reason=form.cleaned_data["reason"],
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"{registration} {'activated' if registration.is_active else 'deactivated'}.",
            )
            return redirect("tax:registration-list")
    return render(
        request,
        "master/lifecycle_form.html",
        {"form": form, "object": registration, "cancel_url": "tax:registration-list"},
    )
