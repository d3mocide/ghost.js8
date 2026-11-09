from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ghostjs8.api.app import create_app
from ghostjs8.api.operator import (
    COOKIE_NAME,
    OperatorAuth,
    hash_password,
    valid_hash,
    verify_password,
)
from ghostjs8.receivers.directory import Directory
from ghostjs8.settings import Settings
from ghostjs8.util.clock import ManualClock
from ghostjs8.util.ratelimit import KeyedLimiter, client_ip

from .test_bridge_core import station

PASSWORD = "correct horse battery"
HASH = hash_password(PASSWORD, salt=b"0123456789abcdef")

CONTROL: list[dict[str, Any]] = [
    {
        "v": 1,
        "type": "tune",
        "tuning": {"dial_hz": 7_078_000, "mode": "usb", "low_cut_hz": 100, "high_cut_hz": 3000},
    },
    {
        "v": 1,
        "type": "select_receiver",
        "receiver": {"host": "example.com", "port": 8073, "name": "x", "tls": False},
        "password": "",
    },
    {"v": 1, "type": "disconnect_receiver"},
    {
        "v": 1,
        "type": "ghostnet_settings",
        "autopilot_enabled": False,
        "park": None,
        "record_audio": None,
        "windows": {},
    },
]


async def _fetch(url: str) -> bytes:
    return b'var x = [{"id":"a","status":"active","offline":"no","url":"http://192.0.2.1:8073"},];'


def app(clock: ManualClock | None = None, **kw: object) -> TestClient:
    opts: dict[str, object] = {
        "db_path": "",
        "operator_password_hash": HASH,
        "operator_secret": "k",
    }
    opts.update(kw)
    st = station()
    return TestClient(
        create_app(
            st,
            Settings(**opts),  # type: ignore[arg-type]
            directory=Directory(fetch=_fetch),
            clock=clock or st.clock,
        )
    )


def login(http: TestClient, password: str = PASSWORD, **kw: Any) -> Any:
    return http.post("/api/operator/login", json={"password": password}, **kw)


def hello(ws: Any) -> dict[str, Any]:
    msg: dict[str, Any] = ws.receive_json()
    while msg["type"] != "hello":
        msg = ws.receive_json()
    return msg


def next_error(ws: Any) -> dict[str, Any]:
    for _ in range(20):
        msg: dict[str, Any] = ws.receive_json()
        if msg["type"] == "error":
            return msg
    raise AssertionError("no error received")


# ------------------------------------------------------------------ password + cookie


def test_hash_roundtrip_and_format() -> None:
    assert valid_hash(HASH)
    assert "$" not in HASH  # compose would interpolate it
    assert verify_password(PASSWORD, HASH)
    assert not verify_password("wrong", HASH)
    assert not verify_password(PASSWORD, "garbage")
    assert not valid_hash("scrypt:x:y")


def test_cookie_tamper_expiry_and_password_binding() -> None:
    a = OperatorAuth(HASH, b"secret", 60.0)
    token = a.issue(1000.0)
    assert a.expiry(token, 1001.0) == 1060.0
    assert a.expiry(token, 1061.0) is None  # expired
    assert a.expiry(token + "x", 1001.0) is None  # forged
    assert a.expiry("a.b", 1001.0) is None
    assert a.expiry(None, 1001.0) is None
    assert OperatorAuth(HASH, b"other", 60.0).expiry(token, 1001.0) is None
    assert (
        OperatorAuth(hash_password("another password!"), b"secret", 60.0).expiry(token, 1001.0)
        is None
    )
    assert OperatorAuth("", b"secret", 60.0).expiry(token, 1001.0) is None  # disabled


# ------------------------------------------------------------------------- the gate


@pytest.mark.parametrize("message", CONTROL, ids=lambda m: m["type"])
def test_viewer_cannot_control(message: dict[str, Any]) -> None:
    with app() as http, http.websocket_connect("/ws") as ws:
        h = hello(ws)
        assert h["operator"] is False
        assert h["operator_available"] is True
        ws.send_json(message)
        err = next_error(ws)
        assert err["code"] == "forbidden"


def test_no_password_configured_is_view_only_and_login_404() -> None:
    with app(operator_password_hash="") as http, http.websocket_connect("/ws") as ws:
        h = hello(ws)
        assert h["operator"] is False
        assert h["operator_available"] is False
        ws.send_json(CONTROL[2])
        assert next_error(ws)["code"] == "forbidden"
        assert login(http).status_code == 404


def test_operator_can_control_after_login() -> None:
    with app() as http:
        r = login(http)
        assert r.status_code == 200
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=strict" in cookie
        with http.websocket_connect("/ws") as ws:
            assert hello(ws)["operator"] is True
            ws.send_json(CONTROL[0])
            for _ in range(20):
                m = ws.receive_json()
                assert m["type"] != "error"
                if m["type"] == "session" and m["tuning"]["dial_hz"] == 7_078_000:
                    break
            else:
                raise AssertionError("tune was not applied")


