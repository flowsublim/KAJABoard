from django.urls import path

from . import views

app_name = "quality"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("inspections/", views.inspection_list, name="inspection-list"),
    path("inspections/new/", views.inspection_create, name="inspection-create"),
    path(
        "inspections/from-production/<uuid:handover_line_pk>/new/",
        views.production_inspection_create,
        name="production-inspection-create",
    ),
    path("inspections/<uuid:pk>/", views.inspection_detail, name="inspection-detail"),
    path("inspections/<uuid:pk>/post/", views.inspection_post, name="inspection-post"),
    path("inspections/<uuid:pk>/reverse/", views.inspection_reverse, name="inspection-reverse"),
    path("production-queue/", views.production_queue, name="production-queue"),
]
