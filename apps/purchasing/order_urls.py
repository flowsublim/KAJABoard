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
]
