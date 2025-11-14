"""
Multi-chain JSON-RPC client.

This wraps web3.py to talk to any EVM-compatible chain's JSON-RPC endpoint
(Ethereum Sepolia and Polygon Amoy testnets by default — see chains.py).
This is the piece a payments backend like Mesh's calls constantly: reading
on-chain state (balances, confirmations) and broadcasting signed
transactions, without ever running its own blockchain node.

Provider setup: get a free RPC URL from Infura (https://infura.io) or
Alchemy (https://alchemy.com) — see README for the 5-minute signup.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from eth_account.datastructures import SignedTransaction
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from .chains import ChainConfig


@dataclass
class TxReceiptSummary:
    tx_hash: str
    status: str  # "success" | "failed" | "pending"
    block_number: Optional[int]
    gas_used: Optional[int]


class RPCClient:
    """
    A connection to one chain's RPC endpoint. Create one instance per
    chain if you need multi-chain support (Mesh's whole thesis is
    unifying many chains behind one integration — this class is the unit
    you'd replicate per-chain to build that).
    """

    def __init__(self, chain: ChainConfig, rpc_url: str):
        self.chain = chain
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if chain.is_poa:
            # Some chains (e.g. some L2s/testnets) use Proof-of-Authority
            # block headers that need this middleware to decode correctly.
            self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    def is_connected(self) -> bool:
        return self.w3.is_connected()

    def get_block_number(self) -> int:
        return self.w3.eth.block_number

    def get_gas_price_gwei(self) -> float:
        wei = self.w3.eth.gas_price
        return self.w3.from_wei(wei, "gwei")

    def get_native_balance(self, address: str) -> float:
        """Native currency balance (ETH on Ethereum, MATIC on Polygon, etc)."""
        wei = self.w3.eth.get_balance(Web3.to_checksum_address(address))
        return self.w3.from_wei(wei, "ether")

    def get_erc20_balance(self, token_contract_address: str, wallet_address: str) -> float:
        """
        Read an ERC-20 token balance (e.g. testnet USDC) — the stablecoin
        settlement layer Mesh's product actually sits on top of.
        """
        erc20_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function",
            },
        ]
        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_contract_address), abi=erc20_abi
        )
        raw_balance = contract.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
        decimals = contract.functions.decimals().call()
        return raw_balance / (10 ** decimals)

    def build_transfer_transaction(self, from_address: str, to_address: str, amount_ether: float) -> dict:
        """Construct an unsigned native-currency transfer transaction."""
        nonce = self.w3.eth.get_transaction_count(Web3.to_checksum_address(from_address))
        return {
            "chainId": self.chain.chain_id,
            "from": Web3.to_checksum_address(from_address),
            "to": Web3.to_checksum_address(to_address),
            "value": self.w3.to_wei(amount_ether, "ether"),
            "nonce": nonce,
            "gas": 21_000,  # standard cost for a plain native transfer
            "gasPrice": self.w3.eth.gas_price,
        }

    def broadcast_signed_transaction(self, signed_tx: SignedTransaction) -> str:
        """Broadcast a locally-signed transaction. Returns the tx hash."""
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        return tx_hash.hex()

    def wait_for_confirmation(self, tx_hash: str, timeout_seconds: int = 120) -> TxReceiptSummary:
        """Block until the transaction is mined (or timeout), then summarize the receipt."""
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout_seconds)
        return TxReceiptSummary(
            tx_hash=tx_hash,
            status="success" if receipt.status == 1 else "failed",
            block_number=receipt.blockNumber,
            gas_used=receipt.gasUsed,
        )
