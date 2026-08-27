from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.purchasing.forms import (
    LifecycleReasonForm,
    PurchaseCategoryForm,
    PurchaseOrderForm,
    PurchaseOrderLineForm,
    WorkOrderForm,
    WorkOrderMaterialAllocationForm,
    WorkOrderOutputForm,
)
from apps.purchasing.models import (
    AccountingTreatment,
    PurchaseCategory,
    PurchaseOrder,
    PurchaseOrderState,
    WorkOrder,
    WorkOrderState,
)
from apps.purchasing.selectors import (
    purchase_categories,
    purchase_order_detail,
    purchase_orders,
    work_orders,
)
from apps.purchasing.selectors import (
    work_order_detail as select_work_order_detail,
)
from apps.purchasing.services import (
    add_material_allocation,
    add_purchase_order_line,
    add_work_order_output,
    approve_work_order,
    cancel_purchase_order,
    confirm_purchase_order,
    create_draft_purchase_order,
    create_draft_work_order,
    create_purchase_category,
    deactivate_purchase_category,
    reactivate_purchase_category,
    remove_material_allocation,
    remove_work_order_output,
    submit_work_order,
    update_draft_work_order,
    update_material_allocation,
    update_purchase_category,
    update_work_order_output,
    void_work_order,
)


def _require(user, action, model):
    permission = f"{model._meta.app_label}.{action}_{model._meta.model_name}"
    if not user.has_perm(permission):
        raise PermissionDenied


def _require_permission(user, permission):
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
def order_list(request):
    _require(request.user, "view", PurchaseOrder)
    page = Paginator(
        purchase_orders(request.user, search=request.GET.get("q", "").strip()), 25
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "purchasing/order_list.html",
        {"page": page, "can_add": request.user.has_perm("purchasing.add_purchaseorder")},
    )


@login_required
def order_create(request):
    _require(request.user, "add", PurchaseOrder)
    form = PurchaseOrderForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            order = create_draft_purchase_order(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, "Pembelian berhasil disimpan.")
            return redirect("purchasing_operations:order-detail", pk=order.pk)
    return render(
        request, "purchasing/order_form.html", {"form": form, "title": "Tambah Pembelian"}
    )


@login_required
def order_detail(request, pk):
    _require(request.user, "view", PurchaseOrder)
    order = get_object_or_404(purchase_orders(request.user), pk=pk)
    return render(
        request,
        "purchasing/order_detail.html",
        {
            "order": purchase_order_detail(request.user, pk=order.pk),
            "can_change": request.user.has_perm("purchasing.change_purchaseorder")
            and order.state == PurchaseOrderState.DRAFT,
            "can_confirm": request.user.has_perm("purchasing.confirm_purchaseorder")
            and order.state == PurchaseOrderState.DRAFT,
            "can_cancel": request.user.has_perm("purchasing.cancel_purchaseorder")
            and order.state in {PurchaseOrderState.DRAFT, PurchaseOrderState.CONFIRMED},
        },
    )


@login_required
def order_line_add(request, pk):
    _require(request.user, "change", PurchaseOrder)
    order = get_object_or_404(purchase_orders(request.user), pk=pk)
    form = PurchaseOrderLineForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            add_purchase_order_line(order, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, "Item pembelian ditambahkan.")
            return redirect("purchasing_operations:order-detail", pk=order.pk)
    return render(
        request, "purchasing/order_form.html", {"form": form, "title": "Tambah Item Pembelian"}
    )


@login_required
def order_confirm(request, pk):
    _require(request.user, "confirm_purchaseorder")
    order = get_object_or_404(purchase_orders(request.user), pk=pk)
    if request.method == "POST":
        try:
            confirm_purchase_order(order, actor=request.user)
            messages.success(request, "Pembelian dikonfirmasi.")
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        return redirect("purchasing_operations:order-detail", pk=order.pk)


