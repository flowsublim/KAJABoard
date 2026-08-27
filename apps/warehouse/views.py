from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, render

from apps.warehouse.selectors import (
    production_material_issue_candidates,
    production_receipt_candidates,
    stock_balances,
    stock_movements,
)


@login_required
@permission_required("warehouse.view_inventoryvaluationstate", raise_exception=True)
def dashboard(request):
    balances = stock_balances(request.user)
    return render(
        request,
        "warehouse/dashboard.html",
        {
            "balances": balances[:50],
            "pending_material": production_material_issue_candidates(request.user)[:50],
            "pending_receipts": production_receipt_candidates(request.user)[:50],
        },
    )


@login_required
@permission_required("warehouse.view_inventoryvaluationstate", raise_exception=True)
def stock_list(request):
    return render(request, "warehouse/stock_list.html", {"balances": stock_balances(request.user)})


@login_required
@permission_required("warehouse.view_stockmovement", raise_exception=True)
def movement_list(request):
    return render(
        request, "warehouse/movement_list.html", {"movements": stock_movements(request.user)[:100]}
    )


@login_required
@permission_required("warehouse.view_stockmovement", raise_exception=True)
def movement_detail(request, pk):
    movement = get_object_or_404(stock_movements(request.user), pk=pk)
    return render(request, "warehouse/movement_detail.html", {"movement": movement})


@login_required
@permission_required("warehouse.view_warehousematerialissue", raise_exception=True)
def production_issue_list(request):
    return render(
        request,
        "warehouse/production_issue_list.html",
        {"candidates": production_material_issue_candidates(request.user)},
    )


@login_required
@permission_required("warehouse.view_warehousereceipt", raise_exception=True)
def production_receipt_list(request):
    return render(
        request,
        "warehouse/production_receipt_list.html",
        {"candidates": production_receipt_candidates(request.user)},
    )
