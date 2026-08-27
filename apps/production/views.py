import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.organizations.selectors import user_can_access_entity
from apps.production.forms import (
    ConfirmationForm,
    CorrectionForm,
    ProductionRejectEntryForm,
    ProductionRejectLineForm,
    ProductionWarehouseHandoverForm,
    ProductionWarehouseHandoverLineForm,
    ProductionWorkEntryForm,
    ProductionWorkLineForm,
)
from apps.production.models import (
    ProductionEntryState,
    ProductionHandoverState,
    ProductionRejectLine,
    ProductionWarehouseHandoverLine,
    ProductionWorkLine,
)
from apps.production.selectors.wip import (
    output_wip_summaries,
    production_handovers,
    production_reject_entries,
    production_work_entries,
    work_order_progress,
)
from apps.production.services.production import (
    add_draft_reject_line,
    add_draft_work_line,
    add_handover_line,
    create_draft_reject_entry,
    create_draft_work_entry,
    create_handover_draft,
    mark_handover_ready,
    post_reject_entry,
    post_work_entry,
    remove_handover_line,
    reverse_handover_line,
    reverse_reject_line,
    reverse_work_line,
    update_draft_work_entry,
    update_handover_draft,
    update_handover_line,
)


def _errors(form, error):
    if hasattr(error, "message_dict"):
        for field, messages_ in error.message_dict.items():
            for message in messages_:
                form.add_error(field if field in form.fields else None, message)
    else:
        form.add_error(None, "; ".join(error.messages))


def _scope_or_403(user, entity):
    if not user_can_access_entity(user, entity.pk):
        raise PermissionError


@login_required
@permission_required("production.view_productionworkentry", raise_exception=True)
def wip_list(request):
    return render(
        request,
        "production/wip_list.html",
        {
            "entries": production_work_entries(request.user)[:50],
            "rejects": production_reject_entries(request.user)[:20],
            "can_add": request.user.has_perm("production.add_productionworkentry"),
        },
    )


@login_required
@permission_required("production.view_productionwarehousehandover", raise_exception=True)
def handover_list(request):
    return render(
        request,
        "production/handover_list.html",
        {
            "handovers": production_handovers(request.user)[:50],
            "can_add": request.user.has_perm("production.add_productionwarehousehandover"),
        },
    )


@login_required
@permission_required("production.view_productionwarehousehandover", raise_exception=True)
def handover_detail(request, pk):
    handover = get_object_or_404(
        production_handovers(request.user).prefetch_related("lines__output"), pk=pk
    )
    return render(
        request,
        "production/handover_detail.html",
        {
            "handover": handover,
            "summaries": output_wip_summaries(handover.work_order),
            "can_change": request.user.has_perm("production.change_productionwarehousehandover")
            and handover.state == ProductionHandoverState.DRAFT,
            "can_ready": request.user.has_perm("production.ready_productionwarehousehandover")
            and handover.state == ProductionHandoverState.DRAFT,
        },
    )


@login_required
@permission_required("production.view_productionwarehousehandover", raise_exception=True)
def handover_print(request, pk):
    handover = get_object_or_404(
        production_handovers(request.user).select_related("legal_entity", "work_order"), pk=pk
    )
    return render(request, "production/handover_print.html", {"handover": handover})


