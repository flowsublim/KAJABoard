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
]
