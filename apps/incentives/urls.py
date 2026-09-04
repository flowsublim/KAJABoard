"""URL configuration for Incentives and CPO operations."""

from django.urls import path

from . import views

app_name = "incentives"

urlpatterns = [
    # Incentive Rules
    path("rules/", views.rule_list, name="rule-list"),
    path("rules/new/", views.rule_create, name="rule-create"),
    path("rules/<uuid:pk>/edit/", views.rule_edit, name="rule-edit"),
    # CPO Operations & Reconciliation
    path("cpo/", views.cpo_dashboard, name="cpo-dashboard"),
    path("cpo/<uuid:pk>/", views.cpo_detail, name="cpo-detail"),
    path("cpo/accrue/<uuid:line_id>/", views.cpo_accrue_action, name="cpo-accrue"),
    path("cpo/approve/<uuid:accrual_id>/", views.cpo_approve_action, name="cpo-approve"),
    path(
        "cpo/post-payable/<uuid:accrual_id>/",
        views.cpo_post_payable_action,
        name="cpo-post-payable",
    ),
    path(
        "cpo/reverse-finance/<uuid:posting_id>/",
        views.cpo_reverse_finance_action,
        name="cpo-reverse-finance",
    ),
]
