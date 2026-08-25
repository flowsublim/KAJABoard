from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("<str:master_type>/", views.catalog_list, name="list"),
    path("<str:master_type>/new/", views.catalog_create, name="create"),
    path("<str:master_type>/<uuid:pk>/edit/", views.catalog_edit, name="edit"),
    path(
        "<str:master_type>/<uuid:pk>/lifecycle/",
        views.catalog_lifecycle,
        name="lifecycle",
    ),
]
