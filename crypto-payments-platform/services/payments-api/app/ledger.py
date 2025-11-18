"""
Double-entry ledger.

Covers core distributed-payments-system concepts:
  - Atomicity: a transfer either fully applies (both legs) or not at all.
  - Idempotency: replaying the same `idempotency_key` returns the original
    result instead of double-processing — the standard defence against
    client retries/timeouts causing duplicate money movement.
  - Strong consistency for balances: guarded by a lock, because for a
    ledger you want correctness over raw throughput (contrast with e.g.
    a "likes" counter which could tolerate eventual consistency).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, Optional


class InsufficientFundsError(Exception):
    pass


class WalletNotFoundError(Exception):
    pass


@dataclass
class Wallet:
    wallet_id: str
    owner_id: str
    currency: str
    balance: float = 0.0


@dataclass
class LedgerEntry:
    transfer_id: str
    from_wallet: str
    to_wallet: str
    amount: float
    currency: str
    idempotency_key: str
    status: str  # "settled" | "failed"


class Ledger:
    """
    In-memory ledger. In production this is a durable, replicated store
    (e.g. an Azure SQL / Postgres table with serializable isolation, or an
    event-sourced log) — the in-memory dict here stands in for that so the
    project runs without external infra.
    """

    def __init__(self) -> None:
        self._wallets: Dict[str, Wallet] = {}
        self._entries: Dict[str, LedgerEntry] = {}
        # idempotency_key -> transfer_id, so replays are detected in O(1)
        self._idempotency_index: Dict[str, str] = {}
        self._lock = RLock()

    def create_wallet(self, owner_id: str, currency: str, opening_balance: float = 0.0) -> Wallet:
        with self._lock:
            wallet = Wallet(wallet_id=str(uuid.uuid4()), owner_id=owner_id,
                             currency=currency, balance=opening_balance)
            self._wallets[wallet.wallet_id] = wallet
            return wallet

    def get_wallet(self, wallet_id: str) -> Wallet:
        wallet = self._wallets.get(wallet_id)
        if wallet is None:
            raise WalletNotFoundError(f"Wallet {wallet_id} does not exist")
        return wallet

    def post_transfer(
        self,
        from_wallet: str,
        to_wallet: str,
        amount: float,
        currency: str,
        idempotency_key: str,
    ) -> tuple[LedgerEntry, bool]:
        """
        Returns (entry, was_duplicate).

        The whole check-then-act sequence is under a single lock to make the
        operation atomic: no interleaving request can observe or act on a
        half-applied transfer.
        """
        with self._lock:
            existing_transfer_id = self._idempotency_index.get(idempotency_key)
            if existing_transfer_id is not None:
                return self._entries[existing_transfer_id], True

            src = self.get_wallet(from_wallet)
            dst = self.get_wallet(to_wallet)

            if src.currency != currency or dst.currency != currency:
                entry = self._record_failure(from_wallet, to_wallet, amount, currency, idempotency_key)
                return entry, False

            if src.balance < amount:
                entry = self._record_failure(from_wallet, to_wallet, amount, currency, idempotency_key)
                raise InsufficientFundsError(
                    f"Wallet {from_wallet} has {src.balance} {currency}, needs {amount}"
                )

            # Both legs applied atomically under the lock.
            src.balance -= amount
            dst.balance += amount

            entry = LedgerEntry(
                transfer_id=str(uuid.uuid4()),
                from_wallet=from_wallet,
                to_wallet=to_wallet,
                amount=amount,
                currency=currency,
                idempotency_key=idempotency_key,
                status="settled",
            )
            self._entries[entry.transfer_id] = entry
            self._idempotency_index[idempotency_key] = entry.transfer_id
            return entry, False

    def _record_failure(self, from_wallet, to_wallet, amount, currency, idempotency_key) -> LedgerEntry:
        entry = LedgerEntry(
            transfer_id=str(uuid.uuid4()),
            from_wallet=from_wallet,
            to_wallet=to_wallet,
            amount=amount,
            currency=currency,
            idempotency_key=idempotency_key,
            status="failed",
        )
        self._entries[entry.transfer_id] = entry
        self._idempotency_index[idempotency_key] = entry.transfer_id
        return entry


# Process-wide singleton ledger for the demo API.
ledger = Ledger()
