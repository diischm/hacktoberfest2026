"""
Turns every API error into the contract's shape:

    {"error": {"code": "...", "message": "...", "fields": {...}}}

DRF calls `api_exception_handler` (set as EXCEPTION_HANDLER in settings) whenever a view raises.
The frontend branches on `code`, so codes come from docs/plan/API_CONTRACT.md#error-format.
"""

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class InvalidBBox(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "bbox must be minLng,minLat,maxLng,maxLat."
    default_code = "invalid_bbox"


def error_response(http_status, code, message, fields=None, headers=None):
    body = {"error": {"code": code, "message": message, "fields": fields or {}}}
    return Response(body, status=http_status, headers=headers)


def _field_errors(detail):
    """DRF's {"lat": [ErrorDetail(...)]} -> plain {"lat": ["..."]}."""
    if not isinstance(detail, dict):
        return {}
    return {
        str(name): [str(m) for m in msgs] if isinstance(msgs, list) else [str(msgs)]
        for name, msgs in detail.items()
    }


def _first_message(detail):
    if isinstance(detail, dict):
        detail = next(iter(detail.values()), "")
    if isinstance(detail, list):
        detail = detail[0] if detail else ""
    return str(detail)


def api_exception_handler(exc, context):
    # Django's own exceptions -> DRF's, same as DRF's default handler does.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    if isinstance(exc, InvalidBBox):
        return error_response(400, "invalid_bbox", str(exc.detail), {"bbox": [str(exc.detail)]})
    if isinstance(exc, (exceptions.ValidationError, exceptions.ParseError)):
        message = "Invalid request." if isinstance(exc.detail, dict) else _first_message(exc.detail)
        return error_response(400, "validation_error", message, _field_errors(exc.detail))
    if isinstance(exc, exceptions.NotFound):
        return error_response(404, "not_found", "Not found.")
    if isinstance(exc, exceptions.MethodNotAllowed):
        return error_response(405, "method_not_allowed", str(exc.detail))
    if isinstance(exc, exceptions.PermissionDenied) and "CSRF" in str(exc.detail):
        return error_response(403, "csrf_failed", "Please reload the page and try again.")
    if isinstance(exc, exceptions.APIException):
        # Not in the contract table (e.g. throttling); keep DRF's status and code.
        code = exc.get_codes() if isinstance(exc.detail, str) else exc.default_code
        return error_response(exc.status_code, code, _first_message(exc.detail))

    # Anything else is a bug: log the traceback on the server, tell the client nothing about it.
    logger.exception("Unhandled API error", exc_info=exc)
    return error_response(500, "server_error", "Something went wrong on our side.")
