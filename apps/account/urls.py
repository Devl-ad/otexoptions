from django.urls import path
from . import views

app_name = "account"

urlpatterns = [
    # Auth
    path("register/", views.register, name="register"),
    path("activate/<uidb64>/<token>/", views.activate, name="activate"),
    path("login/", views.user_login, name="login"),
    path("logout/", views.user_logout, name="logout"),
    path("complete-profile/", views.complete_profile, name="complete_profile"),
    # 2FA
    path("2fa/verify/", views.totp_verify, name="totp_verify"),
    path("2fa/setup/", views.totp_setup, name="totp_setup"),
    path("2fa/disable/", views.totp_disable, name="totp_disable"),
    # Password reset
    path(
        "password/reset/", views.password_reset_request, name="password_reset_request"
    ),
    path(
        "password/reset/<uidb64>/<token>/",
        views.password_reset_confirm,
        name="passwordconfirm",
    ),
]
