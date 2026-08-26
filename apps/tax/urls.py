from django.urls import path

from apps.tax import views

app_name = "tax"

urlpatterns = [
    path("registrations/", views.registration_list, name="registration-list"),
    path("registrations/new/", views.registration_create, name="registration-create"),
    path("registrations/<uuid:pk>/edit/", views.registration_edit, name="registration-edit"),
    path(
        "registrations/<uuid:pk>/lifecycle/",
        views.registration_lifecycle,
        name="registration-lifecycle",
    ),
]
