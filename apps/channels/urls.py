from django.urls import path

from apps.channels import views

app_name = "channels"

urlpatterns = [
    path("stores/", views.store_list, name="store-list"),
    path("stores/new/", views.store_create, name="store-create"),
    path("stores/<uuid:pk>/edit/", views.store_edit, name="store-edit"),
    path(
        "stores/<uuid:pk>/lifecycle/",
        views.lifecycle,
        {"master_type": "stores"},
        name="store-lifecycle",
    ),
    path("sku-mappings/", views.mapping_list, name="mapping-list"),
    path("sku-mappings/new/", views.mapping_create, name="mapping-create"),
    path("sku-mappings/<uuid:pk>/edit/", views.mapping_edit, name="mapping-edit"),
    path(
        "sku-mappings/<uuid:pk>/lifecycle/",
        views.lifecycle,
        {"master_type": "mappings"},
        name="mapping-lifecycle",
    ),
]
