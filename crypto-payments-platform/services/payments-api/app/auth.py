"""
AuthN / AuthZ module.

Covers:
  - AuthN: issuing and verifying signed JWTs (HMAC-SHA256) after a
    credential check.
  - AuthZ: role-based access control (RBAC) via a FastAPI dependency
    that decodes the token and enforces required roles per-endpoint.

In a real Mesh-style deployment, this would delegate to an external IdP
(Azure AD / SAML) rather than issuing tokens locally — the local issuer
here exists purely to make the demo runnable end-to-end.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Iterable

from fastapi import Depends, Header, HTTPException, status

from .models import Role

# In production this comes from Azure Key Vault, never hardcoded.
_JWT_SECRET = b"demo-secret-rotate-me-via-key-vault"
_TOKEN_TTL_SECONDS = 3600

# Demo user directory: username -> (password_hash, role)
# Passwords are stored as salted PBKDF2 hashes, never in plaintext.
_SALT = b"mesh-static-demo-salt"


def _hash_password(password: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), _SALT, 100_000)
    return base64.urlsafe_b64encode(digest).decode()


_USER_DIRECTORY = {
    "alice_admin": (_hash_password("admin-pass"), Role.ADMIN),
    "bob_merchant": (_hash_password("merchant-pass"), Role.MERCHANT),
    "carol_user": (_hash_password("user-pass"), Role.USER),
}


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def authenticate(username: str, password: str) -> Role:
    """Verify credentials in constant time and return the user's role."""
    record = _USER_DIRECTORY.get(username)
    if record is None:
        # Still hash something to avoid leaking user existence via timing.
        _hash_password(password)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    expected_hash, role = record
    given_hash = _hash_password(password)
    if not hmac.compare_digest(expected_hash, given_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return role


def issue_token(username: str, role: Role) -> tuple[str, int]:
    """Issue a signed JWT (header.payload.signature), HMAC-SHA256."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": username,
        "role": role.value,
        "iat": now,
        "exp": now + _TOKEN_TTL_SECONDS,
    }
    header_b64 = _b64url_encode(json.dumps(header).encode())
    payload_b64 = _b64url_encode(json.dumps(payload).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(_JWT_SECRET, signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}", _TOKEN_TTL_SECONDS


def _decode_token(token: str) -> dict:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token")

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = hmac.new(_JWT_SECRET, signing_input, hashlib.sha256).digest()
    given_sig = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, given_sig):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token signature")

    payload = json.loads(_b64url_decode(payload_b64))
    if payload["exp"] < int(time.time()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    return payload


def get_current_claims(authorization: str = Header(...)) -> dict:
    """FastAPI dependency: extract + verify the bearer token."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    return _decode_token(token)


def require_roles(*allowed: Role):
    """
    FastAPI dependency factory for RBAC:

        @app.post("/admin-only")
        def endpoint(claims: dict = Depends(require_roles(Role.ADMIN))):
            ...
    """
    allowed_values = {r.value for r in allowed}

    def _checker(claims: dict = Depends(get_current_claims)) -> dict:
        if claims["role"] not in allowed_values:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{claims['role']}' not permitted; requires one of {sorted(allowed_values)}",
            )
        return claims

    return _checker
