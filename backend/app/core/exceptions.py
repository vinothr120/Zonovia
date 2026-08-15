from typing import Any


class AppError(Exception):
    status_code: int = 400
    error_code: str = "APP_ERROR"

    def __init__(self, message: str, *, field_errors: dict[str, Any] | None = None) -> None:
        self.message = message
        self.field_errors = field_errors
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"


class ValidationAppError(AppError):
    status_code = 422
    error_code = "VALIDATION_ERROR"


class ConflictError(AppError):
    status_code = 409
    error_code = "CONFLICT"


class UnauthorizedError(AppError):
    status_code = 401
    error_code = "UNAUTHORIZED"


class PermissionDeniedError(AppError):
    status_code = 403
    error_code = "PERMISSION_DENIED"


class AccountLockedError(AppError):
    status_code = 423
    error_code = "ACCOUNT_LOCKED"


class RateLimitedError(AppError):
    status_code = 429
    error_code = "RATE_LIMITED"
