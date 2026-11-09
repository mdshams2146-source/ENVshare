import time
from collections import defaultdict
from threading import Lock
from fastapi import HTTPException, Request, status

class InMemoryRateLimiter:
    """Thread-safe sliding-window rate limiter for sensitive endpoints."""

    def __init__(self, requests_per_minute: int = 15, window_seconds: int = 60):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self.history = defaultdict(list)
        self.lock = Lock()

    def check(self, request: Request, identifier: str = None):
        client_ip = identifier or (request.client.host if request.client else "unknown")
        endpoint = request.url.path
        key = f"{client_ip}:{endpoint}"
        now = time.monotonic()

        with self.lock:
            # Purge timestamps outside the active window
            cutoff = now - self.window_seconds
            valid_timestamps = [t for t in self.history[key] if t > cutoff]

            if len(valid_timestamps) >= self.requests_per_minute:
                retry_after = int(self.window_seconds - (now - valid_timestamps[0]))
                if retry_after <= 0:
                    retry_after = 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many authentication requests. Please wait before retrying.",
                    headers={"Retry-After": str(retry_after)}
                )

            valid_timestamps.append(now)
            self.history[key] = valid_timestamps

# Rate limiter instances for auth endpoints (10 attempts per minute)
auth_rate_limiter = InMemoryRateLimiter(requests_per_minute=10, window_seconds=60)

