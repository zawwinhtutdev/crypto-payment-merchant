"""
Pydantic models for the Payments API.

Demonstrates REST API design principles: explicit request/response schemas,
strict input validation, and clear separation between wire format and
internal domain objects.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Currency(str, Enum):
    USD = "USD"
    USDC = "USDC"
    USDT = "USDT"
    PYUSD = "PYUSD"


class Role(str, Enum):
    ADMIN = "admin"
    MERCHANT = "merchant"
    USER = "user"


class TokenRequest(BaseModel):
    """AuthN: exchange a username for a signed JWT (demo-only password flow)."""
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class WalletCreateRequest(BaseModel):
    owner_id: str
    currency: Currency
    is_self_custody: bool = Field(
        default=False,
        description="True = user controls private key (self-custody). "
        "False = Mesh-style custodial/omnibus wallet.",
    )


class TransferRequest(BaseModel):
    """
    A payment/transfer instruction.

    idempotency_key is REQUIRED — this is the mechanism that makes retried
    network calls safe in a distributed payments system (client can safely
    retry on timeout without risking a double-spend).
    """
    from_wallet: str
    to_wallet: str
    amount: float = Field(gt=0, description="Must be strictly positive")
    currency: Currency
    idempotency_key: str = Field(min_length=8, max_length=128)
    memo: Optional[str] = Field(default=None, max_length=280)

    @field_validator("amount")
    @classmethod
    def round_to_cents(cls, v: float) -> float:
        return round(v, 6)  # 6dp to accommodate stablecoin precision


class TransferStatus(str, Enum):
    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"
    DUPLICATE = "duplicate"  # returned when idempotency key was replayed


class TransferResponse(BaseModel):
    transfer_id: str
    status: TransferStatus
    from_wallet: str
    to_wallet: str
    amount: float
    currency: Currency
    settlement_tx_hash: Optional[str] = None


class BalanceResponse(BaseModel):
    wallet_id: str
    currency: Currency
    balance: float


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
