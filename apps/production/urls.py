from django.urls import path

from . import views

app_name = "production"

urlpatterns = [
    path("", views.wip_list, name="wip-list"),
    path("<uuid:pk>/", views.wip_detail, name="wip-detail"),
    path("new/", views.work_create, name="work-create"),
    path("<uuid:pk>/edit/", views.work_edit, name="work-edit"),
    path("<uuid:pk>/line/new/", views.work_line_add, name="work-line-add"),
    path("<uuid:pk>/post/", views.work_post, name="work-post"),
    path("line/<uuid:pk>/reverse/", views.work_line_reverse, name="work-line-reverse"),
    path("reject/new/", views.reject_create, name="reject-create"),
    path("reject/<uuid:pk>/", views.reject_detail, name="reject-detail"),
    path("reject/<uuid:pk>/line/new/", views.reject_line_add, name="reject-line-add"),
    path("reject/<uuid:pk>/post/", views.reject_post, name="reject-post"),
    path("reject-line/<uuid:pk>/reverse/", views.reject_line_reverse, name="reject-line-reverse"),
]
