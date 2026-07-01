from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("trade/", views.trade_page, name="trade"),
    path("trade/place/", views.place_trade, name="place_trade"),
    path("trade/status/<int:trade_id>/", views.trade_status, name="trade_status"),
    path("account/switch/", views.switch_account_mode, name="switch_account_mode"),
    path("agents/", views.deposit_page, name="deposit"),
    path(
        "deposit-funds/crypto/",
        views.deposit_withcrypto_page,
        name="deposit_withcrypto_page",
    ),
    path("kyc/", views.kyc_page, name="kyc_verify"),
    path("transaction-logs/", views.transactions_logs, name="transactions_logs"),
    path("trade-history/", views.trade_logs, name="trade_logs"),
    path("withdraw-funds/", views.withdrawal, name="withdrawal"),
    path("profile/", views.settings, name="settings"),
    path("notifications/", views.notification_page, name="notification_page"),
    path("agent-panel/", views.agent_dashboard, name="dashboard_agent"),
    path("agent/lookup-user/", views.lookup_user, name="lookup_user"),
    path("agent/credit-user/", views.credit_user, name="credit_user"),
    path("faq/", views.faq, name="faq"),
    path("bank-deposit/", views.bank_deposit, name="bank_depoosit"),
    path(
        "payment/flutterwave/callback/",
        views.flutterwave_callback,
        name="flutterwave_callback",
    ),
    path("payment/status/", views.payment_status, name="payment_status"),
    path("withdrawal/agents/", views.agent_withdrawal, name="agent_withdrawal"),
    path("activate-withdrawal/", views.initiate_withdrawal, name="initate_withdrawal"),
    path("withdraw/confirm/", views.confirm_withdrawal, name="confirm_withdrawal"),
    path(
        "agent/withdrawal-requests/",
        views.agent_withdrawal_requests,
        name="agent_withdrawal_requests",
    ),
]
