from django.urls import path

from apps.sales import views

app_name = "sales"

urlpatterns = [
    path("", views.order_list, name="order-list"),
    path("new/", views.order_create, name="order-create"),
    path("<uuid:pk>/", views.order_detail, name="order-detail"),
    path("<uuid:pk>/edit/", views.order_edit, name="order-edit"),
    path("<uuid:pk>/lines/new/", views.line_add, name="line-add"),
    path("<uuid:pk>/lines/<uuid:line_pk>/edit/", views.line_edit, name="line-edit"),
    path("<uuid:pk>/lines/<uuid:line_pk>/remove/", views.line_remove, name="line-remove"),
    path("<uuid:pk>/confirm/", views.order_confirm, name="order-confirm"),
    path("<uuid:pk>/cancel/", views.order_cancel, name="order-cancel"),
    path("<uuid:pk>/hold-release/", views.order_hold_release, name="order-hold-release"),
    path("<uuid:pk>/credit-override/", views.order_credit_override, name="order-credit-override"),
    path("deliveries/", views.delivery_list, name="delivery-list"),
    path("deliveries/new/", views.delivery_create, name="delivery-create"),
    path("deliveries/<uuid:pk>/", views.delivery_detail, name="delivery-detail"),
    path("deliveries/<uuid:pk>/edit/", views.delivery_edit, name="delivery-edit"),
    path("deliveries/<uuid:pk>/lines/new/", views.delivery_line_add, name="delivery-line-add"),
    path(
        "deliveries/<uuid:pk>/lines/<uuid:line_pk>/edit/",
        views.delivery_line_edit,
        name="delivery-line-edit",
    ),
    path(
        "deliveries/<uuid:pk>/lines/<uuid:line_pk>/remove/",
        views.delivery_line_remove,
        name="delivery-line-remove",
    ),
    path("deliveries/<uuid:pk>/post/", views.delivery_post, name="delivery-post"),
    path("deliveries/<uuid:pk>/cancel/", views.delivery_cancel, name="delivery-cancel"),
    path("deliveries/<uuid:pk>/print/", views.delivery_print, name="delivery-print"),
    path("invoices/", views.invoice_list, name="invoice-list"),
    path("invoices/new/", views.invoice_create_delivery, name="invoice-create-delivery"),
    path(
        "invoices/new/sales-order/",
        views.invoice_create_sales_order,
        name="invoice-create-sales-order",
    ),
    path("proformas/new/", views.proforma_create, name="proforma-create"),
    path("invoices/<uuid:pk>/", views.invoice_detail, name="invoice-detail"),
    path("invoices/<uuid:pk>/edit/", views.invoice_edit, name="invoice-edit"),
    path("invoices/<uuid:pk>/lines/new/", views.invoice_line_add, name="invoice-line-add"),
    path(
        "invoices/<uuid:pk>/lines/<uuid:line_pk>/edit/",
        views.invoice_line_edit,
        name="invoice-line-edit",
    ),
    path(
        "invoices/<uuid:pk>/lines/<uuid:line_pk>/remove/",
        views.invoice_line_remove,
        name="invoice-line-remove",
    ),
    path("invoices/<uuid:pk>/confirm/", views.invoice_confirm, name="invoice-confirm"),
    path("invoices/<uuid:pk>/cancel/", views.invoice_cancel, name="invoice-cancel"),
    path("invoices/<uuid:pk>/print/", views.invoice_print, name="invoice-print"),
]
