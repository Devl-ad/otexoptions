from django.core.exceptions import PermissionDenied


def affiliate_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_affiliate:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper
