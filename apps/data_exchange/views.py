from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.data_exchange.forms import COAImportUploadForm, ConfirmImportForm
from apps.data_exchange.models import ImportBatch
from apps.data_exchange.selectors import import_batches, import_rows
from apps.data_exchange.services import coa_template_csv, confirm_import_batch, preview_coa_import


def _require(user, action, model):
    permission = f"{model._meta.app_label}.{action}_{model._meta.model_name}"
    if not user.has_perm(permission):
        raise PermissionDenied


def _add_form_error(form, error):
    if hasattr(error, "message_dict"):
        for field, errors in error.message_dict.items():
            target = field if field in form.fields else None
            for message in errors:
                form.add_error(target, message)
    else:
        for message in error.messages:
            form.add_error(None, message)


@login_required
def import_list(request):
    _require(request.user, "view", ImportBatch)
    search = request.GET.get("q", "").strip()
    import_type = request.GET.get("type", "").strip()
    page = Paginator(
        import_batches(request.user, search=search, import_type=import_type),
        25,
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "data_exchange/import_list.html",
        {
            "page": page,
            "search": search,
            "import_type": import_type,
            "can_add": request.user.has_perm("data_exchange.add_importbatch"),
            "can_change": request.user.has_perm("data_exchange.change_importbatch"),
        },
    )


@login_required
def coa_import_upload(request):
    _require(request.user, "add", ImportBatch)
    form = COAImportUploadForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        source_file = form.cleaned_data["source_file"]
        try:
            batch = preview_coa_import(
                legal_entity=form.cleaned_data["legal_entity"],
                payload=source_file.read(),
                source_filename=source_file.name,
                actor=request.user,
            )
        except ValidationError as error:
            _add_form_error(form, error)
        else:
            messages.success(request, f"Import preview ready: {batch.source_filename}.")
            return redirect("data_exchange:import-detail", pk=batch.pk)
    return render(
        request,
        "data_exchange/import_upload.html",
        {"form": form, "title": "Upload COA CSV"},
    )


@login_required
def coa_template_download(request):
    _require(request.user, "view", ImportBatch)
    return coa_template_csv()


@login_required
def import_detail(request, pk):
    _require(request.user, "view", ImportBatch)
    batch = get_object_or_404(import_batches(request.user), pk=pk)
    rows = import_rows(request.user, batch=batch)
    form = ConfirmImportForm()
    return render(
        request,
        "data_exchange/import_detail.html",
        {
            "batch": batch,
            "rows": rows,
            "form": form,
            "can_change": request.user.has_perm("data_exchange.change_importbatch"),
        },
    )


@login_required
def import_confirm(request, pk):
    _require(request.user, "change", ImportBatch)
    batch = get_object_or_404(import_batches(request.user), pk=pk)
    form = ConfirmImportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            batch = confirm_import_batch(
                batch=batch,
                actor=request.user,
                reason=form.cleaned_data["reason"],
            )
        except ValidationError as error:
            _add_form_error(form, error)
        else:
            messages.success(request, f"Import confirmed: {batch.status}.")
            return redirect("data_exchange:import-detail", pk=batch.pk)
    rows = import_rows(request.user, batch=batch)
    return render(
        request,
        "data_exchange/import_detail.html",
        {"batch": batch, "rows": rows, "form": form, "can_change": True},
    )
