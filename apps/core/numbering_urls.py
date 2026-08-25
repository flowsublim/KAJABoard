from django.urls import path

from apps.core import numbering_views

app_name = "numbering"

urlpatterns = [
    path("", numbering_views.sequence_list, name="list"),
    path("new/", numbering_views.sequence_create, name="create"),
    path("<uuid:pk>/edit/", numbering_views.sequence_edit, name="edit"),
    path("<uuid:pk>/lifecycle/", numbering_views.sequence_lifecycle, name="lifecycle"),
    path("<uuid:pk>/preview/", numbering_views.sequence_preview, name="preview"),
]
