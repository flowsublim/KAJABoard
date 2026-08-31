from django.urls import path

from . import views

app_name = "omnichannel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("import/", views.import_orders, name="import"),
    path("import/<uuid:pk>/", views.import_detail, name="import-detail"),
    path("import/<uuid:pk>/commit/", views.import_commit, name="import-commit"),
    path("orders/", views.order_list, name="order-list"),
    path("orders/<uuid:pk>/", views.order_detail, name="order-detail"),
    path("warehouse-queue/", views.warehouse_queue, name="warehouse-queue"),
    path("packing/", views.packing_list, name="packing-list"),
    path("packing/create/", views.packing_create, name="packing-create"),
    path("packing/<uuid:pk>/", views.packing_detail, name="packing-detail"),
    path("packing/<uuid:pk>/post/", views.packing_post, name="packing-post"),
    path("exceptions/", views.exception_list, name="exception-list"),
    path("revenue/", views.revenue_list, name="revenue"),
    path("settlement/", views.settlement_list, name="settlement"),
    path("returns/", views.return_list, name="return-list"),
    path("adjustments/", views.adjustment_list, name="adjustment-list"),
    path("reconciliation/", views.reconciliation, name="reconciliation"),
    path("payout/", views.payout_list, name="payout"),
]
