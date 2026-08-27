from django.urls import path

from . import views

app_name = "production"

urlpatterns = [
    path("", views.wip_list, name="wip-list"),
    path("tariffs/", views.tariff_list, name="tariff-list"),
    path("tariffs/new/", views.tariff_create, name="tariff-create"),
    path("tariffs/<uuid:pk>/edit/", views.tariff_edit, name="tariff-edit"),
    path("extra-costs/", views.extra_cost_list, name="extra-cost-list"),
    path("extra-costs/new/", views.extra_cost_create, name="extra-cost-create"),
    path("extra-costs/<uuid:pk>/", views.extra_cost_detail, name="extra-cost-detail"),
    path("extra-costs/<uuid:pk>/edit/", views.extra_cost_edit, name="extra-cost-edit"),
    path("extra-costs/<uuid:pk>/post/", views.extra_cost_post, name="extra-cost-post"),
    path("extra-costs/<uuid:pk>/reverse/", views.extra_cost_reverse, name="extra-cost-reverse"),
    path("costs/", views.cost_list, name="cost-list"),
    path("costs/<uuid:pk>/", views.cost_detail, name="cost-detail"),
    path("costs/<uuid:output_pk>/build/", views.cost_build, name="cost-build"),
    path("handover/", views.handover_list, name="handover-list"),
    path("handover/new/", views.handover_create, name="handover-create"),
    path("handover/<uuid:pk>/", views.handover_detail, name="handover-detail"),
    path("handover/<uuid:pk>/print/", views.handover_print, name="handover-print"),
    path("handover/<uuid:pk>/edit/", views.handover_edit, name="handover-edit"),
    path("handover/<uuid:pk>/line/new/", views.handover_line_add, name="handover-line-add"),
    path("handover-line/<uuid:pk>/edit/", views.handover_line_edit, name="handover-line-edit"),
    path(
        "handover-line/<uuid:pk>/remove/", views.handover_line_remove, name="handover-line-remove"
    ),
    path("handover/<uuid:pk>/ready/", views.handover_ready, name="handover-ready"),
    path(
        "handover-line/<uuid:pk>/reverse/",
        views.handover_line_reverse,
        name="handover-line-reverse",
    ),
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
