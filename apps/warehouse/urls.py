from django.urls import path

from . import views

app_name = "warehouse"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("stock/", views.stock_list, name="stock-list"),
    path("movements/", views.movement_list, name="movement-list"),
    path("movements/<uuid:pk>/", views.movement_detail, name="movement-detail"),
    path("production/issues/", views.production_issue_list, name="production-issue-list"),
    path("production/receipts/", views.production_receipt_list, name="production-receipt-list"),
    path("purchase-receipts/", views.purchase_receipt_list, name="purchase-receipt-list"),
    path(
        "purchase-receipts/<uuid:pk>/",
        views.purchase_receipt_detail,
        name="purchase-receipt-detail",
    ),
    path("subcontract-receipts/", views.subcontract_receipt_list, name="subcontract-receipt-list"),
    path(
        "subcontract-receipts/<uuid:pk>/",
        views.subcontract_receipt_detail,
        name="subcontract-receipt-detail",
    ),
    path("sales-issues/", views.sales_issue_list, name="sales-issue-list"),
    path("sales-issues/<uuid:pk>/", views.sales_issue_detail, name="sales-issue-detail"),
    path("stock-opname/", views.stock_opname_list, name="stock-opname-list"),
    path("stock-opname/<uuid:pk>/", views.stock_opname_detail, name="stock-opname-detail"),
    path(
        "internal-consumption/", views.internal_consumption_list, name="internal-consumption-list"
    ),
    path("adjustments/", views.adjustment_list, name="adjustment-list"),
    path("supplier-returns/", views.supplier_return_list, name="supplier-return-list"),
    path("reconciliation/", views.reconciliation, name="reconciliation"),
]