@login_required
@permission_required("production.add_productionwarehousehandover", raise_exception=True)
def handover_create(request):
    form = ProductionWarehouseHandoverForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            handover = create_handover_draft(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Draft Setor Gudang dibuat.")
            return redirect("production:handover-detail", pk=handover.pk)
    return render(request, "production/form.html", {"form": form, "title": "Setor Gudang"})


@login_required
@permission_required("production.change_productionwarehousehandover", raise_exception=True)
def handover_edit(request, pk):
    handover = get_object_or_404(production_handovers(request.user), pk=pk)
    form = ProductionWarehouseHandoverForm(
        request.POST or None, instance=handover, user=request.user
    )
    if request.method == "POST" and form.is_valid():
        try:
            update_handover_draft(handover, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Draft Setor Gudang diperbarui.")
            return redirect("production:handover-detail", pk=handover.pk)
    return render(request, "production/form.html", {"form": form, "title": "Edit Setor Gudang"})


@login_required
@permission_required("production.change_productionwarehousehandover", raise_exception=True)
def handover_line_add(request, pk):
    handover = get_object_or_404(production_handovers(request.user), pk=pk)
    form = ProductionWarehouseHandoverLineForm(request.POST or None)
    form.fields["output"].queryset = handover.work_order.outputs.all()
    if request.method == "POST" and form.is_valid():
        try:
            add_handover_line(handover, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Output handover ditambahkan.")
            return redirect("production:handover-detail", pk=handover.pk)
    return render(
        request, "production/form.html", {"form": form, "title": "Tambah Output Handover"}
    )


@login_required
@permission_required("production.change_productionwarehousehandover", raise_exception=True)
def handover_line_edit(request, pk):
    line = get_object_or_404(
        ProductionWarehouseHandoverLine.objects.select_related("handover__legal_entity"), pk=pk
    )
    if not user_can_access_entity(request.user, line.handover.legal_entity_id):
        return HttpResponseForbidden()
    form = ProductionWarehouseHandoverLineForm(request.POST or None, instance=line)
    form.fields["output"].queryset = line.handover.work_order.outputs.all()
    if request.method == "POST" and form.is_valid():
        try:
            update_handover_line(line, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Output handover diperbarui.")
            return redirect("production:handover-detail", pk=line.handover_id)
    return render(request, "production/form.html", {"form": form, "title": "Edit Output Handover"})


@login_required
@permission_required("production.change_productionwarehousehandover", raise_exception=True)
def handover_line_remove(request, pk):
    line = get_object_or_404(
        ProductionWarehouseHandoverLine.objects.select_related("handover__legal_entity"), pk=pk
    )
    if not user_can_access_entity(request.user, line.handover.legal_entity_id):
        return HttpResponseForbidden()
    form = ConfirmationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            remove_handover_line(line, actor=request.user)
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Output handover dihapus dari draft.")
            return redirect("production:handover-detail", pk=line.handover_id)
    return render(request, "production/form.html", {"form": form, "title": "Hapus Output Handover"})


@login_required
@permission_required("production.ready_productionwarehousehandover", raise_exception=True)
def handover_ready(request, pk):
    handover = get_object_or_404(production_handovers(request.user), pk=pk)
    form = CorrectionForm(request.POST or None, initial={"idempotency_key": str(uuid.uuid4())})
    if request.method == "POST" and form.is_valid():
        try:
            mark_handover_ready(
                handover, actor=request.user, idempotency_key=form.cleaned_data["idempotency_key"]
            )
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Handover Siap Gudang. Menunggu proses Warehouse.")
            return redirect("production:handover-detail", pk=handover.pk)
    return render(request, "production/form.html", {"form": form, "title": "Siap Gudang"})


@login_required
@permission_required("production.reverse_productionhandoverline", raise_exception=True)
def handover_line_reverse(request, pk):
    line = get_object_or_404(
        ProductionWarehouseHandoverLine.objects.select_related("handover__legal_entity"), pk=pk
    )
    if not user_can_access_entity(request.user, line.handover.legal_entity_id):
        return HttpResponseForbidden()
    form = CorrectionForm(request.POST or None, initial={"idempotency_key": str(uuid.uuid4())})
    if request.method == "POST" and form.is_valid():
        try:
            reverse_handover_line(line, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Baris handover dikoreksi.")
            return redirect("production:handover-detail", pk=line.handover_id)
    return render(request, "production/form.html", {"form": form, "title": "Koreksi Handover"})


@login_required
@permission_required("production.view_productionworkentry", raise_exception=True)
def wip_detail(request, pk):
    entry = get_object_or_404(
        production_work_entries(request.user).prefetch_related("lines__output"), pk=pk
    )
    return render(
        request,
        "production/wip_detail.html",
        {
            "entry": entry,
            "summaries": output_wip_summaries(entry.work_order),
            "progress": work_order_progress(entry.work_order),
            "can_change": request.user.has_perm("production.change_productionworkentry")
            and entry.state == ProductionEntryState.DRAFT,
            "can_post": request.user.has_perm("production.post_productionworkentry")
            and entry.state == ProductionEntryState.DRAFT,
        },
    )


@login_required
@permission_required("production.add_productionworkentry", raise_exception=True)
def work_create(request):
    form = ProductionWorkEntryForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            entry = create_draft_work_entry(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Draft WIP Produksi dibuat.")
            return redirect("production:wip-detail", pk=entry.pk)
    return render(request, "production/form.html", {"form": form, "title": "Tambah WIP Produksi"})


@login_required
@permission_required("production.change_productionworkentry", raise_exception=True)
def work_edit(request, pk):
    entry = get_object_or_404(production_work_entries(request.user), pk=pk)
    form = ProductionWorkEntryForm(request.POST or None, instance=entry, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            update_draft_work_entry(entry, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Draft WIP Produksi diperbarui.")
            return redirect("production:wip-detail", pk=entry.pk)
    return render(request, "production/form.html", {"form": form, "title": "Edit WIP Produksi"})


@login_required
@permission_required("production.change_productionworkentry", raise_exception=True)
def work_line_add(request, pk):
    entry = get_object_or_404(production_work_entries(request.user), pk=pk)
    form = ProductionWorkLineForm(request.POST or None)
    form.fields["output"].queryset = entry.work_order.outputs.all()
    if request.method == "POST" and form.is_valid():
        try:
            add_draft_work_line(entry, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Output ditambahkan.")
            return redirect("production:wip-detail", pk=entry.pk)
    return render(request, "production/form.html", {"form": form, "title": "Tambah Output"})


@login_required
@permission_required("production.post_productionworkentry", raise_exception=True)
def work_post(request, pk):
    entry = get_object_or_404(production_work_entries(request.user), pk=pk)
    form = CorrectionForm(request.POST or None, initial={"idempotency_key": str(uuid.uuid4())})
    if request.method == "POST" and form.is_valid():
        try:
            post_work_entry(
                entry, actor=request.user, idempotency_key=form.cleaned_data["idempotency_key"]
            )
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "WIP Produksi diposting.")
            return redirect("production:wip-detail", pk=entry.pk)
    return render(request, "production/form.html", {"form": form, "title": "Posting WIP Produksi"})


@login_required
@permission_required("production.reverse_productionworkline", raise_exception=True)
def work_line_reverse(request, pk):
    line = get_object_or_404(
        ProductionWorkLine.objects.select_related("entry__legal_entity"), pk=pk
    )
    if not user_can_access_entity(request.user, line.entry.legal_entity_id):
        return HttpResponseForbidden()
    form = CorrectionForm(request.POST or None, initial={"idempotency_key": str(uuid.uuid4())})
    if request.method == "POST" and form.is_valid():
        try:
            reverse_work_line(line, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Baris WIP dikoreksi.")
            return redirect("production:wip-detail", pk=line.entry_id)
    return render(request, "production/form.html", {"form": form, "title": "Koreksi WIP"})


@login_required
@permission_required("production.add_productionrejectentry", raise_exception=True)
def reject_create(request):
    form = ProductionRejectEntryForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            entry = create_draft_reject_entry(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            return redirect("production:reject-detail", pk=entry.pk)
    return render(
        request, "production/form.html", {"form": form, "title": "Tambah Reject Produksi"}
    )


@login_required
@permission_required("production.view_productionrejectentry", raise_exception=True)
def reject_detail(request, pk):
    entry = get_object_or_404(
        production_reject_entries(request.user).prefetch_related("lines__output"), pk=pk
    )
    return render(
        request,
        "production/reject_detail.html",
        {
            "entry": entry,
            "can_change": request.user.has_perm("production.change_productionrejectentry")
            and entry.state == ProductionEntryState.DRAFT,
            "can_post": request.user.has_perm("production.post_productionrejectentry")
            and entry.state == ProductionEntryState.DRAFT,
        },
    )


@login_required
@permission_required("production.change_productionrejectentry", raise_exception=True)
def reject_line_add(request, pk):
    entry = get_object_or_404(production_reject_entries(request.user), pk=pk)
    form = ProductionRejectLineForm(request.POST or None)
    form.fields["output"].queryset = entry.work_order.outputs.all()
    if request.method == "POST" and form.is_valid():
        try:
            add_draft_reject_line(entry, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            return redirect("production:reject-detail", pk=entry.pk)
    return render(request, "production/form.html", {"form": form, "title": "Tambah Reject"})


@login_required
@permission_required("production.post_productionrejectentry", raise_exception=True)
def reject_post(request, pk):
    entry = get_object_or_404(production_reject_entries(request.user), pk=pk)
    form = CorrectionForm(request.POST or None, initial={"idempotency_key": str(uuid.uuid4())})
    if request.method == "POST" and form.is_valid():
        try:
            post_reject_entry(
                entry, actor=request.user, idempotency_key=form.cleaned_data["idempotency_key"]
            )
        except ValidationError as error:
            _errors(form, error)
        else:
            return redirect("production:reject-detail", pk=entry.pk)
    return render(request, "production/form.html", {"form": form, "title": "Posting Reject"})


@login_required
@permission_required("production.reverse_productionrejectline", raise_exception=True)
def reject_line_reverse(request, pk):
    line = get_object_or_404(
        ProductionRejectLine.objects.select_related("entry__legal_entity"), pk=pk
    )
    if not user_can_access_entity(request.user, line.entry.legal_entity_id):
        return HttpResponseForbidden()
    form = CorrectionForm(request.POST or None, initial={"idempotency_key": str(uuid.uuid4())})
    if request.method == "POST" and form.is_valid():
        try:
            reverse_reject_line(line, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            return redirect("production:reject-detail", pk=line.entry_id)
    return render(request, "production/form.html", {"form": form, "title": "Koreksi Reject"})
