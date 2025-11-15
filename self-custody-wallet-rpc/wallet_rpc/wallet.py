"""
Self-custody wallet.

"Self-custody" means the private key is generated and held entirely
client-side, and is never transmitted to any server — including the RPC
node this wallet talks to. The RPC provider only ever receives a
*signed* transaction (a public artifact); it never sees the key that
produced the signature.

This is the foundational trust model that distinguishes self-custody
wallets (this module) from custodial wallets (where an exchange or
custodian holds the key on the user's behalf).
"""
from __future__ import annotations

from dataclasses import dataclass

from eth_account import Account
from eth_account.datastructures import SignedTransaction
from eth_account.signers.local import LocalAccount


@dataclass(frozen=True)
class Wallet:
    """
    Thin wrapper around eth_account's LocalAccount.

    The private key lives only in this object, in memory, for the
    lifetime of the process. Nothing in this module ever logs it,
    sends it over a network call, or writes it to disk.
    """
    account: LocalAccount

    @property
    def address(self) -> str:
        return self.account.address

    @classmethod
    def create(cls) -> "Wallet":
        """Generate a brand-new keypair (new self-custody wallet)."""
        account = Account.create()
        return cls(account=account)

    @classmethod
    def from_private_key(cls, private_key: str) -> "Wallet":
        """
        Load an existing wallet from a private key.

        Useful for restoring a wallet you generated previously — but note
        that in a real product, private keys are typically derived from a
        BIP-39 mnemonic seed phrase rather than passed around raw. This
        project keeps it to raw keys for simplicity; see README for the
        mnemonic-based extension idea.
        """
        account = Account.from_key(private_key)
        return cls(account=account)

    def export_private_key_HEX_DANGEROUS(self) -> str:
        """
        Returns the raw private key as a hex string.

        Named loudly on purpose: exporting/printing/logging a private key
        anywhere outside a secure, local context is exactly the mistake
        that turns "self-custody" into "self-inflicted loss of funds."
        Only used in this project's CLI for demo/testnet purposes.
        """
        return self.account.key.hex()

    def sign_transaction(self, transaction_dict: dict) -> SignedTransaction:
        """
        Sign a transaction locally. The private key never leaves this
        process — only the resulting signed transaction (safe to
        broadcast publicly) is returned.
        """
        return self.account.sign_transaction(transaction_dict)

    def sign_message(self, message: str) -> str:
        """
        Sign an arbitrary message — the mechanism used for
        "sign-in with wallet" / proof-of-ownership flows, distinct
        from signing a value-transferring transaction.
        """
        from eth_account.messages import encode_defunct

        signable = encode_defunct(text=message)
        signed = self.account.sign_message(signable)
        return signed.signature.hex()
