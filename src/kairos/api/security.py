"""API-key auth and per-key token-bucket rate limiting.

In-process buckets are correct for one replica. With N replicas behind a
load balancer, move the bucket to Redis (``INCR`` + ``EXPIRE`` or a Lua
token bucket) so the limit is global – documented in scaling.md.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time

from fastapi import Header, HTTPException, Request, status


class TokenBucket:
    def __init__(self, rate_per_min: int) -> None:
        self.capacity = float(rate_per_min)
        self.refill_per_s = rate_per_min / 60.0
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, cost: float = 1.0) -> tuple[bool, float]:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._state.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill_per_s)
            if tokens >= cost:
                self._state[key] = (tokens - cost, now)
                return True, 0.0
            self._state[key] = (tokens, now)
            return False, (cost - tokens) / self.refill_per_s


def key_id(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()[:12]  # never log raw keys


def require_api_key(request: Request, x_api_key: str | None = Header(None)) -> str:
    settings = request.app.state.system.settings
    known = [*settings.api_keys, *settings.admin_api_keys, *settings.approver_api_keys]
    if not x_api_key or not any(hmac.compare_digest(x_api_key, k) for k in known):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid X-API-Key")
    kid = key_id(x_api_key)
    # Agent calls cost more than lookups: weight the bucket by route.
    cost = 5.0 if request.url.path.startswith("/v1/agent") else 1.0
    ok, retry = request.app.state.limiter.allow(kid, cost)
    if not ok:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded",
                            headers={"Retry-After": str(int(retry) + 1)})
    return kid


def require_admin_key(request: Request, x_api_key: str | None = Header(None)) -> str:
    """Admin routes (retrain, rollback). A planner key authenticates but is not authorised."""
    kid = require_api_key(request, x_api_key)
    admins = request.app.state.system.settings.admin_api_keys
    if not any(hmac.compare_digest(x_api_key or "", k) for k in admins):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin key required")
    return kid


def require_approver_key(request: Request, x_api_key: str | None = Header(None)) -> str:
    """Approve/reject purchase-order proposals. Segregation of duties: a separate key set."""
    kid = require_api_key(request, x_api_key)
    approvers = request.app.state.system.settings.approver_api_keys
    if not any(hmac.compare_digest(x_api_key or "", k) for k in approvers):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "approver key required")
    return kid
