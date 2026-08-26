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
]
