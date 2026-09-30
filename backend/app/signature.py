"""ElevenLabs webhook signature: header `ElevenLabs-Signature: t=<unix ts>,v0=<hex hmac>`.

v0 = HMAC-SHA256(secret, "<ts>.<raw body>"). Requests older than the tolerance are rejected (replay protection).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

FUTURE_SKEW_SECS = 300


class SignatureError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def sign(body: bytes, secret: str, timestamp: Optional[int] = None) -> str:
    """Build a header value. Used by tests and by replay scripts."""
    ts = int(timestamp if timestamp is not None else time.time())
    mac = hmac.new(secret.encode("utf-8"), f"{ts}.".encode("utf-8") + body, hashlib.sha256).hexdigest()
    return f"t={ts},v0={mac}"


def verify(
    header: Optional[str],
    body: bytes,
    secret: str,
    tolerance_secs: int = 1800,
    now: Optional[float] = None,
) -> None:
    """Raise SignatureError unless the header is a valid, fresh signature of body."""
    if not secret:
        raise SignatureError("webhook secret not configured")
    if not header:
        raise SignatureError("missing signature header")

    timestamp: Optional[int] = None
    signatures: list[str] = []
    for part in header.split(","):
        key, sep, value = part.strip().partition("=")
        if not sep:
            continue
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise SignatureError("malformed timestamp") from exc
        elif key == "v0":
            signatures.append(value.strip())
    if timestamp is None or not signatures:
        raise SignatureError("malformed signature header")

    current = time.time() if now is None else now
    if current - timestamp > tolerance_secs:
        raise SignatureError("signature expired")
    if timestamp - current > FUTURE_SKEW_SECS:
        raise SignatureError("signature timestamp in the future")

    expected = hmac.new(
        secret.encode("utf-8"), f"{timestamp}.".encode("utf-8") + body, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        raise SignatureError("signature mismatch")
