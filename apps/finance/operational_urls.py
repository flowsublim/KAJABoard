# ruff: noqa: E501
from django.urls import path

from apps.finance import views

app_name = "finance_operations"

urlpatterns = [
    path("fixed-assets/", views.fixed_asset_list, name="fixed-asset-list"),
    path("fixed-assets/<uuid:pk>/", views.fixed_asset_detail_view, name="fixed-asset-detail"),
    path("depreciation/", views.depreciation_list, name="depreciation-list"),
    path("depreciation/<uuid:pk>/", views.depreciation_detail_view, name="depreciation-detail"),
    path(
        "depreciation/<uuid:pk>/<str:action>/",
        views.depreciation_action,
        name="depreciation-action",
    ),
    path("wage-payables/", views.wage_payable_list, name="wage-payable-list"),
    path("wage-payables/<uuid:pk>/", views.wage_payable_detail_view, name="wage-payable-detail"),
    path(
        "wage-payables/<uuid:pk>/reverse/", views.wage_payable_reverse, name="wage-payable-reverse"
    ),
    path("accounting-periods/", views.accounting_period_list, name="accounting-period-list"),
    path(
        "accounting-periods/<uuid:pk>/",
        views.accounting_period_detail_view,
        name="accounting-period-detail",
    ),
    path(
        "accounting-periods/<uuid:pk>/close/",
        views.accounting_period_close,
        name="accounting-period-close",
    ),
    path(
        "accounting-periods/new/", views.accounting_period_create, name="accounting-period-create"
    ),
    path("bank-reconciliation/", views.bank_reconciliation_list, name="bank-reconciliation-list"),
    path("bank-reconciliation/new/", views.bank_statement_create, name="bank-statement-create"),
    path(
        "bank-reconciliation/<uuid:pk>/", views.bank_statement_detail, name="bank-statement-detail"
    ),
    path(
        "bank-reconciliation/<uuid:pk>/lines/new/",
        views.bank_statement_line_add,
        name="bank-statement-line-add",
    ),
    path("bank-reconciliation/lines/<uuid:pk>/match/", views.bank_match, name="bank-match"),
    path("bank-reconciliation/matches/<uuid:pk>/unmatch/", views.bank_unmatch, name="bank-unmatch"),
    path("journals/", views.journal_list, name="journal-list"),
    path("journals/<uuid:pk>/", views.journal_detail, name="journal-detail"),
    path("general-ledger/", views.general_ledger_list, name="general-ledger"),
    path("accounts-receivable/", views.receivable_list, name="receivable-list"),
    path("accounts-payable/", views.payable_list, name="payable-list"),
    path("reconciliation/", views.finance_reconciliation, name="reconciliation"),
    path("payments/", views.payment_list, name="payment-list"),
    path(
        "payments/customer-receipt/", views.customer_receipt_create, name="customer-receipt-create"
    ),
    path("payments/vendor-payment/", views.vendor_payment_create, name="vendor-payment-create"),
    path("payments/<uuid:pk>/", views.payment_detail, name="payment-detail"),
    path("payments/<uuid:pk>/reverse/", views.payment_reverse, name="payment-reverse"),
    path("cash/", views.cash_list, name="cash-list"),
    path("bank/", views.bank_list, name="bank-list"),
    path(
        "marketplace/settlements/",
        views.marketplace_settlement_list,
        name="marketplace-settlement-list",
    ),
    path(
        "marketplace/settlements/post/",
        views.marketplace_settlement_post,
        name="marketplace-settlement-post",
    ),
    path(
        "marketplace/settlements/<uuid:pk>/reverse/",
        views.marketplace_settlement_reverse,
        name="marketplace-settlement-reverse",
    ),
    path("marketplace/balance/", views.marketplace_balance_list, name="marketplace-balance-list"),
    path("marketplace/payouts/", views.marketplace_payout_list, name="marketplace-payout-list"),
    path(
        "marketplace/payouts/post/", views.marketplace_payout_post, name="marketplace-payout-post"
    ),
    path(
        "marketplace/payouts/<uuid:pk>/reverse/",
        views.marketplace_payout_reverse,
        name="marketplace-payout-reverse",
    ),
]
