"""
CLI for the self-custody wallet + multi-chain RPC client.

Usage examples (see README for full setup):

    python -m wallet_rpc.cli create-wallet
    python -m wallet_rpc.cli balance --address 0xabc... --chain sepolia
    python -m wallet_rpc.cli send --private-key 0x... --to 0xdef... --amount 0.001 --chain sepolia
"""
from __future__ import annotations

import argparse
import os
import sys

from .chains import CHAINS, SEPOLIA_USDC_CONTRACT
from .rpc_client import RPCClient
from .wallet import Wallet


def _get_rpc_url(chain_key: str) -> str:
    env_var = f"{chain_key.upper()}_RPC_URL"
    url = os.environ.get(env_var)
    if not url:
        print(
            f"Missing {env_var}. Set it in a .env file or export it, "
            f"pointing at a free Infura/Alchemy RPC endpoint. See README.",
            file=sys.stderr,
        )
        sys.exit(1)
    return url


def cmd_create_wallet(args: argparse.Namespace) -> None:
    wallet = Wallet.create()
    print(f"New self-custody wallet created.\n")
    print(f"  Address:     {wallet.address}")
    print(f"  Private key: {wallet.export_private_key_HEX_DANGEROUS()}")
    print(
        "\nWARNING: this private key is shown once, in plaintext, for demo "
        "purposes only. Never share it, commit it, or reuse a key generated "
        "this way for anything holding real value. Store it in a password "
        "manager or hardware wallet if you want to keep using this address."
    )


def cmd_balance(args: argparse.Namespace) -> None:
    chain = CHAINS[args.chain]
    client = RPCClient(chain, _get_rpc_url(args.chain))

    if not client.is_connected():
        print(f"Could not connect to {chain.name} RPC endpoint.", file=sys.stderr)
        sys.exit(1)

    native = client.get_native_balance(args.address)
    print(f"Chain:   {chain.name}")
    print(f"Address: {args.address}")
    print(f"Balance: {native} {chain.native_currency}")

    if args.chain == "sepolia":
        try:
            usdc = client.get_erc20_balance(SEPOLIA_USDC_CONTRACT, args.address)
            print(f"USDC:    {usdc}")
        except Exception as exc:  # noqa: BLE001 - demo CLI, keep it simple
            print(f"(USDC balance check skipped: {exc})")


def cmd_send(args: argparse.Namespace) -> None:
    chain = CHAINS[args.chain]
    client = RPCClient(chain, _get_rpc_url(args.chain))
    wallet = Wallet.from_private_key(args.private_key)

    print(f"Sending {args.amount} {chain.native_currency} on {chain.name}")
    print(f"  From: {wallet.address}")
    print(f"  To:   {args.to}")

    unsigned_tx = client.build_transfer_transaction(wallet.address, args.to, args.amount)
    signed_tx = wallet.sign_transaction(unsigned_tx)  # signing happens locally
    tx_hash = client.broadcast_signed_transaction(signed_tx)
    print(f"\nBroadcast. Tx hash: {tx_hash}")
    print(f"Explorer: {chain.block_explorer}/tx/{tx_hash}")

    print("\nWaiting for confirmation...")
    receipt = client.wait_for_confirmation(tx_hash)
    print(f"Status: {receipt.status} (block {receipt.block_number}, gas used {receipt.gas_used})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Self-custody wallet + RPC client demo")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("create-wallet", help="Generate a new self-custody keypair")

    p_balance = sub.add_parser("balance", help="Check native + USDC balance for an address")
    p_balance.add_argument("--address", required=True)
    p_balance.add_argument("--chain", choices=CHAINS.keys(), default="sepolia")

    p_send = sub.add_parser("send", help="Sign and broadcast a native-currency transfer")
    p_send.add_argument("--private-key", required=True)
    p_send.add_argument("--to", required=True)
    p_send.add_argument("--amount", type=float, required=True, help="Amount in ETH/MATIC")
    p_send.add_argument("--chain", choices=CHAINS.keys(), default="sepolia")

    args = parser.parse_args()
    {
        "create-wallet": cmd_create_wallet,
        "balance": cmd_balance,
        "send": cmd_send,
    }[args.command](args)


if __name__ == "__main__":
    main()
