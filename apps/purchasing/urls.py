from django.urls import path

from apps.purchasing import views

app_name = "purchasing"

urlpatterns = [
    path("purchase-categories/", views.category_list, name="category-list"),
    path("purchase-categories/new/", views.category_create, name="category-create"),
    path("purchase-categories/<uuid:pk>/edit/", views.category_edit, name="category-edit"),
    path(
        "purchase-categories/<uuid:pk>/lifecycle/",
        views.category_lifecycle,
        name="category-lifecycle",
    ),
]
