#!/usr/bin/env python3
"""Fetch the upstream JS8Call test recording at a pinned commit and verify it.

Stdlib only. Fails hard (exit 1) on any SHA-256 mismatch. The file is GPL-3.0
licensed upstream content and is cached locally, never committed (see README).
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

REPO = "JS8Call-improved/js8call-improved"
COMMIT = "4c592bd9a034f18178a3e7179db92acb14939668"  # tag v3.0.3
PATH = "media/tests/A_1_4.wav"
SHA256 = "60b650c2090dff5e2144f164ebe692cde5f048c769518e1b1b9e67223f3da138"
URL = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{PATH}"

CACHE = Path(__file__).resolve().parent / "cache"
TARGET = CACHE / "A_1_4.wav"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    if TARGET.exists() and sha256(TARGET.read_bytes()) == SHA256:
        print(f"fixture ok (cached): {TARGET}")
        return 0
    print(f"fetching {URL}")
    with urllib.request.urlopen(URL, timeout=60) as resp:  # noqa: S310 - fixed https URL
        data = resp.read()
    digest = sha256(data)
    if digest != SHA256:
        print(f"SHA-256 MISMATCH for {PATH}\n  expected {SHA256}\n  got      {digest}", file=sys.stderr)
        return 1
    CACHE.mkdir(exist_ok=True)
    tmp = TARGET.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(TARGET)
    print(f"fixture ok: {TARGET} ({len(data)} bytes, sha256 {digest})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
