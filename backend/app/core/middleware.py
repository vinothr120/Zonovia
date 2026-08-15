from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.config import settings


def install_security_headers(app: FastAPI) -> None:
    """Standard defensive headers a browser client can act on — none of these are a
    substitute for the actual authz checks elsewhere, they just close off classes of
    attack (clickjacking, MIME-sniffing, protocol downgrade) that don't otherwise show up
    in an API's own test suite."""

    @app.middleware("http")
    async def _add_security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.is_production:
            # Only meaningful once the app is actually served over HTTPS — asserting it in
            # dev over plain http would be misleading.
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
