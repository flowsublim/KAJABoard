from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.partners.forms import BusinessPartnerForm, LifecycleReasonForm, PartnerRoleForm
from apps.partners.models import BusinessPartner, PartnerRole
from apps.partners.selectors import business_partners
from apps.partners.services import (
    assign_partner_role,
    create_business_partner,
    deactivate_business_partner,
    reactivate_business_partner,
    remove_partner_role,
    update_business_partner_with_roles,
)


def _require(user, action: str, model) -> None:
    permission = f"{model._meta.app_label}.{action}_{model._meta.model_name}"
    if not user.has_perm(permission):
        raise PermissionDenied


def _values(form) -> dict:
    fields = {field.name for field in BusinessPartner._meta.fields}
    return {key: value for key, value in form.cleaned_data.items() if key in fields}


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
def partner_list(request):
    _require(request.user, "view", BusinessPartner)
    search = request.GET.get("q", "").strip()
    role_type = request.GET.get("role", "").strip()
    include_inactive = request.GET.get("inactive") == "1"
    queryset = business_partners(
        request.user,
        search=search,
        role_type=role_type,
        include_inactive=include_inactive,
    )
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "partners/partner_list.html",
        {
            "page": page,
            "search": search,
            "role_type": role_type,
            "include_inactive": include_inactive,
            "can_add": request.user.has_perm("partners.add_businesspartner"),
            "can_change": request.user.has_perm("partners.change_businesspartner"),
        },
    )


@login_required
def partner_create(request):
    _require(request.user, "add", BusinessPartner)
    form = BusinessPartnerForm(
        request.POST or None,
        user=request.user,
        can_manage_roles=request.user.has_perm("partners.add_partnerrole"),
    )
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["roles"]:
            _require(request.user, "add", PartnerRole)
        try:
            partner = create_business_partner(
                actor=request.user,
                role_types=form.cleaned_data["roles"],
                reason=form.cleaned_data.get("change_reason", ""),
                **_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{partner} created.")
            return redirect("partners:list")
    return render(request, "partners/partner_form.html", {"form": form, "title": "New Partner"})


@login_required
def partner_edit(request, pk):
    _require(request.user, "change", BusinessPartner)
    partner = get_object_or_404(business_partners(request.user, include_inactive=True), pk=pk)
    form = BusinessPartnerForm(
        request.POST or None,
        instance=partner,
        user=request.user,
        can_manage_roles=(
            request.user.has_perm("partners.add_partnerrole")
            and request.user.has_perm("partners.change_partnerrole")
        ),
    )
    if request.method == "POST" and form.is_valid():
        reason = form.cleaned_data["change_reason"]
        selected = set(form.cleaned_data["roles"])
        active_roles = {role.role_type: role for role in partner.roles.filter(is_active=True)}
        if selected - active_roles.keys():
            _require(request.user, "add", PartnerRole)
        if active_roles.keys() - selected:
            _require(request.user, "change", PartnerRole)
        try:
            partner = update_business_partner_with_roles(
                partner,
                role_types=selected,
                actor=request.user,
                reason=reason,
                **_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{partner} updated.")
            return redirect("partners:list")
    return render(
        request,
        "partners/partner_form.html",
        {"form": form, "title": f"Edit {partner}", "partner": partner},
    )


@login_required
def partner_lifecycle(request, pk):
    _require(request.user, "change", BusinessPartner)
    partner = get_object_or_404(business_partners(request.user, include_inactive=True), pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = deactivate_business_partner if partner.is_active else reactivate_business_partner
        partner = service(partner, actor=request.user, reason=form.cleaned_data["reason"])
        messages.success(
            request, f"{partner} {'activated' if partner.is_active else 'deactivated'}."
        )
        return redirect("partners:list")
    return render(request, "master/lifecycle_form.html", {"form": form, "object": partner})


@login_required
def partner_role_add(request, pk):
    _require(request.user, "add", PartnerRole)
    partner = get_object_or_404(business_partners(request.user), pk=pk)
    form = PartnerRoleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        assign_partner_role(partner, actor=request.user, **form.cleaned_data)
        messages.success(request, "Partner role assigned.")
        return redirect("partners:edit", pk=partner.pk)
    return render(
        request,
        "partners/role_form.html",
        {"form": form, "partner": partner, "title": "Assign Partner Role"},
    )


@login_required
def partner_role_remove(request, pk, role_pk):
    _require(request.user, "change", PartnerRole)
    partner = get_object_or_404(business_partners(request.user, include_inactive=True), pk=pk)
    role = get_object_or_404(PartnerRole, pk=role_pk, partner=partner)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        remove_partner_role(role, actor=request.user, reason=form.cleaned_data["reason"])
        messages.success(request, "Partner role removed.")
        return redirect("partners:edit", pk=partner.pk)
    return render(
        request,
        "partners/role_form.html",
        {"form": form, "partner": partner, "role": role, "title": "Remove Partner Role"},
    )
