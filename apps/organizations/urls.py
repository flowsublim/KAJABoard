from django.urls import path

from . import views

app_name = "organizations"

urlpatterns = [
    path("", views.workspace, name="workspace"),
    path("organization/<str:master_type>/", views.master_list, name="master-list"),
    path("organization/<str:master_type>/new/", views.master_create, name="master-create"),
    path("organization/<str:master_type>/<uuid:pk>/edit/", views.master_edit, name="master-edit"),
    path(
        "organization/<str:master_type>/<uuid:pk>/lifecycle/",
        views.master_lifecycle,
        name="master-lifecycle",
    ),
]
