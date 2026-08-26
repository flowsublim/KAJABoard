from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.sales.forms import SalesOrderForm, SalesOrderLineForm, SalesOrderTransitionForm
from apps.sales.models import SalesOrder, SalesOrderLine, SalesOrderState
from apps.sales.selectors import sales_order_detail, sales_orders
from apps.sales.services import (
    add_draft_line,
    cancel_sales_order,
    confirm_sales_order,
    hold_sales_order,
    release_sales_order,
    remove_draft_line,
    update_draft_line,
    update_draft_sales_order,
)
from apps.sales.services.orders import create_draft_sales_order


def _require(user, permission):
    if not user.has_perm(permission):
        raise PermissionDenied


def _model_values(form):
    fields = {field.name for field in form._meta.model._meta.fields}
    return {key: value for key, value in form.cleaned_data.items() if key in fields}


def _line_values(form):
    values = _model_values(form)
    values["description"] = form.cleaned_data.get("description", "")
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
def order_list(request):
    _require(request.user, "sales.view_salesorder")
    search = request.GET.get("q", "").strip()
    state = request.GET.get("state", "").strip()
    page = Paginator(sales_orders(request.user, search=search, state=state), 25).get_page(
        request.GET.get("page")
    )
    return render(
        request,
        "sales/order_list.html",
        {
            "page": page,
            "search": search,
            "state": state,
            "states": SalesOrderState.choices,
            "can_add": request.user.has_perm("sales.add_salesorder"),
        },
    )


@login_required
def order_create(request):
    _require(request.user, "sales.add_salesorder")
    form = SalesOrderForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            order = create_draft_sales_order(actor=request.user, **_model_values(form))
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{order.document_number} created as a draft.")
            return redirect("sales:order-detail", pk=order.pk)
    return render(request, "sales/order_form.html", {"form": form, "title": "New Sales Order"})


def _order_or_404(user, pk):
    return get_object_or_404(sales_orders(user), pk=pk)


@login_required
def order_detail(request, pk):
    _require(request.user, "sales.view_salesorder")
    try:
        order = sales_order_detail(request.user, pk=pk)
    except SalesOrder.DoesNotExist:
        raise Http404 from None
    return render(
        request,
        "sales/order_detail.html",
        {
            "order": order,
            "can_change": request.user.has_perm("sales.change_salesorder")
            and order.state == SalesOrderState.DRAFT,
            "can_confirm": request.user.has_perm("sales.confirm_salesorder")
            and order.state == SalesOrderState.DRAFT,
            "can_cancel": request.user.has_perm("sales.cancel_salesorder")
            and order.state
            in {SalesOrderState.DRAFT, SalesOrderState.CONFIRMED, SalesOrderState.ON_HOLD},
            "can_hold": request.user.has_perm("sales.hold_salesorder")
            and order.state in {SalesOrderState.CONFIRMED, SalesOrderState.ON_HOLD},
        },
    )


@login_required
def order_edit(request, pk):
    _require(request.user, "sales.change_salesorder")
    order = _order_or_404(request.user, pk)
    form = SalesOrderForm(request.POST or None, instance=order, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            order = update_draft_sales_order(
                order,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{order.document_number} updated.")
            return redirect("sales:order-detail", pk=order.pk)
    return render(request, "sales/order_form.html", {"form": form, "title": f"Edit {order}"})


@login_required
def line_add(request, pk):
    _require(request.user, "sales.change_salesorder")
    order = _order_or_404(request.user, pk)
    form = SalesOrderLineForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            line = add_draft_line(
                order,
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_line_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"Line {line.line_number} added.")
            return redirect("sales:order-detail", pk=order.pk)
    return render(
        request,
        "sales/line_form.html",
        {"form": form, "order": order, "title": f"Add line to {order.document_number}"},
    )


@login_required
def line_edit(request, pk, line_pk):
    _require(request.user, "sales.change_salesorder")
    order = _order_or_404(request.user, pk)
    line = get_object_or_404(SalesOrderLine.objects.filter(sales_order=order), pk=line_pk)
    form = SalesOrderLineForm(request.POST or None, instance=line, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            update_draft_line(
                line,
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_line_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"Line {line.line_number} updated.")
            return redirect("sales:order-detail", pk=order.pk)
    return render(
        request,
        "sales/line_form.html",
        {"form": form, "order": order, "title": f"Edit line {line.line_number}"},
    )


@login_required
def line_remove(request, pk, line_pk):
    _require(request.user, "sales.change_salesorder")
    order = _order_or_404(request.user, pk)
    line = get_object_or_404(SalesOrderLine.objects.filter(sales_order=order), pk=line_pk)
    form = SalesOrderTransitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            remove_draft_line(line, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"Line {line.line_number} removed.")
            return redirect("sales:order-detail", pk=order.pk)
    return render(
        request,
        "sales/transition_form.html",
        {
            "form": form,
            "order": order,
            "title": f"Remove line {line.line_number}",
            "submit_label": "Remove line",
        },
    )


@login_required
def order_confirm(request, pk):
    _require(request.user, "sales.confirm_salesorder")
    order = _order_or_404(request.user, pk)
    if request.method != "POST":
        return redirect("sales:order-detail", pk=order.pk)
    try:
        confirm_sales_order(order, actor=request.user)
    except ValidationError as error:
        messages.error(request, "; ".join(error.messages))
    else:
        messages.success(request, f"{order.document_number} confirmed.")
    return redirect("sales:order-detail", pk=order.pk)


@login_required
def order_cancel(request, pk):
    _require(request.user, "sales.cancel_salesorder")
    order = _order_or_404(request.user, pk)
    form = SalesOrderTransitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            cancel_sales_order(order, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{order.document_number} cancelled.")
            return redirect("sales:order-detail", pk=order.pk)
    return render(
        request,
        "sales/transition_form.html",
        {"form": form, "order": order, "title": f"Cancel {order}", "submit_label": "Cancel order"},
    )


@login_required
def order_hold_release(request, pk):
    _require(request.user, "sales.hold_salesorder")
    order = _order_or_404(request.user, pk)
    form = SalesOrderTransitionForm(request.POST or None)
    action = "release" if order.state == SalesOrderState.ON_HOLD else "hold"
    if request.method == "POST" and form.is_valid():
        try:
            service = release_sales_order if action == "release" else hold_sales_order
            service(order, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{order.document_number} {action}d.")
            return redirect("sales:order-detail", pk=order.pk)
    return render(
        request,
        "sales/transition_form.html",
        {
            "form": form,
            "order": order,
            "title": f"{action.title()} {order}",
            "submit_label": f"{action.title()} order",
        },
    )
