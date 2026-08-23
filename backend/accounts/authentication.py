"""Authentication classes.

`must_change_password` used to be advisory: login returned the flag and then
issued a fully privileged token anyway, with enforcement living only in a
frontend redirect that calling the API directly bypassed (audit V-15).

Enforcing it here rather than in a permission class is deliberate. DRF replaces
DEFAULT_PERMISSION_CLASSES wholesale for any view that declares its own
`permission_classes`, and nearly every view in this project does -- so a default
permission would silently not apply. Authentication always runs.
"""

from django.urls import resolve
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.exceptions import PasswordRotationRequired

#: URL names reachable while a password rotation is outstanding.
ROTATION_EXEMPT_URL_NAMES = frozenset(
    {
        "change_password",
        "logout",
        "token_refresh",
        "current_user",
    }
)


class DayFlowJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, token = result
        if getattr(user, "must_change_password", False) and not self._is_exempt(request):
            raise PasswordRotationRequired()
        return user, token

    @staticmethod
    def _is_exempt(request) -> bool:
        if request.method == "OPTIONS":
            return True
        try:
            return resolve(request.path_info).url_name in ROTATION_EXEMPT_URL_NAMES
        except Exception:
            return False
