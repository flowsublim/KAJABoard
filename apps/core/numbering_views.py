from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.forms import DocumentSequenceForm, LifecycleReasonForm, NumberPreviewForm
from apps.core.models import DocumentSequence
from apps.core.selectors import document_sequences
from apps.core.services import (
    create_document_sequence,
    deactivate_document_sequence,
    preview_document_number,
    reactivate_document_sequence,
    update_document_sequence,
)


def _require(user, action):
    if not user.has_perm(f"core.{action}_documentsequence"):
        raise PermissionDenied


def _values(form):
    model_fields = {field.name for field in DocumentSequence._meta.fields}
    return {key: value for key, value in form.cleaned_data.items() if key in model_fields}


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
def sequence_list(request):
    _require(request.user, "view")
    include_inactive = request.GET.get("inactive") == "1"
    search = request.GET.get("q", "").strip()
    queryset = document_sequences(request.user, include_inactive=include_inactive)
    if search:
        queryset = queryset.filter(
            Q(document_type__icontains=search)
            | Q(name__icontains=search)
            | Q(prefix__icontains=search)
        )
    page = Paginator(queryset, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "numbering/sequence_list.html",
        {
            "page": page,
            "search": search,
            "include_inactive": include_inactive,
            "can_add": request.user.has_perm("core.add_documentsequence"),
            "can_change": request.user.has_perm("core.change_documentsequence"),
        },
    )


@login_required
def sequence_create(request):
    _require(request.user, "add")
    form = DocumentSequenceForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            sequence = create_document_sequence(
                actor=request.user,
                reason=form.cleaned_data.get("change_reason", ""),
                **_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{sequence} created.")
            return redirect("numbering:list")
    return render(request, "numbering/sequence_form.html", {"form": form, "title": "New Series"})


@login_required
def sequence_edit(request, pk):
    _require(request.user, "change")
    sequence = get_object_or_404(document_sequences(request.user, include_inactive=True), pk=pk)
    form = DocumentSequenceForm(request.POST or None, instance=sequence, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            sequence = update_document_sequence(
                sequence,
                actor=request.user,
                reason=form.cleaned_data["change_reason"],
                **_values(form),
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(request, f"{sequence} updated.")
            return redirect("numbering:list")
    return render(
        request,
        "numbering/sequence_form.html",
        {"form": form, "title": f"Edit {sequence}"},
    )


@login_required
def sequence_lifecycle(request, pk):
    _require(request.user, "change")
    sequence = get_object_or_404(document_sequences(request.user, include_inactive=True), pk=pk)
    form = LifecycleReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = (
            deactivate_document_sequence if sequence.is_active else reactivate_document_sequence
        )
        try:
            sequence = service(sequence, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"{sequence} {'activated' if sequence.is_active else 'deactivated'}.",
            )
            return redirect("numbering:list")
    return render(
        request,
        "master/lifecycle_form.html",
        {"form": form, "object": sequence, "cancel_url": "numbering:list"},
    )


@login_required
def sequence_preview(request, pk):
    _require(request.user, "view")
    sequence = get_object_or_404(document_sequences(request.user, include_inactive=True), pk=pk)
    form_data = request.GET or {"business_date": timezone.localdate().isoformat()}
    form = NumberPreviewForm(form_data)
    preview = None
    if form.is_valid():
        try:
            preview = preview_document_number(
                sequence.legal_entity,
                sequence.document_type,
                business_date=form.cleaned_data["business_date"],
            )
        except ValidationError as error:
            _add_service_errors(form, error)
    return render(
        request,
        "numbering/sequence_preview.html",
        {"form": form, "sequence": sequence, "preview": preview},
    )
