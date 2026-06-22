from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect


def withdrawal_confirm_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        token = request.session.get("withdrawal_confirm_token")
        confirmed = request.session.get("withdrawal_confirmed")

        if token and confirmed is True:
            return view_func(request, *args, **kwargs)

        messages.error(request, "Request a new withdrawal confirmation to proceed")
        return redirect("dashboard")  # replace with your dashboard URL name

    return _wrapped_view
