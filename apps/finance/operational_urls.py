from django.urls import path

from apps.finance import views

app_name = "finance_operations"

urlpatterns = [
    path("journals/", views.journal_list, name="journal-list"),
    path("journals/<uuid:pk>/", views.journal_detail, name="journal-detail"),
    path("general-ledger/", views.general_ledger_list, name="general-ledger"),
    path("accounts-receivable/", views.receivable_list, name="receivable-list"),
    path("accounts-payable/", views.payable_list, name="payable-list"),
    path("reconciliation/", views.finance_reconciliation, name="reconciliation"),
]
