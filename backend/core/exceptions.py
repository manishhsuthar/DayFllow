"""Project-wide DRF exception handling.

Unhandled exceptions used to surface differently depending on the view; the
registration endpoint went as far as returning a full Python traceback to
unauthenticated callers (audit V-02). Everything now funnels through here: the
detail is logged server-side with a correlation id, and the client receives only
that id.
"""

import logging
import uuid

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response

logger = logging.getLogger("django.request")


def exception_handler(exc, context):
    # Imported lazily: rest_framework.views resolves DEFAULT_AUTHENTICATION_CLASSES at
    # import time, and that chain reaches back into this module.
    from rest_framework.views import exception_handler as drf_exception_handler

    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    if isinstance(exc, Http404):
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, DjangoPermissionDenied):
        return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

    # Anything left is a genuine server-side fault.
    error_id = uuid.uuid4().hex[:12]
    view = context.get("view").__class__.__name__ if context.get("view") else "unknown"
    request = context.get("request")
    logger.exception(
        "Unhandled exception %s in %s (%s %s)",
        error_id,
        view,
        getattr(request, "method", "?"),
        getattr(request, "path", "?"),
    )
    return Response(
        {
            "detail": "An unexpected error occurred. Quote this reference when reporting it.",
            "error_id": error_id,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


class PasswordRotationRequired(exceptions.APIException):
    """Raised while an account still holds its issued temporary password."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You must change your temporary password before using the API."
    default_code = "password_rotation_required"
