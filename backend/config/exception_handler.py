"""Single place that maps exceptions to the API error shape:

{"error": {"code": "...", "message": "...", "details": {...}}}
"""

import logging
from typing import Any

from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.core.exceptions import DomainError

logger = logging.getLogger(__name__)


def error_response(code: str, message: str, status: int, details: Any = None) -> Response:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return Response({"error": error}, status=status)


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    if isinstance(exc, DomainError):
        return error_response(exc.code, exc.message, exc.http_status, exc.details)

    if isinstance(exc, exceptions.ValidationError):
        return error_response(
            "VALIDATION_ERROR", "The request contains invalid fields.", 400, exc.detail
        )

    response = drf_exception_handler(exc, context)
    if response is not None:
        if isinstance(exc, Http404):
            return error_response("NOT_FOUND", "The requested resource was not found.", 404)
        code = getattr(exc, "default_code", "error").upper()
        message = str(getattr(exc, "detail", "")) or "The request failed."
        return error_response(code, message, response.status_code)

    logger.exception("Unhandled API error", exc_info=exc)
    return error_response("INTERNAL_ERROR", "An unexpected error occurred.", 500)
