from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, render

from apps.warehouse.models import (
    InternalConsumption,
    InventoryAdjustment,
    StockCount,
    SupplierReturn,
    WarehousePurchaseReceipt,
    WarehouseSalesIssue,
    WarehouseSubcontractReceipt,
)
from apps.warehouse.selectors import (
    production_material_issue_candidates,
    production_receipt_candidates,
    purchase_receipt_candidates,
    reconciliation_rows,
    sales_issue_candidates,
    stock_balances,
    stock_movements,
    subcontract_receipt_candidates,
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
            "purchase_receipts": purchase_receipt_candidates(request.user)[:50],
            "subcontract_receipts": subcontract_receipt_candidates(request.user)[:50],
            "sales_issues": sales_issue_candidates(request.user)[:50],
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


@login_required
@permission_required("warehouse.view_warehousepurchasereceipt", raise_exception=True)
def purchase_receipt_list(request):
    return render(
        request,
        "warehouse/purchase_receipt_list.html",
        {"candidates": purchase_receipt_candidates(request.user)},
    )


@login_required
@permission_required("warehouse.view_warehousepurchasereceipt", raise_exception=True)
def purchase_receipt_detail(request, pk):
    receipt = get_object_or_404(
        WarehousePurchaseReceipt.objects.filter(
            legal_entity__in=request.user.organization_memberships.filter(is_active=True).values(
                "legal_entity"
            )
        ),
        pk=pk,
    )
    return render(
        request,
        "warehouse/operational_detail.html",
        {
            "document": receipt,
            "title": "Penerimaan Pembelian",
            "lines": receipt.lines.select_related("item"),
        },
    )


@login_required
@permission_required("warehouse.view_warehousesubcontractreceipt", raise_exception=True)
def subcontract_receipt_list(request):
    return render(
        request,
        "warehouse/subcontract_receipt_list.html",
        {"candidates": subcontract_receipt_candidates(request.user)},
    )


@login_required
@permission_required("warehouse.view_warehousesubcontractreceipt", raise_exception=True)
def subcontract_receipt_detail(request, pk):
    receipt = get_object_or_404(
        WarehouseSubcontractReceipt.objects.filter(
            legal_entity__in=request.user.organization_memberships.filter(is_active=True).values(
                "legal_entity"
            )
        ),
        pk=pk,
    )
    return render(
        request,
        "warehouse/operational_detail.html",
        {
            "document": receipt,
            "title": "Penerimaan Maklun",
            "lines": receipt.lines.select_related("item"),
        },
    )


@login_required
@permission_required("warehouse.view_warehousesalesissue", raise_exception=True)
def sales_issue_list(request):
    return render(
        request,
        "warehouse/sales_issue_list.html",
        {"candidates": sales_issue_candidates(request.user)},
    )


@login_required
@permission_required("warehouse.view_warehousesalesissue", raise_exception=True)
def sales_issue_detail(request, pk):
    issue = get_object_or_404(
        WarehouseSalesIssue.objects.filter(
            legal_entity__in=request.user.organization_memberships.filter(is_active=True).values(
                "legal_entity"
            )
        ),
        pk=pk,
    )
    return render(
        request,
        "warehouse/operational_detail.html",
        {
            "document": issue,
            "title": "Pengeluaran Penjualan",
            "lines": issue.lines.select_related("item"),
        },
    )


@login_required
@permission_required("warehouse.view_stockcount", raise_exception=True)
def stock_opname_list(request):
    return render(
        request,
        "warehouse/stock_opname_list.html",
        {
            "documents": StockCount.objects.filter(
                legal_entity__in=request.user.organization_memberships.filter(
                    is_active=True
                ).values("legal_entity")
            ).select_related("warehouse")
        },
    )


@login_required
@permission_required("warehouse.view_stockcount", raise_exception=True)
def stock_opname_detail(request, pk):
    count = get_object_or_404(
        StockCount.objects.filter(
            legal_entity__in=request.user.organization_memberships.filter(is_active=True).values(
                "legal_entity"
            )
        ),
        pk=pk,
    )
    return render(
        request,
        "warehouse/operational_detail.html",
        {"document": count, "title": "Stock Opname", "lines": count.lines.select_related("item")},
    )


@login_required
@permission_required("warehouse.view_internalconsumption", raise_exception=True)
def internal_consumption_list(request):
    return render(
        request,
        "warehouse/document_list.html",
        {
            "title": "Pemakaian Internal",
            "documents": InternalConsumption.objects.filter(
                legal_entity__in=request.user.organization_memberships.filter(
                    is_active=True
                ).values("legal_entity")
            ).select_related("warehouse"),
        },
    )


@login_required
@permission_required("warehouse.view_inventoryadjustment", raise_exception=True)
def adjustment_list(request):
    return render(
        request,
        "warehouse/document_list.html",
        {
            "title": "Penyesuaian",
            "documents": InventoryAdjustment.objects.filter(
                legal_entity__in=request.user.organization_memberships.filter(
                    is_active=True
                ).values("legal_entity")
            ).select_related("warehouse"),
        },
    )


@login_required
@permission_required("warehouse.view_supplierreturn", raise_exception=True)
def supplier_return_list(request):
    return render(
        request,
        "warehouse/document_list.html",
        {
            "title": "Retur Supplier",
            "documents": SupplierReturn.objects.filter(
                legal_entity__in=request.user.organization_memberships.filter(
                    is_active=True
                ).values("legal_entity")
            ).select_related("warehouse", "supplier"),
        },
    )


@login_required
@permission_required("warehouse.view_inventoryvaluationstate", raise_exception=True)
def reconciliation(request):
    return render(
        request, "warehouse/reconciliation.html", {"rows": reconciliation_rows(request.user)}
    )
