from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.sales.forms import (
    SalesDeliveryForm,
    SalesDeliveryLineForm,
    SalesInvoiceForm,
    SalesInvoiceLineForm,
    SalesOrderForm,
    SalesOrderLineForm,
    SalesOrderTransitionForm,
)
from apps.sales.models import (
    InvoiceSourceMode,
    SalesDelivery,
    SalesDeliveryLine,
    SalesDeliveryState,
    SalesInvoice,
    SalesInvoiceDocumentKind,
    SalesInvoiceLine,
    SalesInvoiceState,
    SalesOrder,
    SalesOrderLine,
    SalesOrderState,
)
from apps.sales.selectors import (
    sales_deliveries,
    sales_delivery_detail,
    sales_invoice_detail,
    sales_invoices,
    sales_order_detail,
    sales_orders,
)
from apps.sales.services import (
    add_draft_delivery_invoice_line,
    add_draft_delivery_line,
    add_draft_line,
    add_draft_sales_order_invoice_line,
    cancel_delivery,
    cancel_invoice,
    cancel_sales_order,
    confirm_invoice,
    confirm_sales_order,
    create_draft_delivery,
    create_draft_delivery_invoice,
    create_draft_sales_order_invoice,
    create_proforma,
    hold_sales_order,
    override_sales_order_credit_hold,
    post_delivery,
    release_sales_order,
    remove_draft_delivery_line,
    remove_draft_invoice_line,
    remove_draft_line,
    update_draft_delivery,
    update_draft_delivery_line,
    update_draft_invoice,
    update_draft_invoice_line,
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
            "can_credit_override": request.user.has_perm("sales.override_salesorder_credit")
            and order.state == SalesOrderState.ON_HOLD
            and getattr(order, "credit_control", None)
            and order.credit_control.status == "HELD",
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
def order_credit_override(request, pk):
    _require(request.user, "sales.override_salesorder_credit")
    order = _order_or_404(request.user, pk)
    form = SalesOrderTransitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            override_sales_order_credit_hold(
                order, actor=request.user, reason=form.cleaned_data["reason"]
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, "Credit hold overridden with an audit reason.")
            return redirect("sales:order-detail", pk=order.pk)
    return render(
        request,
        "sales/transition_form.html",
        {"form": form, "order": order, "title": "Override credit hold", "submit_label": "Override"},
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


def _delivery_or_404(user, pk):
    return get_object_or_404(sales_deliveries(user), pk=pk)


def _invoice_or_404(user, pk):
    return get_object_or_404(sales_invoices(user), pk=pk)


@login_required
def delivery_list(request):
    _require(request.user, "sales.view_salesdelivery")
    search = request.GET.get("q", "").strip()
    state = request.GET.get("state", "").strip()
    page = Paginator(sales_deliveries(request.user, search=search, state=state), 25).get_page(
        request.GET.get("page")
    )
    return render(
        request,
        "sales/delivery_list.html",
        {
            "page": page,
            "search": search,
            "state": state,
            "states": SalesDeliveryState.choices,
            "can_add": request.user.has_perm("sales.add_salesdelivery"),
        },
    )


@login_required
def delivery_create(request):
    _require(request.user, "sales.add_salesdelivery")
    form = SalesDeliveryForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            delivery = create_draft_delivery(actor=request.user, **_model_values(form))
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{delivery.document_number} created as a draft.")
            return redirect("sales:delivery-detail", pk=delivery.pk)
    return render(
        request,
        "sales/document_form.html",
        {"form": form, "title": "New Surat Jalan", "back_url": "sales:delivery-list"},
    )


@login_required
def delivery_detail(request, pk):
    _require(request.user, "sales.view_salesdelivery")
    try:
        delivery = sales_delivery_detail(request.user, pk=pk)
    except SalesDelivery.DoesNotExist:
        raise Http404 from None
    return render(
        request,
        "sales/delivery_detail.html",
        {
            "delivery": delivery,
            "can_change": request.user.has_perm("sales.change_salesdelivery")
            and delivery.state == SalesDeliveryState.DRAFT,
            "can_post": request.user.has_perm("sales.post_salesdelivery")
            and delivery.state == SalesDeliveryState.DRAFT,
            "can_cancel": request.user.has_perm("sales.cancel_salesdelivery")
            and delivery.state in {SalesDeliveryState.DRAFT, SalesDeliveryState.POSTED},
        },
    )


@login_required
def delivery_edit(request, pk):
    _require(request.user, "sales.change_salesdelivery")
    delivery = _delivery_or_404(request.user, pk)
    form = SalesDeliveryForm(request.POST or None, instance=delivery, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            update_draft_delivery(
                delivery,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            return redirect("sales:delivery-detail", pk=delivery.pk)
    return render(
        request,
        "sales/document_form.html",
        {
            "form": form,
            "title": f"Edit {delivery.document_number}",
            "back_url": "sales:delivery-detail",
            "back_pk": delivery.pk,
        },
    )


@login_required
def delivery_line_add(request, pk):
    _require(request.user, "sales.change_salesdelivery")
    delivery = _delivery_or_404(request.user, pk)
    form = SalesDeliveryLineForm(request.POST or None, user=request.user, delivery=delivery)
    if request.method == "POST" and form.is_valid():
        try:
            add_draft_delivery_line(
                delivery,
                actor=request.user,
                source_sales_order_line=form.cleaned_data["source_sales_order_line"],
                quantity=form.cleaned_data["quantity"],
                notes=form.cleaned_data["notes"],
                reason=form.cleaned_data.get("change_reason", ""),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            return redirect("sales:delivery-detail", pk=delivery.pk)
    return render(
        request,
        "sales/document_line_form.html",
        {
            "form": form,
            "document": delivery,
            "title": f"Add line to {delivery.document_number}",
            "kind": "delivery",
        },
    )


@login_required
def delivery_line_edit(request, pk, line_pk):
    _require(request.user, "sales.change_salesdelivery")
    delivery = _delivery_or_404(request.user, pk)
    line = get_object_or_404(SalesDeliveryLine.objects.filter(sales_delivery=delivery), pk=line_pk)
    form = SalesDeliveryLineForm(
        request.POST or None, instance=line, user=request.user, delivery=delivery
    )
    if request.method == "POST" and form.is_valid():
        try:
            update_draft_delivery_line(
                line,
                actor=request.user,
                quantity=form.cleaned_data["quantity"],
                notes=form.cleaned_data["notes"],
                reason=form.cleaned_data["change_reason"],
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            return redirect("sales:delivery-detail", pk=delivery.pk)
    return render(
        request,
        "sales/document_line_form.html",
        {
            "form": form,
            "document": delivery,
            "title": f"Edit line {line.line_number}",
            "kind": "delivery",
        },
    )


@login_required
def delivery_line_remove(request, pk, line_pk):
    _require(request.user, "sales.change_salesdelivery")
    delivery = _delivery_or_404(request.user, pk)
    line = get_object_or_404(SalesDeliveryLine.objects.filter(sales_delivery=delivery), pk=line_pk)
    form = SalesOrderTransitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            remove_draft_delivery_line(line, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            return redirect("sales:delivery-detail", pk=delivery.pk)
    return render(
        request,
        "sales/document_transition_form.html",
        {
            "form": form,
            "document": delivery,
            "title": "Remove delivery line",
            "submit_label": "Remove line",
            "danger": True,
            "kind": "delivery",
        },
    )


@login_required
def delivery_post(request, pk):
    _require(request.user, "sales.post_salesdelivery")
    delivery = _delivery_or_404(request.user, pk)
    if request.method == "POST":
        try:
            post_delivery(delivery, actor=request.user)
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(
                request, f"{delivery.document_number} posted as a Warehouse issue candidate."
            )
    return redirect("sales:delivery-detail", pk=delivery.pk)


@login_required
def delivery_cancel(request, pk):
    _require(request.user, "sales.cancel_salesdelivery")
    delivery = _delivery_or_404(request.user, pk)
    form = SalesOrderTransitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            cancel_delivery(delivery, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            return redirect("sales:delivery-detail", pk=delivery.pk)
    return render(
        request,
        "sales/document_transition_form.html",
        {
            "form": form,
            "document": delivery,
            "title": f"Cancel {delivery.document_number}",
            "submit_label": "Cancel delivery",
            "danger": True,
            "kind": "delivery",
        },
    )


@login_required
def delivery_print(request, pk):
    _require(request.user, "sales.view_salesdelivery")
    return render(
        request,
        "sales/delivery_print.html",
        {"delivery": sales_delivery_detail(request.user, pk=pk)},
    )


@login_required
def invoice_list(request):
    _require(request.user, "sales.view_salesinvoice")
    search = request.GET.get("q", "").strip()
    state = request.GET.get("state", "").strip()
    page = Paginator(sales_invoices(request.user, search=search, state=state), 25).get_page(
        request.GET.get("page")
    )
    return render(
        request,
        "sales/invoice_list.html",
        {
            "page": page,
            "search": search,
            "state": state,
            "states": SalesInvoiceState.choices,
            "can_add": request.user.has_perm("sales.add_salesinvoice"),
            "can_exception": request.user.has_perm("sales.create_salesorder_invoice"),
        },
    )


def _invoice_create(request, *, source_mode, document_kind, title):
    _require(request.user, "sales.add_salesinvoice")
    if (
        source_mode == InvoiceSourceMode.SALES_ORDER
        and document_kind == SalesInvoiceDocumentKind.INVOICE
    ):
        _require(request.user, "sales.create_salesorder_invoice")
    form = SalesInvoiceForm(request.POST or None, user=request.user, source_mode=source_mode)
    if request.method == "POST" and form.is_valid():
        try:
            if document_kind == SalesInvoiceDocumentKind.PROFORMA:
                invoice = create_proforma(actor=request.user, **_model_values(form))
            elif source_mode == InvoiceSourceMode.DELIVERY:
                invoice = create_draft_delivery_invoice(actor=request.user, **_model_values(form))
            else:
                invoice = create_draft_sales_order_invoice(
                    actor=request.user, **_model_values(form)
                )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{invoice.document_number} created as a draft.")
            return redirect("sales:invoice-detail", pk=invoice.pk)
    return render(
        request,
        "sales/document_form.html",
        {"form": form, "title": title, "back_url": "sales:invoice-list"},
    )


@login_required
def invoice_create_delivery(request):
    return _invoice_create(
        request,
        source_mode=InvoiceSourceMode.DELIVERY,
        document_kind=SalesInvoiceDocumentKind.INVOICE,
        title="New delivery-based Invoice Source",
    )


@login_required
def invoice_create_sales_order(request):
    return _invoice_create(
        request,
        source_mode=InvoiceSourceMode.SALES_ORDER,
        document_kind=SalesInvoiceDocumentKind.INVOICE,
        title="New Sales Order invoice exception",
    )


@login_required
def proforma_create(request):
    return _invoice_create(
        request,
        source_mode=InvoiceSourceMode.SALES_ORDER,
        document_kind=SalesInvoiceDocumentKind.PROFORMA,
        title="New Proforma",
    )


@login_required
def invoice_detail(request, pk):
    _require(request.user, "sales.view_salesinvoice")
    try:
        invoice = sales_invoice_detail(request.user, pk=pk)
    except SalesInvoice.DoesNotExist:
        raise Http404 from None
    return render(
        request,
        "sales/invoice_detail.html",
        {
            "invoice": invoice,
            "can_change": request.user.has_perm("sales.change_salesinvoice")
            and invoice.state == SalesInvoiceState.DRAFT,
            "can_confirm": request.user.has_perm("sales.confirm_salesinvoice")
            and invoice.state == SalesInvoiceState.DRAFT,
            "can_cancel": request.user.has_perm("sales.cancel_salesinvoice")
            and invoice.state in {SalesInvoiceState.DRAFT, SalesInvoiceState.CONFIRMED},
        },
    )


@login_required
def invoice_edit(request, pk):
    _require(request.user, "sales.change_salesinvoice")
    invoice = _invoice_or_404(request.user, pk)
    form = SalesInvoiceForm(request.POST or None, instance=invoice, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            update_draft_invoice(
                invoice,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_model_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            return redirect("sales:invoice-detail", pk=invoice.pk)
    return render(
        request,
        "sales/document_form.html",
        {
            "form": form,
            "title": f"Edit {invoice.document_number}",
            "back_url": "sales:invoice-detail",
            "back_pk": invoice.pk,
        },
    )


@login_required
def invoice_line_add(request, pk):
    _require(request.user, "sales.change_salesinvoice")
    invoice = _invoice_or_404(request.user, pk)
    form = SalesInvoiceLineForm(request.POST or None, user=request.user, invoice=invoice)
    if request.method == "POST" and form.is_valid():
        try:
            if invoice.source_mode == InvoiceSourceMode.DELIVERY:
                add_draft_delivery_invoice_line(
                    invoice,
                    actor=request.user,
                    source_sales_delivery_line=form.cleaned_data["source_sales_delivery_line"],
                    quantity=form.cleaned_data["quantity"],
                    notes=form.cleaned_data["notes"],
                    reason=form.cleaned_data.get("change_reason", ""),
                )
            else:
                add_draft_sales_order_invoice_line(
                    invoice,
                    actor=request.user,
                    source_sales_order_line=form.cleaned_data["source_sales_order_line"],
                    quantity=form.cleaned_data["quantity"],
                    notes=form.cleaned_data["notes"],
                    reason=form.cleaned_data.get("change_reason", ""),
                )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            return redirect("sales:invoice-detail", pk=invoice.pk)
    return render(
        request,
        "sales/document_line_form.html",
        {
            "form": form,
            "document": invoice,
            "title": f"Add source line to {invoice.document_number}",
            "kind": "invoice",
        },
    )


@login_required
def invoice_line_edit(request, pk, line_pk):
    _require(request.user, "sales.change_salesinvoice")
    invoice = _invoice_or_404(request.user, pk)
    line = get_object_or_404(SalesInvoiceLine.objects.filter(sales_invoice=invoice), pk=line_pk)
    form = SalesInvoiceLineForm(
        request.POST or None, instance=line, user=request.user, invoice=invoice
    )
    if request.method == "POST" and form.is_valid():
        try:
            update_draft_invoice_line(
                line,
                actor=request.user,
                quantity=form.cleaned_data["quantity"],
                notes=form.cleaned_data["notes"],
                reason=form.cleaned_data["change_reason"],
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            return redirect("sales:invoice-detail", pk=invoice.pk)
    return render(
        request,
        "sales/document_line_form.html",
        {
            "form": form,
            "document": invoice,
            "title": f"Edit line {line.line_number}",
            "kind": "invoice",
        },
    )


@login_required
def invoice_line_remove(request, pk, line_pk):
    _require(request.user, "sales.change_salesinvoice")
    invoice = _invoice_or_404(request.user, pk)
    line = get_object_or_404(SalesInvoiceLine.objects.filter(sales_invoice=invoice), pk=line_pk)
    form = SalesOrderTransitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            remove_draft_invoice_line(line, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            return redirect("sales:invoice-detail", pk=invoice.pk)
    return render(
        request,
        "sales/document_transition_form.html",
        {
            "form": form,
            "document": invoice,
            "title": "Remove invoice line",
            "submit_label": "Remove line",
            "danger": True,
            "kind": "invoice",
        },
    )


@login_required
def invoice_confirm(request, pk):
    _require(request.user, "sales.confirm_salesinvoice")
    invoice = _invoice_or_404(request.user, pk)
    if request.method == "POST":
        try:
            confirm_invoice(invoice, actor=request.user)
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(
                request, f"{invoice.document_number} confirmed as a commercial source."
            )
    return redirect("sales:invoice-detail", pk=invoice.pk)


@login_required
def invoice_cancel(request, pk):
    _require(request.user, "sales.cancel_salesinvoice")
    invoice = _invoice_or_404(request.user, pk)
    form = SalesOrderTransitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            cancel_invoice(invoice, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            return redirect("sales:invoice-detail", pk=invoice.pk)
    return render(
        request,
        "sales/document_transition_form.html",
        {
            "form": form,
            "document": invoice,
            "title": f"Cancel {invoice.document_number}",
            "submit_label": "Cancel invoice",
            "danger": True,
            "kind": "invoice",
        },
    )


@login_required
def invoice_print(request, pk):
    _require(request.user, "sales.view_salesinvoice")
    return render(
        request, "sales/invoice_print.html", {"invoice": sales_invoice_detail(request.user, pk=pk)}
    )
