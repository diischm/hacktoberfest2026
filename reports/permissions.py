"""
CSRF for anonymous POSTs.

Why this is needed: DRF wraps every APIView in `csrf_exempt`, so Django's CsrfViewMiddleware
skips API views. DRF then runs the CSRF check itself, but only inside SessionAuthentication, i.e.
only for logged-in users. Our users are anonymous, so without this nothing would check the token.

A *permission* class runs before the view's post() (and before throttling). This one runs the
same check Django's middleware would, for unsafe methods (POST, PUT, PATCH, DELETE) only.
"""

from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission


def _no_response(request):  # CSRFCheck wants a get_response callable; never called
    return None


class CsrfForUnsafeMethods(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        # CSRFCheck is Django's CsrfViewMiddleware, tweaked by DRF to return the reason as text
        # instead of rendering Django's HTML 403 page. SessionAuthentication uses it the same way.
        check = CSRFCheck(_no_response)
        check.process_request(request)  # reads the CSRF cookie
        reason = check.process_view(request, None, (), {})  # None = token OK
        if reason:
            # "CSRF" in the message -> config/exceptions.py answers 403 csrf_failed.
            raise PermissionDenied(f"CSRF Failed: {reason}")
        return True
