import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.production.models import ProductionWarehouseHandoverLine
from apps.quality.forms import QualityCorrectionForm, QualityInspectionForm
from apps.quality.models import QualityDocumentState
from apps.quality.selectors import (
    production_quality_queue,
    quality_inspections,
    rework_candidates,
)
from apps.quality.services import (
    create_from_production_handover,
    create_inspection,
    post_inspection,
    reverse_inspection,
)


def _errors(form, error):
    if hasattr(error, "message_dict"):
        for field, errors in error.message_dict.items():
            for message in errors:
                form.add_error(field if field in form.fields else None, message)
    else:
        form.add_error(None, "; ".join(error.messages))


@login_required
@permission_required("quality.view_qualityinspection", raise_exception=True)
def dashboard(request):
    inspections = quality_inspections(request.user)
    queue = production_quality_queue(request.user)
    return render(
        request,
        "quality/dashboard.html",
        {
            "pending_production": queue[:50],
            "inspections": inspections[:20],
            "rework": rework_candidates(request.user)[:20],
            "hold_count": sum(1 for row in inspections if row.state == QualityDocumentState.POSTED),
        },
    )


@login_required
@permission_required("quality.view_qualityinspection", raise_exception=True)
def inspection_list(request):
    return render(
        request,
        "quality/inspection_list.html",
        {"inspections": quality_inspections(request.user)[:100]},
    )


@login_required
@permission_required("quality.view_qualityinspection", raise_exception=True)
def inspection_detail(request, pk):
    inspection = get_object_or_404(
        quality_inspections(request.user).prefetch_related(
            "lines__item", "lines__production_handover_line__handover", "lines__reversal"
        ),
        pk=pk,
    )
    return render(
        request,
        "quality/inspection_detail.html",
        {
            "inspection": inspection,
            "can_post": request.user.has_perm("quality.post_qualityinspection")
            and inspection.state == QualityDocumentState.DRAFT,
            "can_reverse": request.user.has_perm("quality.reverse_qualityinspection")
            and inspection.state == QualityDocumentState.POSTED,
        },
    )


@login_required
@permission_required("quality.view_qualityinspection", raise_exception=True)
def production_queue(request):
    return render(
        request,
        "quality/production_queue.html",
        {"queue": production_quality_queue(request.user)},
    )


@login_required
@permission_required("quality.add_qualityinspection", raise_exception=True)
def inspection_create(request):
    form = QualityInspectionForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            inspection = create_inspection(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Draft inspeksi dibuat.")
            return redirect("quality:inspection-detail", pk=inspection.pk)
    return render(request, "quality/form.html", {"form": form, "title": "Inspeksi Baru"})


@login_required
@permission_required("quality.add_qualityinspection", raise_exception=True)
def production_inspection_create(request, handover_line_pk):
    source = get_object_or_404(
        ProductionWarehouseHandoverLine.objects.select_related("handover__legal_entity"),
        pk=handover_line_pk,
    )
    if (
        not request.user.organization_memberships.filter(
            legal_entity_id=source.handover.legal_entity_id, is_active=True
        ).exists()
        and not request.user.is_superuser
    ):
        return render(request, "quality/forbidden.html", status=403)
    if request.method == "POST":
        try:
            inspection = create_from_production_handover(source, actor=request.user)
        except ValidationError as error:
            form = QualityInspectionForm(request.POST or None, user=request.user)
            _errors(form, error)
        else:
            messages.success(request, "Draft inspeksi Production dibuat.")
            return redirect("quality:inspection-detail", pk=inspection.pk)
    form = QualityInspectionForm(
        user=request.user, initial={"inspection_type": "PRODUCTION_FINISHED_GOODS"}
    )
    return render(request, "quality/form.html", {"form": form, "title": "Inspeksi FG Produksi"})


@login_required
@permission_required("quality.post_qualityinspection", raise_exception=True)
def inspection_post(request, pk):
    inspection = get_object_or_404(quality_inspections(request.user), pk=pk)
    form = QualityCorrectionForm(
        request.POST or None,
        initial={"idempotency_key": str(uuid.uuid4()), "reason": "Posting inspeksi"},
    )
    if request.method == "POST" and form.is_valid():
        try:
            post_inspection(
                inspection, actor=request.user, idempotency_key=form.cleaned_data["idempotency_key"]
            )
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Inspeksi diposting dan menjadi fakta Quality immutable.")
            return redirect("quality:inspection-detail", pk=inspection.pk)
    return render(request, "quality/form.html", {"form": form, "title": "Post Inspeksi"})


@login_required
@permission_required("quality.reverse_qualityinspection", raise_exception=True)
def inspection_reverse(request, pk):
    inspection = get_object_or_404(quality_inspections(request.user), pk=pk)
    form = QualityCorrectionForm(
        request.POST or None, initial={"idempotency_key": str(uuid.uuid4())}
    )
    if request.method == "POST" and form.is_valid():
        try:
            reverse_inspection(inspection, actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, "Inspeksi dibalik; histori asli tetap tersimpan.")
            return redirect("quality:inspection-detail", pk=inspection.pk)
    return render(
        request, "quality/form.html", {"form": form, "title": "Koreksi / Reversal Inspeksi"}
    )
