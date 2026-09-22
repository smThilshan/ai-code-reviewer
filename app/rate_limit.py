"""Per-client rate limiting, so one caller can't drain the OpenAI budget.

Every /review request costs real money, so an unauthenticated public endpoint
needs a ceiling on how fast any one caller can spend it. This is a coarse,
cheap defense (per IP), not a substitute for authentication and per-user
quotas, which are the real answer once the app has users.

Known limits of this setup, worth knowing before deploying:
- Counters live in this process's memory. They reset on restart, and with N
  worker processes the effective limit is N times higher. Sharing them needs
  a backing store such as Redis (`Limiter(storage_uri="redis://...")`).
- The key is the connecting IP. Behind a reverse proxy or platform router,
  that is the proxy's IP, so all users would share one bucket. Run uvicorn
  with `--proxy-headers --forwarded-allow-ips=<your proxy's IP>` so the real
  client IP is used. Don't trust X-Forwarded-For from arbitrary sources, or a
  caller can spoof a new IP on every request and bypass the limit entirely.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# headers_enabled adds X-RateLimit-Limit/Remaining/Reset and, on a 429,
# Retry-After to every rate-limited response. Without it a client (our own
# Phase 8 frontend, or anyone else) can only learn it was throttled from the
# message text; with it, it can show "try again in N seconds" or back off
# automatically instead of guessing or polling.
limiter = Limiter(key_func=get_remote_address, headers_enabled=True)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return 429 in the same {"detail": ...} shape as the API's other errors.

    slowapi's own default handler returns {"error": ...} instead, which would
    be the one inconsistent error shape in the API, so we replace it with
    this one but still delegate to its `_inject_headers` for the
    Retry-After/X-RateLimit-* headers rather than re-deriving them.
    """
    response = JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}. Try again later."},
    )
    return request.app.state.limiter._inject_headers(  # noqa: SLF001 - slowapi's own handler does the same
        response, request.state.view_rate_limit
    )
