"""Domain exceptions shared by all apps.

Each carries a stable error code and HTTP status; config/exception_handler.py turns them
into API responses, so services never build HTTP responses themselves.
"""

from typing import Any


class DomainError(Exception):
    code = "DOMAIN_ERROR"
    http_status = 400
    default_message = "The request could not be processed."

    def __init__(self, message: str | None = None, details: Any = None) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)


class NotFoundError(DomainError):
    code = "NOT_FOUND"
    http_status = 404
    default_message = "The requested resource was not found."


class ConflictError(DomainError):
    code = "CONFLICT"
    http_status = 409
    default_message = "The request conflicts with the current state of the resource."


class ServiceUnavailableError(DomainError):
    code = "SERVICE_UNAVAILABLE"
    http_status = 503
    default_message = "A backing service is unavailable. Please retry shortly."
