# Crypto Payments Demo

A demo project that shows how a crypto payment platform moves value between
wallets, split into two self-contained subprojects.

## 1. Crypto Payments Platform

The main demo service, built from the pieces you would expect from a
production-grade application:

- REST API for wallets, transfers and on-chain settlements
- AuthN (JWT) and AuthZ (RBAC)
- Encryption at rest and rate limiting
- Double-entry ledger with idempotency and atomicity
- Crypto settlement over a simulated blockchain RPC, self-custody wallet and
  stablecoin flow
- In-memory pub/sub message queue

## 2. Self-Custody Wallet + Multi-Chain RPC Client

A focused client for the wallet side: local key generation, a JSON-RPC
transport for reading chain state, and signed transaction broadcast.

## Repository layout

| Path | What it is |
| --- | --- |
| [`crypto-payments-platform/`](crypto-payments-platform/README.md) | Payments API, notification consumer, Terraform/K8s/CI |
| [`self-custody-wallet-rpc/`](self-custody-wallet-rpc/README.md) | Wallet library, RPC client and CLI |

Setup, endpoints and example requests live in each subproject's README.
