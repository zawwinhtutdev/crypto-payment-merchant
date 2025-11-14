"""
Chain configuration registry.

Keeping chain-specific constants (chain ID, native currency, whether it
needs POA middleware, known testnet token addresses) in one place is what
makes the RPCClient reusable across chains rather than hardcoded to
Ethereum — the pattern any "network of networks" style integration
(Mesh's own positioning) needs at its base.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChainConfig:
    name: str
    chain_id: int
    native_currency: str
    is_poa: bool
    block_explorer: str


SEPOLIA = ChainConfig(
    name="Ethereum Sepolia",
    chain_id=11155111,
    native_currency="ETH",
    is_poa=False,
    block_explorer="https://sepolia.etherscan.io",
)

POLYGON_AMOY = ChainConfig(
    name="Polygon Amoy",
    chain_id=80002,
    native_currency="MATIC",
    is_poa=True,
    block_explorer="https://amoy.polygonscan.com",
)

# Well-known testnet ERC-20 stablecoin contract addresses, for the
# get_erc20_balance() demo. USDC on Sepolia (Circle's official testnet
# faucet contract) as of this writing — verify on Etherscan before relying
# on it, testnet contract addresses do occasionally change.
SEPOLIA_USDC_CONTRACT = "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238"

CHAINS = {
    "sepolia": SEPOLIA,
    "amoy": POLYGON_AMOY,
}
