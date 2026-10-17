"""
Turns every API error into the contract's shape:

    {"error": {"code": "...", "message": "...", "fields": {...}}}

DRF calls `api_exception_handler` (set as EXCEPTION_HANDLER in settings) whenever a view raises.
The frontend branches on `code`, so codes come from docs/plan/API_CONTRACT.md#error-format.
"""

import logging
import math

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class InvalidBBox(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "bbox must be minLng,minLat,maxLng,maxLat."
    default_code = "invalid_bbox"


class PhotoTooLarge(exceptions.APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "The photo is too large (max 10 MB)."
    default_code = "photo_too_large"


class UnsupportedPhotoType(exceptions.APIException):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_detail = "Please upload a JPEG, PNG or WebP photo."
    default_code = "unsupported_photo_type"


# Gemini didn't say how long to wait (and for our own upload throttle, as a fallback).
DEFAULT_RETRY_AFTER_SECONDS = 60


class AiRateLimitedError(exceptions.APIException):
    """Gemini quota hit: 429 ai_rate_limited, the report is NOT created."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "The photo analyzer is busy. Please try again in a minute."
    default_code = "ai_rate_limited"

    def __init__(self, retry_after_seconds=None):
        super().__init__()
        self.retry_after_seconds = retry_after_seconds or DEFAULT_RETRY_AFTER_SECONDS


def error_response(http_status, code, message, fields=None, headers=None, extra=None):
    body = {"error": {"code": code, "message": message, "fields": fields or {}, **(extra or {})}}
    return Response(body, status=http_status, headers=headers)


def _rate_limited_response(message, retry_after_seconds):
    seconds = max(1, math.ceil(retry_after_seconds))
    return error_response(
        429,
        "ai_rate_limited",
        message,
        headers={"Retry-After": str(seconds)},
        extra={"retry_after_seconds": seconds},
    )


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
    if isinstance(exc, AiRateLimitedError):
        return _rate_limited_response(str(exc.detail), exc.retry_after_seconds)
    if isinstance(exc, exceptions.Throttled):
        # Our own upload limit. The contract has no separate code for it; ai_rate_limited is the
        # closest (same meaning for the user: "not saved, try again in N seconds").
        return _rate_limited_response(
            "Too many uploads from this device. Please try again in a minute.",
            exc.wait or DEFAULT_RETRY_AFTER_SECONDS,
        )
    if isinstance(exc, exceptions.APIException):
        # Not in the contract table (e.g. throttling); keep DRF's status and code.
        code = exc.get_codes() if isinstance(exc.detail, str) else exc.default_code
        return error_response(exc.status_code, code, _first_message(exc.detail))

    # Anything else is a bug: log the traceback on the server, tell the client nothing about it.
    logger.exception("Unhandled API error", exc_info=exc)
    return error_response(500, "server_error", "Something went wrong on our side.")
