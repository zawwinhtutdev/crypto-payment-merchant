"""
Payments API — the primary microservice.

Endpoints:
  POST /auth/token          - AuthN: exchange credentials for a JWT
  POST /wallets              - create a wallet (custodial or self-custody)
  GET  /wallets/{id}/balance - read balance (AuthZ enforced)
  POST /transfers             - idempotent fiat/stablecoin transfer (core flow)
  POST /transfers/{id}/settle-onchain - bridge a transfer to on-chain settlement
  GET  /health                - liveness/readiness probe (for k8s)

Run locally:
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from .auth import authenticate, get_current_claims, issue_token, require_roles
from .crypto_settlement import BlockchainRPCClient, SelfCustodyWallet, StablecoinSettlementService
from .ledger import InsufficientFundsError, Ledger, WalletNotFoundError, ledger
from .message_queue import TRANSFER_SETTLED_TOPIC, bus
from .models import (
    BalanceResponse,
    Role,
    TokenRequest,
    TokenResponse,
    TransferRequest,
    TransferResponse,
    TransferStatus,
    WalletCreateRequest,
)
from .security import default_rate_limiter, encrypt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("payments-api")

app = FastAPI(
    title="Crypto Payments API",
    description="Demo microservice: crypto-aware payments/settlement backend.",
    version="1.0.0",
)

_rpc_client = BlockchainRPCClient(chain="demo-chain")
_settlement_service = StablecoinSettlementService(_rpc_client)
# transfer_id -> SelfCustodyWallet used for that transfer's on-chain leg
_transfer_wallets: dict[str, SelfCustodyWallet] = {}


# ---------------------------------------------------------------------------
# Cross-cutting: rate limiting middleware (API security / abuse protection)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_id = request.client.host if request.client else "unknown"
    if not default_rate_limiter.allow(client_id):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "rate_limited", "detail": "Too many requests, slow down."},
        )
    return await call_next(request)


@app.get("/health")
def health():
    """Kubernetes liveness/readiness probe target."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# AuthN
# ---------------------------------------------------------------------------
@app.post("/auth/token", response_model=TokenResponse)
def login(body: TokenRequest):
    role = authenticate(body.username, body.password)
    token, ttl = issue_token(body.username, role)
    logger.info("issued token for user=%s role=%s", body.username, role.value)
    return TokenResponse(access_token=token, expires_in=ttl)


# ---------------------------------------------------------------------------
# Wallets
# ---------------------------------------------------------------------------
@app.post("/wallets", status_code=status.HTTP_201_CREATED)
def create_wallet(body: WalletCreateRequest, claims: dict = Depends(get_current_claims)):
    wallet = ledger.create_wallet(owner_id=body.owner_id, currency=body.currency.value)
    # Encrypt owner_id at rest as a stand-in for any sensitive PII field.
    _ = encrypt(body.owner_id)
    return {"wallet_id": wallet.wallet_id, "currency": wallet.currency, "balance": wallet.balance}


@app.get("/wallets/{wallet_id}/balance", response_model=BalanceResponse)
def get_balance(wallet_id: str, claims: dict = Depends(get_current_claims)):
    try:
        wallet = ledger.get_wallet(wallet_id)
    except WalletNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return BalanceResponse(wallet_id=wallet.wallet_id, currency=wallet.currency, balance=wallet.balance)


@app.post("/wallets/{wallet_id}/fund", status_code=status.HTTP_204_NO_CONTENT)
def fund_wallet(wallet_id: str, amount: float, claims: dict = Depends(require_roles(Role.ADMIN))):
    """Admin-only faucet endpoint so the demo can be exercised without a real payment rail."""
    wallet = ledger.get_wallet(wallet_id)
    wallet.balance += amount


# ---------------------------------------------------------------------------
# Transfers (core payments flow)
# ---------------------------------------------------------------------------
@app.post("/transfers", response_model=TransferResponse)
def create_transfer(
    body: TransferRequest,
    claims: dict = Depends(require_roles(Role.ADMIN, Role.MERCHANT, Role.USER)),
):
    try:
        entry, was_duplicate = ledger.post_transfer(
            from_wallet=body.from_wallet,
            to_wallet=body.to_wallet,
            amount=body.amount,
            currency=body.currency.value,
            idempotency_key=body.idempotency_key,
        )
    except WalletNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except InsufficientFundsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    status_value = TransferStatus.DUPLICATE if was_duplicate else TransferStatus(entry.status)

    if not was_duplicate and entry.status == "settled":
        # Publish downstream for the notification-service to consume async —
        # the API response doesn't wait on this.
        bus.publish(
            TRANSFER_SETTLED_TOPIC,
            {
                "transfer_id": entry.transfer_id,
                "from_wallet": entry.from_wallet,
                "to_wallet": entry.to_wallet,
                "amount": entry.amount,
                "currency": entry.currency,
            },
        )

    return TransferResponse(
        transfer_id=entry.transfer_id,
        status=status_value,
        from_wallet=entry.from_wallet,
        to_wallet=entry.to_wallet,
        amount=entry.amount,
        currency=body.currency,
    )


@app.post("/transfers/{transfer_id}/settle-onchain")
def settle_onchain(
    transfer_id: str,
    merchant_address: str,
    claims: dict = Depends(require_roles(Role.ADMIN, Role.MERCHANT)),
):
    """
    Bridges an off-chain ledger transfer to an on-chain stablecoin
    settlement — the "make crypto spendable as traditional value" flow
    that's the core of Mesh's product.
    """
    entry = ledger._entries.get(transfer_id)  # demo access; real code exposes a proper getter
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transfer not found")

    if entry.currency not in ("USDC", "USDT", "PYUSD"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only stablecoin transfers can settle on-chain")

    wallet = _transfer_wallets.setdefault(transfer_id, SelfCustodyWallet.create())
    result = _settlement_service.settle_to_fiat(
        wallet=wallet,
        merchant_address=merchant_address,
        stablecoin=entry.currency,
        amount=entry.amount,
    )
    return result
