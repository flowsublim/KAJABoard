from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.omnichannel.forms import OmniImportUploadForm, OmniPackingForm
from apps.omnichannel.selectors import (
    adjustment_sources,
    import_batches,
    omni_exceptions,
    omni_orders,
    operational_summary,
    order_daily_store_summary,
    packing_documents,
    payout_sources,
    reconciliation_dashboard,
    return_sources,
    revenue_events,
    settlement_sources,
    warehouse_demand,
)
from apps.omnichannel.services import (
    commit_bigseller_import,
    create_packing,
    post_packing,
    preview_bigseller_import,
)
from apps.organizations.selectors import effective_warehouses


def _require(request, codename):
    if not request.user.has_perm(f"omnichannel.{codename}"):
        raise PermissionDenied


@login_required
def dashboard(request):
    _require(request, "view_omniorder")
    return render(
        request,
        "omnichannel/dashboard.html",
        {
            "summary": operational_summary(request.user),
            "daily_summary": order_daily_store_summary(request.user),
        },
    )


@login_required
def import_orders(request):
    _require(request, "add_omniimportbatch")
    form = OmniImportUploadForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            batch = preview_bigseller_import(
                legal_entity=form.cleaned_data["legal_entity"],
                payload=form.cleaned_data["source_file"].read(),
                source_filename=form.cleaned_data["source_file"].name,
                actor=request.user,
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Preview import berhasil dibuat.")
            return redirect("omnichannel:import-detail", pk=batch.pk)
    return render(
        request,
        "omnichannel/import.html",
        {"form": form, "batches": import_batches(request.user)[:20]},
    )


@login_required
def import_detail(request, pk):
    _require(request, "view_omniimportbatch")
    batch = get_object_or_404(import_batches(request.user), pk=pk)
    return render(
        request,
        "omnichannel/import_detail.html",
        {"batch": batch, "rows": batch.rows.all().order_by("row_number")},
    )


@login_required
def import_commit(request, pk):
    _require(request, "change_omniimportbatch")
    if request.method != "POST":
        raise PermissionDenied
    batch = get_object_or_404(import_batches(request.user), pk=pk)
    try:
        commit_bigseller_import(
            batch=batch, actor=request.user, idempotency_key=request.POST.get("idempotency_key", "")
        )
    except ValidationError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Import BigSeller berhasil dikomit.")
    return redirect("omnichannel:import-detail", pk=batch.pk)


@login_required
def order_list(request):
    _require(request, "view_omniorder")
    return render(
        request,
        "omnichannel/order_list.html",
        {"orders": omni_orders(request.user, search=request.GET.get("q", ""))[:200]},
    )


@login_required
def order_detail(request, pk):
    _require(request, "view_omniorder")
    order = get_object_or_404(omni_orders(request.user), pk=pk)
    return render(
        request,
        "omnichannel/order_detail.html",
        {"order": order, "lines": order.lines.select_related("item", "mapping")},
    )


@login_required
def warehouse_queue(request):
    _require(request, "view_omniorder")
    warehouses = effective_warehouses(request.user)
    selected_warehouse = warehouses.filter(pk=request.GET.get("warehouse")).first()
    return render(
        request,
        "omnichannel/warehouse_queue.html",
        {
            "demand": warehouse_demand(request.user, warehouse=selected_warehouse),
            "warehouses": warehouses,
            "selected_warehouse": selected_warehouse,
        },
    )


@login_required
def packing_list(request):
    _require(request, "view_omnipacking")
    return render(
        request, "omnichannel/packing_list.html", {"packings": packing_documents(request.user)}
    )


@login_required
def packing_create(request):
    _require(request, "add_omnipacking")
    form = OmniPackingForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        line = form.cleaned_data["order_line"]
        try:
            packing = create_packing(
                legal_entity=line.order.legal_entity,
                store=line.order.store,
                warehouse=form.cleaned_data["warehouse"],
                packing_date=form.cleaned_data["packing_date"],
                lines=[{"order_line": line, "quantity": form.cleaned_data["quantity"]}],
                actor=request.user,
                notes=form.cleaned_data["notes"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Packing draft dibuat.")
            return redirect("omnichannel:packing-detail", pk=packing.pk)
    return render(request, "omnichannel/packing_form.html", {"form": form})


@login_required
def packing_detail(request, pk):
    _require(request, "view_omnipacking")
    packing = get_object_or_404(packing_documents(request.user), pk=pk)
    return render(
        request,
        "omnichannel/packing_detail.html",
        {
            "packing": packing,
            "lines": packing.lines.select_related(
                "order", "order_line", "item", "warehouse_movement"
            ),
        },
    )


@login_required
def packing_post(request, pk):
    _require(request, "post_omnipacking")
    if request.method != "POST":
        raise PermissionDenied
    packing = get_object_or_404(packing_documents(request.user), pk=pk)
    try:
        post_packing(
            packing, actor=request.user, idempotency_key=request.POST.get("idempotency_key", "")
        )
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Packing diposting melalui Warehouse.")
    return redirect("omnichannel:packing-detail", pk=packing.pk)


@login_required
def exception_list(request):
    _require(request, "view_omniexception")
    return render(
        request, "omnichannel/exception_list.html", {"exceptions": omni_exceptions(request.user)}
    )


def _source_list(request, codename, template_name, context_name, selector):
    _require(request, codename)
    return render(request, template_name, {context_name: selector(request.user)})


@login_required
def revenue_list(request):
    return _source_list(
        request,
        "view_omnirevenueevent",
        "omnichannel/revenue_list.html",
        "events",
        revenue_events,
    )


@login_required
def settlement_list(request):
    return _source_list(
        request,
        "view_omnisettlement",
        "omnichannel/settlement_list.html",
        "settlements",
        settlement_sources,
    )


@login_required
def return_list(request):
    return _source_list(
        request,
        "view_omnireturnsource",
        "omnichannel/return_list.html",
        "returns",
        return_sources,
    )


@login_required
def adjustment_list(request):
    return _source_list(
        request,
        "view_omniadjustmentsource",
        "omnichannel/adjustment_list.html",
        "adjustments",
        adjustment_sources,
    )


@login_required
def reconciliation(request):
    _require(request, "view_omniorder")
    return render(
        request,
        "omnichannel/reconciliation.html",
        reconciliation_dashboard(request.user),
    )


@login_required
def payout_list(request):
    return _source_list(
        request,
        "view_omnipayoutsource",
        "omnichannel/payout_list.html",
        "payouts",
        payout_sources,
    )
