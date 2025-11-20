# Self-Custody Wallet + Multi-Chain RPC Client

A small, focused project demonstrating the core building blocks of crypto
payments infrastructure: **self-custody key management**, a **JSON-RPC
client** for reading on-chain state and broadcasting transactions, and
**ERC-20 stablecoin balance checks** — the same primitives that sit
underneath any "pay with crypto" product.

Built as a self-directed learning project to go deeper on blockchain/RPC/
wallet fundamentals alongside backend and distributed-systems work.

## Why this project

Most crypto-payments products (Mesh, MoonPay, and similar infrastructure
companies) are ultimately built on three things: a wallet that holds keys,
an RPC client that talks to a chain, and a settlement layer that converts
on-chain value into something a merchant can use. This project implements
the first two directly against a **real public Ethereum testnet** — not a
simulation — and documents the settlement problem in the README below.

## What it does

- **Generates a real self-custody keypair** (secp256k1, via `eth_account`) —
  the private key never leaves the local process.
- **Connects to Ethereum Sepolia** (or Polygon Amoy) via a standard
  JSON-RPC endpoint (Infura/Alchemy).
- **Reads on-chain state**: native currency balance, ERC-20 token
  balance (testnet USDC), current block number, gas price.
- **Signs and broadcasts a transaction**: builds an unsigned transfer,
  signs it locally with the private key, submits the raw signed
  transaction to the network, and polls for confirmation.

## Project layout

```
wallet_rpc/
├── wallet.py       # Self-custody wallet: keygen, local signing
├── rpc_client.py   # JSON-RPC client: balances, tx build/broadcast/confirm
├── chains.py       # Chain configs (Sepolia, Polygon Amoy) — multi-chain pattern
└── cli.py          # CLI entry point tying it together

tests/
├── test_wallet.py      # Local crypto ops — no network required
└── test_rpc_client.py  # RPC client logic, with Web3 mocked out
```

## Setup

```bash
git clone <this-repo>
cd self-custody-wallet-rpc
pip install -r requirements.txt

cp .env.example .env
# Edit .env: add a free RPC URL from https://infura.io or https://alchemy.com
```

You'll also want some free Sepolia testnet ETH to actually broadcast a
transaction — get it from a faucet like
[sepoliafaucet.com](https://sepoliafaucet.com) once you've generated an
address (step 1 below).

## Usage

```bash
# 1. Generate a new self-custody wallet
python -m wallet_rpc.cli create-wallet
# -> prints an address + private key. Fund the address via a Sepolia faucet.

# 2. Check its balance (native ETH + testnet USDC)
python -m wallet_rpc.cli balance --address 0xYourAddress --chain sepolia

# 3. Sign and broadcast a transfer to a second address
python -m wallet_rpc.cli send \
  --private-key 0xYourPrivateKey \
  --to 0xRecipientAddress \
  --amount 0.001 \
  --chain sepolia
```

## Testing

```bash
pytest tests/ -v
```

The test suite runs entirely offline: `test_wallet.py` exercises real
local cryptographic operations (key generation, signing) with no network
dependency, and `test_rpc_client.py` mocks the `Web3` provider to verify
the client's own logic (unit conversion, transaction construction, receipt
parsing) without requiring a live RPC connection. This is also what runs
in CI (see `.github/workflows/tests.yml`).

To manually smoke-test against a **real** testnet connection, run the CLI
commands above directly with a valid `.env`.

## Design notes

**Why self-custody, specifically?** The distinction between self-custody
(user holds the key) and custodial (a third party holds it on the user's
behalf) is the central trust boundary in any crypto payments product.
`wallet.py` is written so the private key is created, used for signing,
and discarded — it's never logged, transmitted, or persisted anywhere by
this code.

**Why a real testnet instead of a full simulation?** A simulated chain can
model the shapes of the calls but not the actual failure modes: gas
estimation, PoA quirks on some chains, transaction confirmation timing,
nonce management. Hitting a real (if free/fake-value) network surfaces
those honestly.

**Why the chain config abstraction (`chains.py`)?** Real crypto-payments
infrastructure has to support many chains behind one integration. Keeping
chain-specific values (chain ID, native currency, POA middleware
requirement) in a small config object — rather than hardcoding
Ethereum-specific assumptions into the RPC client — is the minimum
structure needed to add a second or third chain without a rewrite.

**What this project deliberately does NOT do:** it doesn't build a
custodial wallet service, doesn't implement the fiat on/off-ramp or
stablecoin settlement side, and doesn't handle BIP-39 mnemonic-based key
derivation (raw private keys only, for simplicity). Those are natural
next steps — see below.

## Possible extensions

- BIP-39 mnemonic seed phrase generation/recovery instead of raw private
  keys (via `eth_account.hdaccount`)
- A minimal FastAPI wrapper exposing `/wallet/create` and
  `/wallet/{address}/balance` endpoints
- A stablecoin settlement layer that converts a confirmed on-chain USDC
  transfer into a simulated fiat payout record
- Support for a third chain to stress-test the `chains.py` abstraction

## Disclaimer

This project only ever uses testnet funds with no real-world value.
`export_private_key_HEX_DANGEROUS()` is named the way it is on purpose —
it exists for local demo/testing only. Never adapt this code path to
export, log, or transmit a private key holding real funds.

## License

MIT — see [LICENSE](LICENSE).
