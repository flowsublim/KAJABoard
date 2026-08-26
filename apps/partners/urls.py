from django.urls import path

from . import views

app_name = "partners"

urlpatterns = [
    path("", views.partner_list, name="list"),
    path("new/", views.partner_create, name="create"),
    path("<uuid:pk>/edit/", views.partner_edit, name="edit"),
    path("<uuid:pk>/360/", views.partner_customer_360, name="customer-360"),
    path("<uuid:pk>/soa/", views.partner_statement_of_account, name="statement-of-account"),
    path("<uuid:pk>/lifecycle/", views.partner_lifecycle, name="lifecycle"),
    path("<uuid:pk>/roles/new/", views.partner_role_add, name="role-add"),
    path("<uuid:pk>/roles/<uuid:role_pk>/remove/", views.partner_role_remove, name="role-remove"),
]
