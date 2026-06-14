def get_account_mode(request):
    return request.session.get("account_mode", "demo")


def get_current_balance(request, wallet):
    mode = get_account_mode(request)
    return wallet.demo_balance if mode == "demo" else wallet.balance