def test_session_expires_mid_connection() -> None:
    clock = ManualClock()
    with app(clock, operator_session_hours=1.0) as http:
        login(http)
        with http.websocket_connect("/ws") as ws:
            assert hello(ws)["operator"] is True
            clock.advance(3601)
            ws.send_json(CONTROL[2])
            assert next_error(ws)["code"] == "forbidden"


def test_open_access_is_explicit_opt_in() -> None:
    with app(operator_password_hash="", open_access=True) as http:
        with http.websocket_connect("/ws") as ws:
            assert hello(ws)["operator"] is True
        assert http.get("/api/receivers").status_code == 200


def test_receiver_directory_and_readyz_detail_are_operator_only() -> None:
    with app() as http:
        assert http.get("/api/receivers").status_code == 401
        assert set(http.get("/readyz").json()) == {"overall"}
        assert http.get("/api/operator/session").json() == {"operator": False, "available": True}
        login(http)
        assert http.get("/api/receivers").status_code == 200
        assert "components" in http.get("/readyz").json() or len(http.get("/readyz").json()) > 1
        assert http.get("/api/operator/session").json()["operator"] is True
        http.post("/api/operator/logout")
        assert http.get("/api/receivers").status_code == 401


def test_forged_cookie_is_a_viewer() -> None:
    with app() as http:
        http.cookies.set(COOKIE_NAME, "eyJleHAiOjk5OTk5OTk5OTl9.AAAA")
        assert http.get("/api/receivers").status_code == 401


# ---------------------------------------------------------------------- rate limiting


def test_login_lockout_after_failures() -> None:
    with app(login_attempts_per_15min=3) as http:
        for _ in range(3):
            assert login(http, "nope").status_code == 401
        assert login(http, PASSWORD).status_code == 429  # locked out, even with the right one
        assert "retry-after" in login(http, PASSWORD).headers


def test_login_lockout_expires() -> None:
    clock = ManualClock()
    with app(clock, login_attempts_per_15min=2) as http:
        login(http, "a")
        login(http, "b")
        assert login(http, PASSWORD).status_code == 429
        clock.advance(901)
        assert login(http, PASSWORD).status_code == 200


def test_login_rejects_cross_origin() -> None:
    with app() as http:
        r = http.post(
            "/api/operator/login",
            json={"password": PASSWORD},
            headers={"origin": "https://evil.example", "host": "ghost.example"},
        )
        assert r.status_code == 403


def test_http_rate_limit_per_ip_and_downloads_stricter() -> None:
    with app(http_requests_per_min=3, download_requests_per_min=1) as http:
        for _ in range(3):
            assert http.get("/api/nets").status_code == 200
        limited = http.get("/api/nets")
        assert limited.status_code == 429
        assert "retry-after" in limited.headers
        assert http.get("/healthz").status_code == 200  # probes are never limited
    with app(download_requests_per_min=1) as http:
        assert http.get("/api/nets/na-net-20261009T0100Z/audio.flac").status_code == 404
        assert http.get("/api/nets/na-net-20261009T0100Z/audio.flac").status_code == 429


def test_per_ip_websocket_cap_and_x_forwarded_for() -> None:
    with app(max_clients_per_ip=1, proxy_hops=1) as http:
        a = {"x-forwarded-for": "198.51.100.1, 10.0.0.2"}
        b = {"x-forwarded-for": "198.51.100.2, 10.0.0.2"}
        with http.websocket_connect("/ws", headers=a) as ws1:
            hello(ws1)
            with (
                pytest.raises(WebSocketDisconnect) as refused,
                http.websocket_connect("/ws", headers=a),
            ):
                pass
            assert refused.value.code == 1013
            with http.websocket_connect("/ws", headers=b) as ws3:  # another viewer: fine
                hello(ws3)
        with http.websocket_connect("/ws", headers=a) as ws4:  # slot freed
            hello(ws4)


def test_keyed_limiter_window_and_bounded_keys() -> None:
    clock = ManualClock()
    lim = KeyedLimiter(clock, 2, 10.0, max_keys=3)
    assert lim.allow("a")
    assert lim.allow("a")
    assert not lim.allow("a")
    assert lim.retry_after("a") >= 1
    clock.advance(11)
    assert lim.allow("a")
    for k in "bcdef":
        lim.allow(k)
    assert len(lim._hits) <= 3


def test_client_ip_ignores_spoofed_left_entries() -> None:
    h = {"x-forwarded-for": "1.2.3.4, 203.0.113.9, 10.0.0.2"}
    assert client_ip(h, "172.18.0.3", 1) == "203.0.113.9"
    assert client_ip({"x-forwarded-for": "203.0.113.9"}, "172.18.0.3", 0) == "203.0.113.9"
    assert client_ip({}, "172.18.0.3", 1) == "172.18.0.3"
    assert client_ip({"x-forwarded-for": "203.0.113.9"}, "172.18.0.3", 1) == "172.18.0.3"