@login_required
def order_cancel(request, pk):
    _require(request.user, "cancel_purchaseorder")
    order = get_object_or_404(purchase_orders(request.user), pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            cancel_purchase_order(order, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, "Pembelian dibatalkan.")
            return redirect("purchasing_operations:order-detail", pk=order.pk)
    return render(
        request,
        "master/lifecycle_form.html",
        {"form": form, "object": order, "cancel_url": "purchasing:order-detail"},
    )


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


@login_required
def work_order_list(request):
    _require(request.user, "view", WorkOrder)
    page = Paginator(work_orders(request.user), 25).get_page(request.GET.get("page"))
    return render(
        request,
        "purchasing/work_order_list.html",
        {"page": page, "can_add": request.user.has_perm("purchasing.add_workorder")},
    )


@login_required
def work_order_create(request):
    _require(request.user, "add", WorkOrder)
    form = WorkOrderForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            work_order = create_draft_work_order(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, "SPK berhasil disimpan.")
            return redirect("purchasing_operations:work-order-detail", pk=work_order.pk)
    return render(request, "purchasing/work_order_form.html", {"form": form, "title": "Tambah SPK"})


@login_required
def work_order_detail(request, pk):
    _require(request.user, "view", WorkOrder)
    work_order = get_object_or_404(work_orders(request.user), pk=pk)
    return render(
        request,
        "purchasing/work_order_detail.html",
        {
            "work_order": select_work_order_detail(request.user, pk=work_order.pk),
            "can_change": request.user.has_perm("purchasing.change_workorder")
            and work_order.state == WorkOrderState.DRAFT,
            "can_submit": request.user.has_perm("purchasing.submit_workorder")
            and work_order.state == WorkOrderState.DRAFT,
            "can_approve": request.user.has_perm("purchasing.approve_workorder")
            and work_order.state == WorkOrderState.SUBMITTED,
            "can_void": request.user.has_perm("purchasing.void_workorder")
            and work_order.state != WorkOrderState.VOID,
        },
    )


@login_required
def work_order_edit(request, pk):
    _require(request.user, "change", WorkOrder)
    work_order = get_object_or_404(work_orders(request.user), pk=pk)
    form = WorkOrderForm(request.POST or None, instance=work_order, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            update_draft_work_order(work_order, actor=request.user, **_model_values(form))
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, "SPK berhasil diperbarui.")
            return redirect("purchasing_operations:work-order-detail", pk=work_order.pk)
    return render(request, "purchasing/work_order_form.html", {"form": form, "title": "Edit SPK"})


@login_required
def work_order_output_add(request, pk):
    _require(request.user, "change", WorkOrder)
    work_order = get_object_or_404(work_orders(request.user), pk=pk)
    form = WorkOrderOutputForm(request.POST or None, work_order=work_order)
    if request.method == "POST" and form.is_valid():
        try:
            add_work_order_output(work_order, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, "Output SPK ditambahkan.")
            return redirect("purchasing_operations:work-order-detail", pk=work_order.pk)
    return render(
        request, "purchasing/work_order_form.html", {"form": form, "title": "Tambah Output SPK"}
    )


@login_required
def work_order_output_edit(request, pk, output_pk):
    _require(request.user, "change", WorkOrder)
    work_order = get_object_or_404(work_orders(request.user), pk=pk)
    output = get_object_or_404(work_order.outputs, pk=output_pk)
    form = WorkOrderOutputForm(request.POST or None, instance=output, work_order=work_order)
    if request.method == "POST" and form.is_valid():
        try:
            update_work_order_output(
                output,
                actor=request.user,
                target_quantity=form.cleaned_data["target_quantity"],
                due_date=form.cleaned_data["due_date"],
                notes=form.cleaned_data["notes"],
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, "Output SPK diperbarui.")
            return redirect("purchasing_operations:work-order-detail", pk=work_order.pk)
    return render(
        request, "purchasing/work_order_form.html", {"form": form, "title": "Edit Output SPK"}
    )


@login_required
def work_order_output_remove(request, pk, output_pk):
    _require(request.user, "change", WorkOrder)
    work_order = get_object_or_404(work_orders(request.user), pk=pk)
    output = get_object_or_404(work_order.outputs, pk=output_pk)
    if request.method == "POST":
        try:
            remove_work_order_output(output, actor=request.user)
            messages.success(request, "Output SPK dihapus.")
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        return redirect("purchasing_operations:work-order-detail", pk=work_order.pk)
    return render(
        request,
        "purchasing/work_order_action.html",
        {"work_order": work_order, "action_title": "Hapus Output", "action_label": "Hapus"},
    )


@login_required
def work_order_material_add(request, pk):
    _require(request.user, "change", WorkOrder)
    work_order = get_object_or_404(work_orders(request.user), pk=pk)
    form = WorkOrderMaterialAllocationForm(request.POST or None, work_order=work_order)
    if request.method == "POST" and form.is_valid():
        try:
            add_material_allocation(work_order, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, "Alokasi bahan ditambahkan.")
            return redirect("purchasing_operations:work-order-detail", pk=work_order.pk)
    return render(
        request, "purchasing/work_order_form.html", {"form": form, "title": "Tambah Alokasi Bahan"}
    )


@login_required
def work_order_material_edit(request, pk, allocation_pk):
    _require(request.user, "change", WorkOrder)
    work_order = get_object_or_404(work_orders(request.user), pk=pk)
    allocation = get_object_or_404(work_order.material_allocations, pk=allocation_pk)
    form = WorkOrderMaterialAllocationForm(
        request.POST or None, instance=allocation, work_order=work_order
    )
    if request.method == "POST" and form.is_valid():
        try:
            update_material_allocation(
                allocation,
                actor=request.user,
                planned_quantity=form.cleaned_data["planned_quantity"],
                reference_cost=form.cleaned_data["reference_cost"],
                notes=form.cleaned_data["notes"],
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, "Alokasi bahan diperbarui.")
            return redirect("purchasing_operations:work-order-detail", pk=work_order.pk)
    return render(
        request, "purchasing/work_order_form.html", {"form": form, "title": "Edit Alokasi Bahan"}
    )


@login_required
def work_order_material_remove(request, pk, allocation_pk):
    _require(request.user, "change", WorkOrder)
    work_order = get_object_or_404(work_orders(request.user), pk=pk)
    allocation = get_object_or_404(work_order.material_allocations, pk=allocation_pk)
    if request.method == "POST":
        try:
            remove_material_allocation(allocation, actor=request.user)
            messages.success(request, "Alokasi bahan dihapus.")
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        return redirect("purchasing_operations:work-order-detail", pk=work_order.pk)
    return render(
        request,
        "purchasing/work_order_action.html",
        {"work_order": work_order, "action_title": "Hapus Alokasi Bahan", "action_label": "Hapus"},
    )


@login_required
def work_order_submit(request, pk):
    _require_permission(request.user, "purchasing.submit_workorder")
    work_order = get_object_or_404(work_orders(request.user), pk=pk)
    if request.method == "POST":
        try:
            submit_work_order(work_order, actor=request.user)
            messages.success(request, "SPK diajukan.")
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        return redirect("purchasing_operations:work-order-detail", pk=work_order.pk)
    return render(
        request,
        "purchasing/work_order_action.html",
        {"work_order": work_order, "action_title": "Ajukan SPK", "action_label": "Ajukan"},
    )


@login_required
def work_order_approve(request, pk):
    _require_permission(request.user, "purchasing.approve_workorder")
    work_order = get_object_or_404(work_orders(request.user), pk=pk)
    if request.method == "POST":
        try:
            approve_work_order(work_order, actor=request.user)
            messages.success(request, "SPK disetujui.")
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        return redirect("purchasing_operations:work-order-detail", pk=work_order.pk)
    return render(
        request,
        "purchasing/work_order_action.html",
        {"work_order": work_order, "action_title": "Setujui SPK", "action_label": "Setujui"},
    )


@login_required
def work_order_void(request, pk):
    _require_permission(request.user, "purchasing.void_workorder")
    work_order = get_object_or_404(work_orders(request.user), pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            void_work_order(work_order, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, "SPK di-void.")
            return redirect("purchasing_operations:work-order-detail", pk=work_order.pk)
    return render(
        request, "purchasing/work_order_void_form.html", {"form": form, "work_order": work_order}
    )


@login_required
def work_order_print(request, pk):
    _require(request.user, "view", WorkOrder)
    work_order = select_work_order_detail(request.user, pk=pk)
    return render(request, "purchasing/work_order_print.html", {"work_order": work_order})
