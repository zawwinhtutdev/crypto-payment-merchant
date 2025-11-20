# Architecture & Design Trade-offs

## Service boundary: why two services?

`payments-api` owns the ledger and the synchronous transfer flow — it's on
the critical path, so its latency and correctness bar are high.
`notification-service` is decoupled behind a message bus because notification
delivery is not on the critical path: a slow email provider should never
slow down (or fail) a money movement. This is the classic "synchronous core,
asynchronous periphery" split.

**Trade-off:** decoupling adds eventual-consistency risk (a notification
could theoretically be lost if the bus isn't durable) in exchange for not
coupling payment latency to a third-party's uptime. In production this bus
would be Azure Service Bus with at-least-once delivery + a dead-letter queue,
not the in-memory stand-in used here.

## Consistency model: why the ledger is NOT eventually consistent

Account balances use a single lock around check-then-act (`post_transfer`)
rather than optimistic concurrency or eventual consistency. For a ledger,
correctness (no double-spend, no lost update) matters more than raw
throughput — this is a deliberate CP choice (favoring Consistency over
Availability under partition, in CAP terms). A "likes counter" could tolerate
eventual consistency; a balance cannot.

**Trade-off:** a single lock is a throughput ceiling. At real scale you'd
shard the lock per-account (or per-account-group) so unrelated transfers
don't serialize against each other, and/or move to a database with
serializable transaction isolation (e.g. Postgres `SERIALIZABLE`) instead of
an in-process lock.

## Idempotency: why every transfer requires a client-supplied key

Network calls fail in ambiguous ways — a client can time out on a request
that actually succeeded server-side. Without an idempotency key, a naive
retry would double-process the transfer. `Ledger.post_transfer` treats the
`idempotency_key` as the source of truth for "have I seen this exact
instruction before?" and returns the original result on replay instead of
re-applying it. This mirrors how Stripe/most payment APIs are designed.

## AuthN/AuthZ split

`authenticate()` (credential check) is separate from `require_roles()`
(authorization on an already-verified identity). This separation matters
because in production `authenticate` would be swapped out for an external
IdP integration (Azure AD / SAML) without touching a single line of the
RBAC logic — the two concerns don't leak into each other.

## Crypto settlement: why it's a separate module from the ledger

`crypto_settlement.py` never touches the ledger's internal state directly —
it takes a completed ledger entry and bridges it to an on-chain action. This
mirrors Mesh's real problem: the off-chain ledger (who-owes-whom) and the
on-chain settlement (moving real stablecoin value) are two different systems
with different failure modes, and conflating them would make both harder to
reason about and test independently.

## What would change at real scale (~10k+ TPS)

- Ledger: move from a Python dict + lock to a horizontally-shardable store
  (Postgres with per-account partitioning, or an event-sourced ledger with a
  CQRS read model for balance queries).
- Message bus: swap the in-memory `InMemoryMessageBus` for Azure Service Bus
  / Event Hubs with proper partitioning and consumer groups.
- Rate limiting: move from per-process token buckets to a shared store
  (Redis) so limits hold across horizontally-scaled pod replicas — the
  current in-memory limiter only rate-limits per-pod, which is a real gap
  worth calling out in an interview.
- Auth: replace the local JWT issuer with Azure AD / an external IdP;
  services would validate tokens against a JWKS endpoint rather than a
  shared static secret.
