from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int
import time


class AccountActivationTokenGenerator(PasswordResetTokenGenerator):
    """One-time token for email verification (expires in 24 h)."""

    def _make_hash_value(self, user, timestamp):
        return (
            str(user.pk)
            + str(timestamp)
            + str(user.is_active)
            + str(user.email_verified)
        )

    def check_token(self, user, token):
        # Limit validity to 24 hours (86400 s)
        if not (user and token):
            return False
        try:
            ts_b36, _ = token.split("-", 1)
            ts = base36_to_int(ts_b36)
        except (ValueError, AttributeError):
            return False
        if (self._num_seconds(self._now()) - ts) > 86400:
            return False
        return super().check_token(user, token)


account_activation_token = AccountActivationTokenGenerator()
password_reset_token = PasswordResetTokenGenerator()