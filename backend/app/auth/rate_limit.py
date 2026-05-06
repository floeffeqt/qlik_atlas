from __future__ import annotations

import os
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name, str(default)) or str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


def normalize_login_email(email: str) -> str:
    return (email or "").strip().lower()


@dataclass(frozen=True)
class RateLimitStatus:
    blocked: bool
    retry_after_seconds: int
    scope: str | None = None


class LoginRateLimiter:
    def __init__(
        self,
        *,
        ip_limit: int,
        email_limit: int,
        window_seconds: int,
        lockout_seconds: int,
    ) -> None:
        self.ip_limit = max(1, ip_limit)
        self.email_limit = max(1, email_limit)
        self.window_seconds = max(1, window_seconds)
        self.lockout_seconds = max(1, lockout_seconds)
        self._lock = Lock()
        self._attempts: dict[str, dict[str, deque[datetime]]] = {
            "ip": defaultdict(deque),
            "email": defaultdict(deque),
        }
        self._blocked_until: dict[str, dict[str, datetime]] = {
            "ip": {},
            "email": {},
        }

    def reset(self) -> None:
        with self._lock:
            self._attempts = {"ip": defaultdict(deque), "email": defaultdict(deque)}
            self._blocked_until = {"ip": {}, "email": {}}

    def check(self, ip_address: str, email: str, now: datetime | None = None) -> RateLimitStatus:
        current = now or datetime.now(timezone.utc)
        email_key = normalize_login_email(email)
        with self._lock:
            ip_status = self._bucket_status("ip", ip_address, current)
            if ip_status.blocked:
                return ip_status
            if email_key:
                return self._bucket_status("email", email_key, current)
            return RateLimitStatus(blocked=False, retry_after_seconds=0)

    def register_failure(self, ip_address: str, email: str, now: datetime | None = None) -> RateLimitStatus:
        current = now or datetime.now(timezone.utc)
        email_key = normalize_login_email(email)
        with self._lock:
            statuses = [self._record_bucket_failure("ip", ip_address, current)]
            if email_key:
                statuses.append(self._record_bucket_failure("email", email_key, current))
            blocked = [item for item in statuses if item.blocked]
            if not blocked:
                return RateLimitStatus(blocked=False, retry_after_seconds=0)
            blocked.sort(key=lambda item: item.retry_after_seconds, reverse=True)
            return blocked[0]

    def register_success(self, ip_address: str, email: str) -> None:
        email_key = normalize_login_email(email)
        with self._lock:
            self._clear_bucket("ip", ip_address)
            if email_key:
                self._clear_bucket("email", email_key)

    def _bucket_status(self, scope: str, key: str, now: datetime) -> RateLimitStatus:
        self._prune_bucket(scope, key, now)
        blocked_until = self._blocked_until[scope].get(key)
        if blocked_until is None or blocked_until <= now:
            self._blocked_until[scope].pop(key, None)
            return RateLimitStatus(blocked=False, retry_after_seconds=0)
        retry_after = max(1, int((blocked_until - now).total_seconds()))
        return RateLimitStatus(blocked=True, retry_after_seconds=retry_after, scope=scope)

    def _record_bucket_failure(self, scope: str, key: str, now: datetime) -> RateLimitStatus:
        self._prune_bucket(scope, key, now)
        attempts = self._attempts[scope][key]
        attempts.append(now)
        limit = self.ip_limit if scope == "ip" else self.email_limit
        if len(attempts) < limit:
            return RateLimitStatus(blocked=False, retry_after_seconds=0, scope=scope)
        blocked_until = now + timedelta(seconds=self.lockout_seconds)
        self._blocked_until[scope][key] = blocked_until
        return RateLimitStatus(
            blocked=True,
            retry_after_seconds=self.lockout_seconds,
            scope=scope,
        )

    def _clear_bucket(self, scope: str, key: str) -> None:
        self._attempts[scope].pop(key, None)
        self._blocked_until[scope].pop(key, None)

    def _prune_bucket(self, scope: str, key: str, now: datetime) -> None:
        cutoff = now - timedelta(seconds=self.window_seconds)
        attempts = self._attempts[scope].get(key)
        if attempts is not None:
            while attempts and attempts[0] < cutoff:
                attempts.popleft()
            if not attempts:
                self._attempts[scope].pop(key, None)
        blocked_until = self._blocked_until[scope].get(key)
        if blocked_until is not None and blocked_until <= now:
            self._blocked_until[scope].pop(key, None)


LOGIN_RATE_LIMITER = LoginRateLimiter(
    ip_limit=_env_int("AUTH_LOGIN_IP_LIMIT", 10),
    email_limit=_env_int("AUTH_LOGIN_EMAIL_LIMIT", 5),
    window_seconds=_env_int("AUTH_LOGIN_WINDOW_SECONDS", 3600),
    lockout_seconds=_env_int("AUTH_LOGIN_LOCKOUT_SECONDS", 900),
)
