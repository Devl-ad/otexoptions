import requests
from django.conf import settings


def get_account_mode(request):
    return request.session.get("account_mode", "demo")


def get_current_balance(request, wallet):
    mode = get_account_mode(request)
    return wallet.demo_balance if mode == "demo" else wallet.balance


def verify_korapay_transaction(reference):
    url = f"https://api.korapay.com/merchant/api/v1/charges/{reference}"

    headers = {
        "Authorization": f"Bearer {settings.KORAPAY_SECRET_KEY}",
    }

    response = requests.get(url, headers=headers)
    data = response.json()

    if not data.get("status"):
        return "failed"

    charge_data = data.get("data", {})

    status = charge_data.get("status", "").lower()

    if status == "success":
        return "success"

    if status in ["failed", "cancelled"]:
        return "failed"

    return "pending"
