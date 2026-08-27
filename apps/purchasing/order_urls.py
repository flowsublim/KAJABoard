from django.urls import path

from apps.purchasing import views

app_name = "purchasing_operations"
urlpatterns = [
    path("", views.order_list, name="order-list"),
    path("new/", views.order_create, name="order-create"),
    path("<uuid:pk>/", views.order_detail, name="order-detail"),
    path("<uuid:pk>/lines/new/", views.order_line_add, name="order-line-add"),
    path("<uuid:pk>/confirm/", views.order_confirm, name="order-confirm"),
    path("<uuid:pk>/cancel/", views.order_cancel, name="order-cancel"),
    path("spk/", views.work_order_list, name="work-order-list"),
    path("spk/new/", views.work_order_create, name="work-order-create"),
    path("spk/<uuid:pk>/", views.work_order_detail, name="work-order-detail"),
    path("spk/<uuid:pk>/edit/", views.work_order_edit, name="work-order-edit"),
    path("spk/<uuid:pk>/outputs/new/", views.work_order_output_add, name="work-order-output-add"),
    path(
        "spk/<uuid:pk>/outputs/<uuid:output_pk>/edit/",
        views.work_order_output_edit,
        name="work-order-output-edit",
    ),
    path(
        "spk/<uuid:pk>/outputs/<uuid:output_pk>/remove/",
        views.work_order_output_remove,
        name="work-order-output-remove",
    ),
    path(
        "spk/<uuid:pk>/materials/new/",
        views.work_order_material_add,
        name="work-order-material-add",
    ),
    path(
        "spk/<uuid:pk>/materials/<uuid:allocation_pk>/edit/",
        views.work_order_material_edit,
        name="work-order-material-edit",
    ),
    path(
        "spk/<uuid:pk>/materials/<uuid:allocation_pk>/remove/",
        views.work_order_material_remove,
        name="work-order-material-remove",
    ),
    path("spk/<uuid:pk>/submit/", views.work_order_submit, name="work-order-submit"),
    path("spk/<uuid:pk>/approve/", views.work_order_approve, name="work-order-approve"),
    path("spk/<uuid:pk>/void/", views.work_order_void, name="work-order-void"),
    path("spk/<uuid:pk>/print/", views.work_order_print, name="work-order-print"),
    path("kirim-bahan/", views.dispatch_list, name="dispatch-list"),
    path("kirim-bahan/new/", views.dispatch_create, name="dispatch-create"),
    path("kirim-bahan/<uuid:pk>/", views.dispatch_detail, name="dispatch-detail"),
    path("kirim-bahan/<uuid:pk>/lines/new/", views.dispatch_line_add, name="dispatch-line-add"),
    path("kirim-bahan/<uuid:pk>/confirm/", views.dispatch_confirm, name="dispatch-confirm"),
    path("kirim-bahan/<uuid:pk>/cancel/", views.dispatch_cancel, name="dispatch-cancel"),
    path("terima-maklun/", views.receipt_list, name="receipt-list"),
    path("terima-maklun/new/", views.receipt_create, name="receipt-create"),
    path("terima-maklun/<uuid:pk>/", views.receipt_detail, name="receipt-detail"),
    path(
        "terima-maklun/<uuid:pk>/outputs/new/", views.receipt_output_add, name="receipt-output-add"
    ),
    path("terima-maklun/<uuid:pk>/costs/new/", views.receipt_cost_add, name="receipt-cost-add"),
    path("terima-maklun/<uuid:pk>/accept/", views.receipt_accept, name="receipt-accept"),
    path("terima-maklun/<uuid:pk>/cancel/", views.receipt_cancel, name="receipt-cancel"),
]
