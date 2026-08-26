from django.urls import path

from apps.projects import views

app_name = "projects"
urlpatterns = [
    path("", views.project_list, name="list"),
    path("new/", views.project_create, name="create"),
    path("<uuid:pk>/", views.project_detail_view, name="detail"),
    path("<uuid:pk>/edit/", views.project_edit, name="edit"),
    path("<uuid:pk>/budget/new/", views.budget_add, name="budget-add"),
    path("<uuid:pk>/sales-orders/link/", views.sales_order_link, name="sales-order-link"),
    path("<uuid:pk>/<str:action>/", views.project_transition, name="transition"),
]
