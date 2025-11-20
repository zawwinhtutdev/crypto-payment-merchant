# Crypto Payments Platform

This is a demo crypto payment platform. Its features include:
1) Rest API interface with wallets, transfers, on-chain settlements
2) AuthN (JWT) and AuthZ (RBAC)
3) Encryption at rest and rate limiting
4) Double entry ledge, idenpotency, atomicity
5) Crypto settlement using simulated blockchain RPC,self-custody wallet, stablecoin settlement
6) In-memory pub/sub message queue.

## What's here

```
crypto-payments-platform/
├── services/
│   ├── payments-api/          # Core microservice (FastAPI)
│   │   ├── app/
│   │   │   ├── main.py            # REST API: wallets, transfers, on-chain settlement
│   │   │   ├── auth.py            # AuthN (JWT) + AuthZ (RBAC)
│   │   │   ├── security.py        # Encryption at rest + rate limiting
│   │   │   ├── ledger.py          # Double-entry ledger, idempotency, atomicity
│   │   │   ├── crypto_settlement.py  # Simulated blockchain RPC, self-custody wallet, stablecoin settlement
│   │   │   ├── message_queue.py   # In-memory pub/sub (stand-in for Azure Service Bus)
│   │   │   └── models.py          # Pydantic request/response schemas
│   │   ├── tests/                 # pytest suite
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── notification-service/  # Second microservice — async event consumer
│       └── consumer.py
├── infra/
│   ├── terraform/main.tf      # Azure AKS, ACR, Key Vault, Postgres (IaC)
│   ├── k8s/                   # Deployment, Service, HPA, NetworkPolicy
│   └── ci-cd/pipeline.yml     # Build -> test -> SAST/SCA/image scan -> deploy
└── docs/architecture.md       # System design trade-off discussion
```

## Running it

```bash
cd services/payments-api
pip install -r requirements.txt

# Run the API
uvicorn app.main:app --reload --port 8000

# Run the tests
pytest tests/ -v

# In a second terminal, run the notification-service consumer
cd services/notification-service
python consumer.py
```

### Example flow

```bash
# 1. Get a token
curl -X POST localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "alice_admin", "password": "admin-pass"}'

# 2. Create two wallets (use the returned access_token as Bearer)
curl -X POST localhost:8000/wallets \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"owner_id": "alice", "currency": "USD"}'

# 3. Fund a wallet (admin-only)
curl -X POST "localhost:8000/wallets/<wallet_id>/fund?amount=100" \
  -H "Authorization: Bearer <token>"

# 4. Transfer funds (idempotent — retry-safe)
curl -X POST localhost:8000/transfers \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"from_wallet": "<id>", "to_wallet": "<id>", "amount": 25, "currency": "USD", "idempotency_key": "order-42-attempt-1"}'
```

## Notes

- No real cryptography library is used for the AES-style cipher in
  `security.py` — it's a teaching-grade construction to avoid an external
  dependency in a sandboxed environment. **Do not use it in production** —
  use `cryptography`'s `AESGCM` and a real KMS-backed key instead.
- The in-memory ledger/wallet stores reset on process restart. A durable
  backing store (Postgres, per `infra/terraform/main.tf`) is the intended
  production replacement.
- This project is deliberately over-commented relative to normal production
  code — the comments are there to make the "why," not just the "what,"
  legible for interview prep.
