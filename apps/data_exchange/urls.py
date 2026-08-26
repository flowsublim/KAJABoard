from django.urls import path

from apps.data_exchange import views

app_name = "data_exchange"

urlpatterns = [
    path("imports/", views.import_list, name="import-list"),
    path("imports/coa/upload/", views.coa_import_upload, name="coa-import-upload"),
    path("imports/coa/template/", views.coa_template_download, name="coa-template"),
    path("imports/<uuid:pk>/", views.import_detail, name="import-detail"),
    path("imports/<uuid:pk>/confirm/", views.import_confirm, name="import-confirm"),
]
