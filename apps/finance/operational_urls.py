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
