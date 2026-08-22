from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
from threading import Lock


_attempts = defaultdict(deque)
_lock = Lock()

LOGIN_WINDOW = timedelta(minutes=10)
LOGIN_MAX_FAILURES = 8


def login_key(request, username=""):
    # Cloudflare normally supplies CF-Connecting-IP. Locally, fall back to
    # Flask's remote_addr. Username is included so one IP does not lock out
    # every account.
    address = (
        request.headers.get("CF-Connecting-IP")
        or request.remote_addr
        or "unknown"
    )
    return f"{address}|{(username or '').strip().lower()}"


def _trim(queue, now):
    cutoff = now - LOGIN_WINDOW
    while queue and queue[0] < cutoff:
        queue.popleft()


def login_is_limited(key):
    now = datetime.now()

    with _lock:
        queue = _attempts[key]
        _trim(queue, now)
        return len(queue) >= LOGIN_MAX_FAILURES


def record_login_failure(key):
    now = datetime.now()

    with _lock:
        queue = _attempts[key]
        _trim(queue, now)
        queue.append(now)


def clear_login_failures(key):
    with _lock:
        _attempts.pop(key, None)


def apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault(
        "Referrer-Policy",
        "strict-origin-when-cross-origin",
    )
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    return response
