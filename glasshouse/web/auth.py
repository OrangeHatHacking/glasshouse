"""
mTLS enforcement middleware.

Uvicorn handles TLS termination with ssl_certfile/ssl_keyfile. For mutual TLS,
we set ssl_ca_certs and ssl_cert_reqs=ssl.CERT_REQUIRED in the Uvicorn config.
this means the TLS handshake itself rejects clients without a valid cert.

This middleware is a secondary defence: it verifies the client cert is present
in the ASGI scope (populated by Uvicorn after successful TLS handshake) and
rejects anything that slipped through without one.

In practice, if Uvicorn is correctly configured with CERT_REQUIRED, this
middleware should never see an uncertified request, but it checks anyway.
"""

import logging
import hmac
import secrets
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger(__name__)
CSRF_TOKEN = secrets.token_urlsafe(32)


def verify_csrf(token: str) -> None:
    if not hmac.compare_digest(token, CSRF_TOKEN):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Invalid CSRF token")


class MTLSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Uvicorn populates 'ssl' scope key with the client cert when mTLS is
        # enforced at the transport layer. If it's absent, drop the connection.
        ssl_scope = request.scope.get("ssl")
        if ssl_scope is None:
            log.warning(
                "Request without TLS scope from %s - dropping",
                request.client.host if request.client else "unknown",
            )
            # Return an empty 400 response.
            return Response(status_code=400)

        return await call_next(request)
