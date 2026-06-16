# apps/accounts/referrals.py
from decimal import Decimal
from django.utils import timezone
import logging

from .models import ReferralDeposit

logger = logging.getLogger(__name__)


def record_referral_deposit(user, amount):
    """
    Call this whenever a referred user makes a deposit.
    Automatically calculates commission and updates referrer earnings.

    Usage:
        from apps.accounts.referrals import record_referral_deposit
        record_referral_deposit(request.user, deposit_amount)
    """
    try:
        # check if this user was referred by someone
        referral = user.referral_record  # OneToOne reverse
    except Exception:
        return  # user was not referred — do nothing

    amount = Decimal(str(amount))
    commission = round(amount * (referral.commission_rate / 100), 2)

    # update referral record
    referral.total_deposited += amount
    referral.total_commission += commission
    referral.last_deposit_at = timezone.now()
    referral.status = "ACTIVE"

    if not referral.first_deposit_at:
        referral.first_deposit_at = timezone.now()

    referral.save(
        update_fields=[
            "total_deposited",
            "total_commission",
            "last_deposit_at",
            "first_deposit_at",
            "status",
        ]
    )

    # log individual deposit
    ReferralDeposit.objects.create(
        referral=referral,
        amount=amount,
        commission_earned=commission,
    )

    # credit commission to referrer's wallet
    try:
        from apps.dashboard.models import Wallet

        referrer_wallet = Wallet.objects.get(user=referral.referrer)
        referrer_wallet.credit(float(commission), mode="live")
        logger.info(
            f"Referral commission: {referral.referrer.username} "
            f"earned ${commission} from {user.username} deposit of ${amount}"
        )
    except Exception as e:
        logger.error(f"Failed to credit referral commission: {e}")
