"""Incentives and CPO Finished Goods Fee views."""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Item
from apps.finance.models import IncentivePayablePosting
from apps.finance.selectors.incentive_payables import get_incentive_payable_status
from apps.finance.services.incentive_payables import (
    post_incentive_payable,
    reverse_incentive_payable_posting,
)
from apps.incentives.forms import EXECUTABLE_CALCULATION_METHODS, IncentiveRuleForm
from apps.incentives.models import (
    IncentiveAccrual,
    IncentiveAccrualState,
    IncentiveRule,
    IncentiveType,
)
from apps.incentives.selectors.cpo import get_cpo_candidate_for_receipt_line
from apps.incentives.services.accruals import approve_incentive_accrual
from apps.incentives.services.cpo import accrue_cpo_fee_for_receipt_line
from apps.organizations.selectors import accessible_legal_entities, user_can_access_entity
from apps.projects.models import Project
from apps.warehouse.models import WarehouseDocumentState, WarehouseReceiptLine

# =========================================================================
# 1. INCENTIVE RULES VIEWS
# =========================================================================


@login_required
@permission_required("incentives.view_incentiverule", raise_exception=True)
def rule_list(request):
    entities = accessible_legal_entities(request.user)
    rules = (
        IncentiveRule.objects.filter(legal_entity__in=entities)
        .select_related("legal_entity", "item")
        .order_by("code")
    )

    # Filters
    selected_type = request.GET.get("incentive_type", "")
    if selected_type:
        rules = rules.filter(incentive_type=selected_type)

    is_active_param = request.GET.get("is_active", "")
    if is_active_param == "1":
        rules = rules.filter(is_active=True)
    elif is_active_param == "0":
        rules = rules.filter(is_active=False)

    item_id = request.GET.get("item_id", "")
    if item_id:
        rules = rules.filter(item_id=item_id)

    q = request.GET.get("q", "").strip()
    if q:
        rules = rules.filter(code__icontains=q) | rules.filter(name__icontains=q)

    # Wrap rules with executable indicator
    annotated_rules = []
    for r in rules:
        annotated_rules.append(
            {
                "rule": r,
                "is_executable": r.calculation_method in EXECUTABLE_CALCULATION_METHODS,
            }
        )

    items = Item.objects.filter(is_active=True).order_by("code")

    return render(
        request,
        "incentives/rule_list.html",
        {
            "annotated_rules": annotated_rules,
            "incentive_types": IncentiveType.choices,
            "selected_type": selected_type,
            "is_active_param": is_active_param,
            "selected_item_id": item_id,
            "items": items,
            "q": q,
            "can_add": request.user.has_perm("incentives.add_incentiverule"),
            "can_change": request.user.has_perm("incentives.change_incentiverule"),
        },
    )


@login_required
@permission_required("incentives.add_incentiverule", raise_exception=True)
def rule_create(request):
    form = IncentiveRuleForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            rule = form.save(actor=request.user)
        except ValidationError:
            pass
        else:
            messages.success(request, f"Aturan insentif '{rule.code}' berhasil dibuat.")
            return redirect("incentives:rule-list")
    return render(
        request,
        "incentives/rule_form.html",
        {
            "form": form,
            "title": "Tambah Aturan Insentif",
            "is_create": True,
        },
    )


