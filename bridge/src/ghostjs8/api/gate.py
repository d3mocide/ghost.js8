"""Access control for the browser API: operator sessions and per-address rate limits.

``Gate`` owns every piece of per-viewer state (limiters, connection counts, the cookie
verifier). ``operator_router`` is the login surface. ``app.py`` only asks questions of it.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable, Mapping

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ghostjs8.api.operator import COOKIE_NAME, OperatorAuth, valid_hash
from ghostjs8.settings import Settings
from ghostjs8.util.clock import Clock
from ghostjs8.util.ratelimit import KeyedLimiter, client_ip

log = logging.getLogger("ghostjs8.api.gate")

LOGIN_LOCKOUT_S = 900.0
GLOBAL_LOGIN_FAILURES = 50  # across all addresses per lockout window: stops a distributed guess
DOWNLOAD_SUFFIXES = ("/audio.flac", "/waterfall.png")
FOREVER = float("inf")


class Gate:
    def __init__(self, settings: Settings, clock: Clock) -> None:
        if settings.operator_password_hash and not valid_hash(settings.operator_password_hash):
            raise ValueError(
                "GHOSTJS8_OPERATOR_PASSWORD_HASH is malformed: regenerate it with "
                "`python -m ghostjs8 hash-password`"
            )
        self.settings, self.clock = settings, clock
        self.auth = OperatorAuth(
            settings.operator_password_hash,
            (settings.operator_secret or secrets.token_hex(32)).encode(),
            settings.operator_session_hours * 3600.0,
        )
        self.http = KeyedLimiter(clock, settings.http_requests_per_min, 60.0)
        self.downloads = KeyedLimiter(clock, settings.download_requests_per_min, 60.0)
        self.ws_rate = KeyedLimiter(clock, settings.ws_connects_per_min, 60.0)
        self.login_rate = KeyedLimiter(clock, 10, 60.0)
        self.login_failures = KeyedLimiter(
            clock, settings.login_attempts_per_15min, LOGIN_LOCKOUT_S
        )
        self.login_failures_all = KeyedLimiter(clock, GLOBAL_LOGIN_FAILURES, LOGIN_LOCKOUT_S)
        self._ws_per_ip: dict[str, int] = {}
        if settings.open_access:
            log.warning("GHOSTJS8_OPEN_ACCESS is on: every viewer can control the station")
        elif not self.auth.enabled:
            log.warning(
                "no operator password configured: the station is view-only for everyone "
                "(set GHOSTJS8_OPERATOR_PASSWORD_HASH; see docs/operations.md)"
            )

    @property
    def available(self) -> bool:
        return self.auth.enabled

    def now(self) -> float:
        return self.clock.utc_now().timestamp()

    def ip_of(self, headers: Mapping[str, str], peer: str | None) -> str:
        return client_ip(headers, peer, self.settings.proxy_hops)

    def operator_until(self, token: str | None) -> float | None:
        """Epoch second an operator session ends; None for a viewer."""
        if self.settings.open_access:
            return FOREVER
        return self.auth.expiry(token, self.now())

    def is_operator(self, request: Request) -> bool:
        return self.operator_until(request.cookies.get(COOKIE_NAME)) is not None

    def require_operator(self, request: Request) -> None:
        if not self.is_operator(request):
            raise HTTPException(status_code=401, detail="operator login required")

    def http_limited(self, request: Request) -> JSONResponse | None:
        """A 429 response when this address is over its /api budget, else None."""
        path = request.url.path
        if not path.startswith("/api/"):
            return None
        ip = self.ip_of(request.headers, request.client.host if request.client else None)
        limiter = self.downloads if path.endswith(DOWNLOAD_SUFFIXES) else self.http
        if limiter.allow(ip):
            return None
        return JSONResponse(
            {"detail": "rate limited"},
            status_code=429,
            headers={"Retry-After": str(limiter.retry_after(ip))},
        )

    def admit_ws(self, ip: str) -> str | None:
        """Reason to refuse a new WebSocket from this address, or None (and count it)."""
        if not self.ws_rate.allow(ip):
            return "too many connections; slow down"
        if self._ws_per_ip.get(ip, 0) >= self.settings.max_clients_per_ip:
            return "too many connections from your address"
        self._ws_per_ip[ip] = self._ws_per_ip.get(ip, 0) + 1
        return None

    def release_ws(self, ip: str) -> None:
        if self._ws_per_ip.get(ip, 1) <= 1:
            self._ws_per_ip.pop(ip, None)
        else:
            self._ws_per_ip[ip] -= 1


def operator_router(gate: Gate, origin_ok: Callable[[Request], bool]) -> APIRouter:
    router = APIRouter(prefix="/api/operator")

    @router.get("/session")
    async def session(request: Request) -> JSONResponse:
        return JSONResponse({"operator": gate.is_operator(request), "available": gate.available})

    @router.post("/login")
    async def login(request: Request) -> JSONResponse:
        ip = gate.ip_of(request.headers, request.client.host if request.client else None)
        if not origin_ok(request):
            raise HTTPException(status_code=403, detail="origin not allowed")
        if not gate.available:
            raise HTTPException(status_code=404, detail="operator login is not configured")
        if (
            gate.login_failures.blocked(ip)
            or gate.login_failures_all.blocked("*")
            or not gate.login_rate.allow(ip)
        ):
            log.warning("operator login throttled", extra={"ip": ip})
            raise HTTPException(
                status_code=429,
                detail="too many attempts; try again later",
                headers={"Retry-After": str(max(gate.login_failures.retry_after(ip), 30))},
            )
        try:
            body = await request.json()
        except ValueError:
            body = None
        password = body.get("password") if isinstance(body, dict) else None
        if (
            not isinstance(password, str)
            or len(password) > 256
            or not gate.auth.check_password(password)
        ):
            gate.login_failures.hit(ip)
            gate.login_failures_all.hit("*")
            log.warning("operator login failed", extra={"ip": ip})
            raise HTTPException(status_code=401, detail="wrong password")
        gate.login_failures.reset(ip)
        log.info("operator login", extra={"ip": ip})
        secure = request.url.scheme == "https" or (
            request.headers.get("x-forwarded-proto", "") == "https"
        )
        resp = JSONResponse({"operator": True, "available": True})
        resp.set_cookie(
            COOKIE_NAME,
            gate.auth.issue(gate.now()),
            max_age=int(gate.auth.session_s),
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/",
        )
        return resp

    @router.post("/logout")
    async def logout() -> JSONResponse:
        resp = JSONResponse({"operator": False, "available": gate.available})
        resp.delete_cookie(COOKIE_NAME, path="/", samesite="strict", httponly=True)
        return resp

    return router
