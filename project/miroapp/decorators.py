from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def role_required(allowed_roles):
    """
    Usage:
    @role_required(['Processor', 'Checker'])
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):

            user = request.user

            # Not logged in
            if not user.is_authenticated:
                return redirect('login')

            

            # Role-based check
            if user.role in allowed_roles:
                return view_func(request, *args, **kwargs)

            return HttpResponseForbidden("You are not authorized to access this resource.")

        return wrapper
    return decorator
