from .models import Wallet


def account(request):
    if not request.user.is_authenticated:
        return {}

    try:
        wallet = request.user.wallet
        mode = request.session.get("account_mode", "demo")

        balance = wallet.demo_balance if mode == "demo" else wallet.balance

        return {
            "balance": balance,
            "demo_balance": wallet.demo_balance,
            "live_balance": wallet.balance,
            "account_mode": mode,
            "is_demo": mode == "demo",
            "is_live": mode == "live",
        }

    except Wallet.DoesNotExist:
        return {
            "balance": 0,
            "demo_balance": 0,
            "live_balance": 0,
            "account_mode": "demo",
            "is_demo": True,
            "is_live": False,
        }