@login_required
@permission_required("incentives.change_incentiverule", raise_exception=True)
def rule_edit(request, pk):
    rule = get_object_or_404(IncentiveRule.objects.select_related("legal_entity"), pk=pk)
    if not user_can_access_entity(request.user, rule.legal_entity_id):
        return HttpResponseForbidden("Akses entitas tidak diizinkan.")

    form = IncentiveRuleForm(request.POST or None, instance=rule, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            updated_rule = form.save(actor=request.user)
        except ValidationError:
            pass
        else:
            messages.success(request, f"Aturan insentif '{updated_rule.code}' berhasil diperbarui.")
            return redirect("incentives:rule-list")
    return render(
        request,
        "incentives/rule_form.html",
        {
            "form": form,
            "title": f"Edit Aturan Insentif: {rule.code}",
            "is_create": False,
            "rule": rule,
        },
    )


# =========================================================================
# 2. CPO OPERATIONS DASHBOARD & DETAIL
# =========================================================================


@login_required
@permission_required("incentives.view_incentiveaccrual", raise_exception=True)
def cpo_dashboard(request):
    """Operational CPO reconciliation and management dashboard.

    Pure GET: creates 0 database writes.
    """
    entities = accessible_legal_entities(request.user)
    receipt_lines = (
        WarehouseReceiptLine.objects.filter(
            receipt__legal_entity__in=entities,
            receipt__state__in=[WarehouseDocumentState.POSTED, WarehouseDocumentState.REVERSED],
            receipt__source_module="production",
            receipt__source_type="PRODUCTION_HANDOVER",
        )
        .select_related(
            "receipt",
            "receipt__legal_entity",
            "receipt__work_order",
            "receipt__work_order__project",
            "receipt__handover",
            "receipt__handover__cpo_beneficiary",
            "item",
        )
        .order_by("-receipt__receipt_date", "-receipt__created_at", "sequence")
    )

    # Bounded filters
    date_from = request.GET.get("date_from", "")
    if date_from:
        receipt_lines = receipt_lines.filter(receipt__receipt_date__gte=date_from)

    date_to = request.GET.get("date_to", "")
    if date_to:
        receipt_lines = receipt_lines.filter(receipt__receipt_date__lte=date_to)

    project_id = request.GET.get("project_id", "")
    if project_id:
        receipt_lines = receipt_lines.filter(receipt__work_order__project_id=project_id)

    employee_id = request.GET.get("employee_id", "")
    if employee_id:
        receipt_lines = receipt_lines.filter(receipt__handover__cpo_beneficiary_id=employee_id)

    item_id = request.GET.get("item_id", "")
    if item_id:
        receipt_lines = receipt_lines.filter(item_id=item_id)

    status_filter = request.GET.get("status", "")

    # Evaluation items and summary counts
    summary = {
        "total_posted_lines": 0,
        "pending_rule": 0,
        "pending_beneficiary": 0,
        "ready": 0,
        "accrued": 0,
        "approved": 0,
        "approved_not_posted": 0,
        "payable_open": 0,
        "partially_paid": 0,
        "paid": 0,
        "source_reversed_finance_pending": 0,
        "reversed": 0,
        "authoritative_total_amount": Decimal("0"),
        "approved_total_amount": Decimal("0"),
    }

    evaluated_rows = []
    authoritative_states = {
        IncentiveAccrualState.ACCRUED,
        IncentiveAccrualState.APPROVED,
        IncentiveAccrualState.PAYABLE,
        IncentiveAccrualState.PAID,
    }
    finance_eligible_states = {
        IncentiveAccrualState.APPROVED,
        IncentiveAccrualState.PAYABLE,
        IncentiveAccrualState.PAID,
    }

    project_coverage_incomplete = False
    selected_project = None
    if project_id:
        selected_project = Project.objects.filter(pk=project_id).first()
        if selected_project:
            all_proj_lines = WarehouseReceiptLine.objects.filter(
                receipt__legal_entity_id=selected_project.legal_entity_id,
                receipt__work_order__project_id=selected_project.pk,
                receipt__state=WarehouseDocumentState.POSTED,
                receipt__source_module="production",
                receipt__source_type="PRODUCTION_HANDOVER",
            )
            for r_line in all_proj_lines:
                c_item = get_cpo_candidate_for_receipt_line(r_line)
                if not c_item.existing_accrual:
                    project_coverage_incomplete = True
                    break

    for line in receipt_lines:
        cand = get_cpo_candidate_for_receipt_line(line)
        summary["total_posted_lines"] += 1

        accrual = cand.existing_accrual
        recon_item = None
        op_status = cand.status

        if accrual:
            recon_item = get_incentive_payable_status(accrual)
            # Authoritative subtotal (includes ACCRUED, APPROVED, PAYABLE, PAID)
            if accrual.state in authoritative_states:
                summary["authoritative_total_amount"] += accrual.amount
            if accrual.state in finance_eligible_states:
                summary["approved_total_amount"] += accrual.amount

            # Resolve detailed operational status
            if recon_item.reconciliation_status == "SOURCE_REVERSED_FINANCE_REVERSAL_PENDING":
                op_status = "SOURCE_REVERSED_FINANCE_REVERSAL_PENDING"
                summary["source_reversed_finance_pending"] += 1
            elif recon_item.reconciliation_status == "REVERSED":
                op_status = "REVERSED"
                summary["reversed"] += 1
            elif recon_item.reconciliation_status == "PAID":
                op_status = "PAID"
                summary["paid"] += 1
            elif recon_item.reconciliation_status == "PARTIALLY_PAID":
                op_status = "PARTIALLY_PAID"
                summary["partially_paid"] += 1
            elif recon_item.reconciliation_status == "PAYABLE_OPEN":
                op_status = "PAYABLE_OPEN"
                summary["payable_open"] += 1
            elif recon_item.reconciliation_status == "APPROVED_NOT_POSTED":
                op_status = "APPROVED_NOT_POSTED"
                summary["approved_not_posted"] += 1
            elif accrual.state == IncentiveAccrualState.APPROVED:
                op_status = "APPROVED"
                summary["approved"] += 1
            elif accrual.state == IncentiveAccrualState.ACCRUED:
                op_status = "ACCRUED"
                summary["accrued"] += 1
            else:
                op_status = cand.status
        else:
            if cand.status == "PENDING_RULE":
                summary["pending_rule"] += 1
            elif cand.status in (
                "PENDING_BENEFICIARY",
                "INVALID_BENEFICIARY",
                "INACTIVE_BENEFICIARY",
            ):
                summary["pending_beneficiary"] += 1
            elif cand.status == "READY":
                summary["ready"] += 1

        # Check status filter
        if status_filter and op_status != status_filter:
            continue

        posting = getattr(accrual, "finance_posting", None) if accrual else None

        evaluated_rows.append(
            {
                "line": line,
                "candidate": cand,
                "accrual": accrual,
                "posting": posting,
                "reconciliation": recon_item,
                "operational_status": op_status,
            }
        )

    # Reference lists for filter dropdowns
    projects = Project.objects.filter(legal_entity__in=entities).order_by("code")
    items = Item.objects.filter(is_active=True).order_by("code")
    from apps.accounts.models import Employee

    beneficiaries = Employee.objects.filter(legal_entity__in=entities, is_active=True).order_by(
        "display_name"
    )

    can_accrue = request.user.has_perm("incentives.add_incentiveaccrual")
    can_approve = request.user.has_perm("incentives.change_incentiveaccrual")
    can_post_payable = request.user.has_perm("finance.post_journal") or request.user.has_perm(
        "finance.add_payableentry"
    )
    can_reverse_finance = request.user.has_perm("finance.reverse_journal")

    return render(
        request,
        "incentives/cpo_dashboard.html",
        {
            "rows": evaluated_rows,
            "summary": summary,
            "projects": projects,
            "items": items,
            "beneficiaries": beneficiaries,
            "selected_date_from": date_from,
            "selected_date_to": date_to,
            "selected_project_id": project_id,
            "selected_employee_id": employee_id,
            "selected_item_id": item_id,
            "selected_status": status_filter,
            "selected_project": selected_project,
            "project_coverage_incomplete": project_coverage_incomplete,
            "can_accrue": can_accrue,
            "can_approve": can_approve,
            "can_post_payable": can_post_payable,
            "can_reverse_finance": can_reverse_finance,
        },
    )


@login_required
@permission_required("incentives.view_incentiveaccrual", raise_exception=True)
def cpo_detail(request, pk):
    """Shows immutable snapshots and Finance lineage for a specific CPO accrual."""
    accrual = get_object_or_404(
        IncentiveAccrual.objects.select_related("legal_entity", "project", "rule"),
        pk=pk,
    )
    if not user_can_access_entity(request.user, accrual.legal_entity_id):
        return HttpResponseForbidden("Akses entitas tidak diizinkan.")

    recon_item = get_incentive_payable_status(accrual)
    posting = getattr(accrual, "finance_posting", None)

    return render(
        request,
        "incentives/cpo_detail.html",
        {
            "accrual": accrual,
            "recon_item": recon_item,
            "posting": posting,
            "can_approve": (
                request.user.has_perm("incentives.change_incentiveaccrual")
                and accrual.state == IncentiveAccrualState.ACCRUED
            ),
            "can_post_payable": (
                (
                    request.user.has_perm("finance.post_journal")
                    or request.user.has_perm("finance.add_payableentry")
                )
                and accrual.state == IncentiveAccrualState.APPROVED
                and not posting
            ),
        },
    )


# =========================================================================
# 3. OPERATIONAL ACTIONS (POST ONLY)
# =========================================================================


@login_required
@permission_required("incentives.add_incentiveaccrual", raise_exception=True)
@require_POST
def cpo_accrue_action(request, line_id):
    line = get_object_or_404(
        WarehouseReceiptLine.objects.select_related("receipt__legal_entity"),
        pk=line_id,
    )
    if not user_can_access_entity(request.user, line.receipt.legal_entity_id):
        return HttpResponseForbidden("Akses entitas tidak diizinkan.")

    try:
        accrual = accrue_cpo_fee_for_receipt_line(line, actor=request.user)
        messages.success(
            request,
            f"Akrual CPO Fee {accrual.currency_snapshot} {accrual.amount:,.0f} berhasil dicatat.",
        )
    except ValidationError as exc:
        err_msg = exc.message if hasattr(exc, "message") else str(exc)
        messages.error(request, f"Gagal mencatat akrual CPO: {err_msg}")

    return redirect("incentives:cpo-dashboard")


@login_required
@permission_required("incentives.change_incentiveaccrual", raise_exception=True)
@require_POST
def cpo_approve_action(request, accrual_id):
    accrual = get_object_or_404(
        IncentiveAccrual.objects.select_related("legal_entity"),
        pk=accrual_id,
    )
    if not user_can_access_entity(request.user, accrual.legal_entity_id):
        return HttpResponseForbidden("Akses entitas tidak diizinkan.")

    try:
        approve_incentive_accrual(accrual, actor=request.user)
        messages.success(request, "Akrual CPO Fee berhasil disetujui (APPROVED).")
    except ValidationError as exc:
        err_msg = exc.message if hasattr(exc, "message") else str(exc)
        messages.error(request, f"Gagal menyetujui akrual CPO: {err_msg}")

    return redirect("incentives:cpo-dashboard")


@login_required
@permission_required("finance.post_journal", raise_exception=True)
@require_POST
def cpo_post_payable_action(request, accrual_id):
    accrual = get_object_or_404(
        IncentiveAccrual.objects.select_related("legal_entity"),
        pk=accrual_id,
    )
    if not user_can_access_entity(request.user, accrual.legal_entity_id):
        return HttpResponseForbidden("Akses entitas tidak diizinkan.")

    try:
        posting = post_incentive_payable(accrual, actor=request.user)
        j_no = posting.journal.journal_number
        messages.success(
            request,
            f"Finance posting berhasil. Hutang tercatat pada Journal {j_no}.",
        )
    except ValidationError as exc:
        err_msg = exc.message if hasattr(exc, "message") else str(exc)
        messages.error(request, f"Gagal Finance posting: {err_msg}")

    return redirect("incentives:cpo-dashboard")


@login_required
@permission_required("finance.reverse_journal", raise_exception=True)
@require_POST
def cpo_reverse_finance_action(request, posting_id):
    posting = get_object_or_404(
        IncentivePayablePosting.objects.select_related("legal_entity", "payable_entry"),
        pk=posting_id,
    )
    if not user_can_access_entity(request.user, posting.legal_entity_id):
        return HttpResponseForbidden("Akses entitas tidak diizinkan.")

    try:
        reverse_incentive_payable_posting(posting, actor=request.user)
        messages.success(request, "Posting hutang insentif berhasil dikoreksi (REVERSED).")
    except ValidationError as exc:
        err_msg = exc.message if hasattr(exc, "message") else str(exc)
        messages.error(request, f"Koreksi Finance diblokir: {err_msg}")

    return redirect("incentives:cpo-dashboard")
