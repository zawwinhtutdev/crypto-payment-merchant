import time

import pytest
from fastapi import HTTPException

from app.auth import authenticate, issue_token, _decode_token
from app.models import Role
from app.security import encrypt, decrypt, TokenBucketRateLimiter


def test_authenticate_success():
    role = authenticate("alice_admin", "admin-pass")
    assert role == Role.ADMIN


def test_authenticate_wrong_password_rejected():
    with pytest.raises(HTTPException) as exc_info:
        authenticate("alice_admin", "wrong-password")
    assert exc_info.value.status_code == 401


def test_authenticate_unknown_user_rejected():
    with pytest.raises(HTTPException) as exc_info:
        authenticate("nobody", "whatever")
    assert exc_info.value.status_code == 401


def test_issued_token_round_trips():
    token, ttl = issue_token("carol_user", Role.USER)
    claims = _decode_token(token)
    assert claims["sub"] == "carol_user"
    assert claims["role"] == "user"
    assert ttl == 3600


def test_tampered_token_rejected():
    token, _ = issue_token("carol_user", Role.USER)
    header, payload, sig = token.split(".")
    tampered = f"{header}.{payload}.{sig[:-2]}00"  # corrupt signature
    with pytest.raises(HTTPException) as exc_info:
        _decode_token(tampered)
    assert exc_info.value.status_code == 401


def test_encrypt_decrypt_round_trip():
    secret = "user-pii-12345"
    token = encrypt(secret)
    assert token != secret  # must not be stored in plaintext
    assert decrypt(token) == secret


def test_decrypt_detects_tampering():
    token = encrypt("sensitive-data")
    nonce, ct, mac = token.split(".")
    tampered = f"{nonce}.{ct}.{'0' * len(mac)}"
    with pytest.raises(ValueError):
        decrypt(tampered)


def test_rate_limiter_blocks_after_capacity_exhausted():
    limiter = TokenBucketRateLimiter(capacity=3, refill_rate=0.0)  # no refill during test
    client = "test-client"
    assert limiter.allow(client) is True
    assert limiter.allow(client) is True
    assert limiter.allow(client) is True
    assert limiter.allow(client) is False  # 4th request within the burst window


def test_rate_limiter_refills_over_time():
    limiter = TokenBucketRateLimiter(capacity=1, refill_rate=100.0)  # fast refill
    client = "test-client-2"
    assert limiter.allow(client) is True
    assert limiter.allow(client) is False
    time.sleep(0.05)  # enough time for >1 token to refill at 100/sec
    assert limiter.allow(client) is True
