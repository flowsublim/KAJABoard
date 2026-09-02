from django.urls import path

from apps.finance import views

app_name = "finance"

urlpatterns = [
    path("liquidity-accounts/", views.liquidity_account_list, name="liquidity-account-list"),
    path(
        "liquidity-accounts/new/", views.liquidity_account_create, name="liquidity-account-create"
    ),
    path(
        "liquidity-accounts/<uuid:pk>/edit/",
        views.liquidity_account_edit,
        name="liquidity-account-edit",
    ),
    path("coa/", views.account_list, name="account-list"),
    path("coa/new/", views.account_create, name="account-create"),
    path("coa/<uuid:pk>/edit/", views.account_edit, name="account-edit"),
    path("coa/<uuid:pk>/lifecycle/", views.account_lifecycle, name="account-lifecycle"),
    path("coa-mappings/", views.mapping_list, name="mapping-list"),
    path("coa-mappings/new/", views.mapping_create, name="mapping-create"),
    path("coa-mappings/<uuid:pk>/edit/", views.mapping_edit, name="mapping-edit"),
    path(
        "coa-mappings/<uuid:pk>/lifecycle/",
        views.mapping_lifecycle,
        name="mapping-lifecycle",
    ),
]
