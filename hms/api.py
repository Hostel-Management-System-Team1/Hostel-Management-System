"""Shared API plumbing: the error envelope and trace IDs (SAD 4.4).

Every API error is {timestamp, path, status, error, message, traceId}; it never carries a
stack trace or personal data. The same trace ID is sent back in the X-Trace-Id header so a
user's report can be matched to the server log.
"""

import uuid
from http import HTTPStatus

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class TraceIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.trace_id = uuid.uuid4().hex
        response = self.get_response(request)
        response["X-Trace-Id"] = request.trace_id
        return response


def error_body(request, status, message, details=None):
    body = {
        "timestamp": timezone.now().isoformat(),
        "path": request.path,
        "status": status,
        "error": HTTPStatus(status).phrase,
        "message": message,
        "traceId": getattr(request, "trace_id", ""),
    }
    if details:
        body["details"] = details
    return body


def error_response(request, status, message, details=None):
    return Response(error_body(request, status, message, details), status=status)


def exception_handler(exc, context):
    """DRF exception handler that returns the SAD 4.4 envelope."""
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()
    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # unexpected errors stay Django's 500, which shows no detail when DEBUG is off
    request = context["request"]
    if isinstance(exc, exceptions.ValidationError):
        details = response.data
        message = "Validation failed."
    else:
        details = None
        message = str(getattr(exc, "detail", exc))
    response.data = error_body(request, response.status_code, message, details)
    return response
