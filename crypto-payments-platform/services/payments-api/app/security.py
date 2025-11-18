"""
Security utilities.

Covers:
  - Symmetric encryption at rest for sensitive fields (AES-GCM), the kind of
    thing you'd apply to PII or wallet metadata before it hits the DB.
  - A token-bucket rate limiter, applied per-client as API/DevSecOps hygiene
    against abuse and accidental retry storms.

Uses only the standard library's `hashlib`/`hmac` for the demo cipher so the
project runs with zero external crypto dependencies. In production, use a
vetted library (e.g. `cryptography`'s AESGCM) and store keys in Azure Key
Vault / a KMS, never inline in source.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict


# ---------------------------------------------------------------------------
# Encryption at rest (XOR-stream + HMAC, i.e. a minimal authenticated cipher)
# ---------------------------------------------------------------------------
# NOTE: This is a teaching-grade construction to avoid a third-party crypto
# dependency in the sandbox. Real systems must use AES-GCM / ChaCha20-Poly1305
# via an audited library — never hand-roll a stream cipher in production.

_ENCRYPTION_KEY = hashlib.sha256(b"mesh-demo-encryption-key").digest()


def _keystream(nonce: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < length:
        out += hashlib.sha256(_ENCRYPTION_KEY + nonce + counter.to_bytes(4, "big")).digest()
        counter += 1
    return out[:length]


def encrypt(plaintext: str) -> str:
    """Returns nonce.ciphertext.mac, all hex-encoded."""
    nonce = os.urandom(16)
    pt_bytes = plaintext.encode()
    ct_bytes = bytes(a ^ b for a, b in zip(pt_bytes, _keystream(nonce, len(pt_bytes))))
    mac = hmac.new(_ENCRYPTION_KEY, nonce + ct_bytes, hashlib.sha256).digest()
    return f"{nonce.hex()}.{ct_bytes.hex()}.{mac.hex()}"


def decrypt(token: str) -> str:
    nonce_hex, ct_hex, mac_hex = token.split(".")
    nonce, ct_bytes, mac = bytes.fromhex(nonce_hex), bytes.fromhex(ct_hex), bytes.fromhex(mac_hex)
    expected_mac = hmac.new(_ENCRYPTION_KEY, nonce + ct_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_mac, mac):
        raise ValueError("Ciphertext failed integrity check (tampered or wrong key)")
    pt_bytes = bytes(a ^ b for a, b in zip(ct_bytes, _keystream(nonce, len(ct_bytes))))
    return pt_bytes.decode()


# ---------------------------------------------------------------------------
# Rate limiting (token bucket, per client identifier)
# ---------------------------------------------------------------------------
@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class TokenBucketRateLimiter:
    """
    Thread-safe token-bucket limiter.

    capacity: max burst size.
    refill_rate: tokens added per second.
    """

    def __init__(self, capacity: int = 10, refill_rate: float = 2.0):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = Lock()

    def allow(self, client_id: str) -> bool:
        with self._lock:
            now = time.monotonic()
            bucket = self._buckets.get(client_id)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity - 1, last_refill=now)
                self._buckets[client_id] = bucket
                return True

            elapsed = now - bucket.last_refill
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_rate)
            bucket.last_refill = now

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return True
            return False


# Shared limiter instance used by the API layer (per-client, keyed on user/IP).
default_rate_limiter = TokenBucketRateLimiter(capacity=10, refill_rate=2.0)
