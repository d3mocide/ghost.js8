"""Operator mode: the password gate for everything that changes shared state.

Viewers are anonymous and read-only. An operator logs in over HTTPS with a password; the
bridge verifies it against a scrypt hash from the environment and sets a signed, expiring,
``HttpOnly`` cookie. The WebSocket upgrade reads that cookie, and ``_handle`` refuses every
control message from a connection that is not an operator. Nothing is trusted from the browser
but the signed cookie, and nothing secret ships in the web bundle.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
_MAXMEM = 64 * 1024 * 1024
COOKIE_NAME = "ghostjs8_op"


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """``scrypt:N:r:p:salt:hash`` (colon-separated so compose never sees a ``$``)."""
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=_MAXMEM
    )
    return f"scrypt:{SCRYPT_N}:{SCRYPT_R}:{SCRYPT_P}:{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split(":")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=_MAXMEM,
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def valid_hash(stored: str) -> bool:
    parts = stored.split(":")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        [int(x) for x in parts[1:4]]
        bytes.fromhex(parts[4])
        bytes.fromhex(parts[5])
    except ValueError:
        return False
    return True


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass(frozen=True)
class OperatorAuth:
    """Password check + cookie sessions. ``password_hash`` empty means operator mode is off."""

    password_hash: str
    secret: bytes
    session_s: float

    @property
    def enabled(self) -> bool:
        return bool(self.password_hash)

    def check_password(self, password: str) -> bool:
        return self.enabled and verify_password(password, self.password_hash)

    def _key(self) -> bytes:
        # Bound to the hash: changing the password signs every operator out.
        return hmac.new(self.secret, self.password_hash.encode(), hashlib.sha256).digest()

    def issue(self, now_epoch: float) -> str:
        body = _b64(
            json.dumps({"exp": int(now_epoch + self.session_s), "n": secrets.token_hex(8)}).encode()
        )
        sig = _b64(hmac.new(self._key(), body.encode(), hashlib.sha256).digest())
        return f"{body}.{sig}"

    def expiry(self, token: str | None, now_epoch: float) -> float | None:
        """Epoch second the session ends, or None if the token is missing, forged or expired."""
        if not self.enabled or not token or token.count(".") != 1:
            return None
        body, sig = token.split(".")
        good = _b64(hmac.new(self._key(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        try:
            exp = float(json.loads(_unb64(body))["exp"])
        except (ValueError, KeyError, TypeError, binascii.Error):
            return None
        return exp if exp > now_epoch else None
