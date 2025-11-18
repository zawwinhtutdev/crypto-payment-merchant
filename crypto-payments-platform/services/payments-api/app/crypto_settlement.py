"""
Crypto settlement layer.

Covers crypto/blockchain concepts called out in the JD: blockchains, RPCs,
self-custody wallets, and the "stablecoin -> spendable value" settlement
problem that is literally Mesh's business (fiat off-ramp for stablecoins).

Everything here is a deterministic simulation (no real chain, no real
keys) so the project has zero external dependencies and no real funds risk
— but the shapes of the interfaces mirror how a real integration looks:
an RPC client you call to check tx status, a wallet abstraction that
distinguishes self-custody (user holds the key) from custodial, and a
settlement service that converts a stablecoin amount into fiat value.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict


class TxStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


@dataclass
class KeyPair:
    """A simulated Ed25519-style keypair. Never do real keygen like this."""
    private_key: str
    public_key: str

    @classmethod
    def generate(cls) -> "KeyPair":
        priv = secrets.token_hex(32)
        pub = hashlib.sha256(bytes.fromhex(priv)).hexdigest()
        return cls(private_key=priv, public_key=pub)


@dataclass
class SelfCustodyWallet:
    """
    Self-custody: the wallet controls its own private key. Mesh-style
    integrations never see or store this key — they only ever request a
    *signature* or a *connection* via a wallet provider (WalletConnect-style),
    which is why `sign` is the only operation exposed here.
    """
    keypair: KeyPair
    address: str

    @classmethod
    def create(cls) -> "SelfCustodyWallet":
        kp = KeyPair.generate()
        address = "0x" + kp.public_key[:40]
        return cls(keypair=kp, address=address)

    def sign(self, message: str) -> str:
        return hashlib.sha256((self.keypair.private_key + message).encode()).hexdigest()


class BlockchainRPCClient:
    """
    Stand-in for a real JSON-RPC client (e.g. an Infura/Alchemy-style
    provider) that a payments backend calls to broadcast and confirm
    transactions on-chain.
    """

    def __init__(self, chain: str = "ethereum-mainnet"):
        self.chain = chain
        self._tx_log: Dict[str, TxStatus] = {}

    def broadcast_transaction(self, from_address: str, to_address: str, amount: float, signature: str) -> str:
        tx_hash = "0x" + hashlib.sha256(
            f"{from_address}{to_address}{amount}{signature}{time.time()}".encode()
        ).hexdigest()
        # Real RPCs are async and take multiple blocks to confirm; we
        # simulate immediate confirmation to keep the demo deterministic.
        self._tx_log[tx_hash] = TxStatus.CONFIRMED
        return tx_hash

    def get_transaction_status(self, tx_hash: str) -> TxStatus:
        return self._tx_log.get(tx_hash, TxStatus.FAILED)


class StablecoinSettlementService:
    """
    This is Mesh's actual core problem in miniature: a user holds a
    stablecoin balance (USDC/USDT/PYUSD) and a merchant wants to receive
    fiat value without volatility exposure. The settlement service
    converts + records that on/off-ramp step.
    """

    # Simplified peg assumptions for the demo (real system would pull live
    # rates and handle de-peg risk / slippage).
    _PEG_RATE_TO_USD = {
        "USDC": 1.0,
        "USDT": 1.0,
        "PYUSD": 1.0,
    }

    def __init__(self, rpc_client: BlockchainRPCClient):
        self.rpc_client = rpc_client

    def settle_to_fiat(
        self, wallet: SelfCustodyWallet, merchant_address: str, stablecoin: str, amount: float
    ) -> dict:
        if stablecoin not in self._PEG_RATE_TO_USD:
            raise ValueError(f"Unsupported stablecoin: {stablecoin}")

        message = f"settle:{merchant_address}:{amount}:{stablecoin}"
        signature = wallet.sign(message)
        tx_hash = self.rpc_client.broadcast_transaction(
            wallet.address, merchant_address, amount, signature
        )
        status = self.rpc_client.get_transaction_status(tx_hash)
        fiat_value = round(amount * self._PEG_RATE_TO_USD[stablecoin], 2)

        return {
            "tx_hash": tx_hash,
            "chain_status": status.value,
            "stablecoin": stablecoin,
            "stablecoin_amount": amount,
            "settled_fiat_currency": "USD",
            "settled_fiat_amount": fiat_value,
        }
