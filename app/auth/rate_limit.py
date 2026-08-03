from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from app.auth.errors import AuthenticationError


class AuthRateLimiter:
    """Small process-local limiter for focused auth abuse protection."""

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = monotonic()
        cutoff = now - window_seconds
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= limit:
                raise AuthenticationError(
                    "rate_limited",
                    "Too many authentication attempts. Please try again later.",
                    status_code=429,
                )
            attempts.append(now)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()


auth_rate_limiter = AuthRateLimiter()
