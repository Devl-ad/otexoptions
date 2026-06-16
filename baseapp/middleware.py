# baseapp/middleware.py
class ReferralMiddleware:
    """
    Captures ?ref=CODE from any URL and stores it in the session.
    Works silently — user never knows it's happening.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ref_code = request.GET.get("ref")
        if ref_code:
            # only store if not already referred and not logged in
            if (
                not request.session.get("ref_code")
                and not request.user.is_authenticated
            ):
                request.session["ref_code"] = ref_code
                request.session.modified = True

        return self.get_response(request)
