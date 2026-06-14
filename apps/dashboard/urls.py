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
]
