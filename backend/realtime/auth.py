"""WebSocket authentication.

The middleware used to validate with `UntypedToken`, which by design skips the
`token_type` claim -- so a seven-day refresh token authenticated a socket exactly
like a fifteen-minute access token (audit V-12). `AccessToken` checks the claim.

The token is still accepted from the query string because browsers cannot set
headers on a WebSocket handshake, but the `Sec-WebSocket-Protocol` form is
preferred and tried first: query strings end up in access logs, proxy logs and
browser history.
"""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken

#: Subprotocol prefix carrying the credential, e.g. "dayflow.jwt.eyJhbGci...".
SUBPROTOCOL_PREFIX = "dayflow.jwt."


@database_sync_to_async
def get_user_for_token(raw_token):
    if not raw_token:
        return AnonymousUser()

    User = get_user_model()
    try:
        # AccessToken, not UntypedToken: this rejects refresh tokens.
        validated = AccessToken(raw_token)
        user_id = validated.get(api_settings.USER_ID_CLAIM)
        if user_id is None:
            return AnonymousUser()

        user = User.objects.select_related("organization").get(
            **{api_settings.USER_ID_FIELD: user_id, "is_active": True}
        )
    except (InvalidToken, TokenError, User.DoesNotExist, KeyError, ValueError):
        return AnonymousUser()

    # A pending password rotation blocks the HTTP API; it blocks realtime too.
    if getattr(user, "must_change_password", False):
        return AnonymousUser()
    return user


def _token_from_scope(scope):
    for protocol in scope.get("subprotocols") or []:
        if protocol.startswith(SUBPROTOCOL_PREFIX):
            return protocol[len(SUBPROTOCOL_PREFIX):], protocol

    query_string = scope.get("query_string", b"").decode(errors="ignore")
    return parse_qs(query_string).get("token", [""])[0], None


class QueryStringJWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        token, subprotocol = _token_from_scope(scope)
        scope["user"] = await get_user_for_token(token)
        scope["accepted_subprotocol"] = subprotocol
        return await self.app(scope, receive, send)
