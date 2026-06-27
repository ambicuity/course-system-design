# Design a Payment System

A payment system moves money between parties reliably. Unlike most systems where a dropped event is an annoyance, here a duplicated or lost event is *real money* gained or lost. The design is therefore dominated by one obsession: **correctness under failure**. Throughput matters, but exactly-once semantics, auditability, and consistency matter more.

---

## Step 1 — Understand the Problem and Scope

### What the system does

At the highest level a payment system supports two flows:

- **Pay-in**: money flows *into* the platform. A buyer pays a merchant (e.g., placing an order on an e-commerce site). The platform collects the money via a Payment Service Provider (PSP).
- **Pay-out**: money flows *out* of the platform to a recipient (e.g., paying a seller, driver, or contractor). Often this is a marketplace settling balances.

This chapter focuses primarily on the **pay-in** flow for an e-commerce checkout, then generalizes.

### Functional requirements

- Accept payment for an order and credit the merchant after success.
- Integrate with one or more PSPs (Stripe, Adyen, Braintree) so we never store raw card numbers ourselves.
- Maintain an internal **ledger** that records every money movement for accounting.
- Maintain a **wallet** (account balance) per merchant/user.
- Support **reconciliation** between our internal records and the PSP's records.
- Handle failures: retries, timeouts, partial failures, and refunds.

### Non-functional requirements

- **Correctness / exactly-once**: a single user action results in exactly one charge. No double-charging, no lost payments.
- **Durability**: once we acknowledge a payment, it is never lost.
- **Auditability**: every state change is traceable and immutable. Regulators and accountants must be able to reconstruct history.
- **Availability**: ~99.99%. Checkout downtime is lost revenue.
- **Consistency over availability** for money movement — we prefer to reject/retry than to corrupt balances.
- **Security & compliance**: PCI DSS. Never store PAN/CVV; delegate to PSP via tokenization.

### Back-of-the-envelope estimation

- Assume 1 million transactions/day.
- 1,000,000 / 86,400 ≈ **~12 TPS average**, peak maybe 10× → **~120 TPS**.

This is *low* throughput by web standards. **Payment systems are not throughput-bound; they are correctness-bound.** A single node database can handle the write volume. The hard part is never losing or duplicating a transaction, and that's where the engineering goes.

---

## Step 2 — High-Level Design

### Components

```
                ┌────────────┐
   User ──────► │  Payment   │
                │   Gateway  │ (API edge, auth, validation)
                └─────┬──────┘
                      │
                ┌─────▼──────┐      ┌──────────────┐
                │  Payment   │◄────►│   PSP (e.g.  │
                │  Service   │      │   Stripe)    │
                └─────┬──────┘      └──────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
   ┌────▼────┐   ┌────▼────┐   ┌────▼─────┐
   │ Ledger  │   │ Wallet  │   │ Payment  │
   │ Service │   │ Service │   │   DB     │
   └─────────┘   └─────────┘   └──────────┘
```

1. **Payment Service** — receives payment events, validates them, applies risk checks (AML, fraud), and orchestrates the rest. The brain.
2. **PSP integration** — talks to Stripe/Adyen. Handles the actual card authorization & capture. We store only PSP **tokens**, never card data.
3. **Ledger** — append-only, double-entry record of every money movement. Source of truth for accounting.
4. **Wallet** — per-account balance. Updated as a consequence of ledger entries.
5. **Payment DB** — stores payment orders and their status.

### The pay-in flow (happy path)

1. User clicks "Pay". The order service creates a **payment event** containing buyer, seller, amount, currency, and a unique order/payment ID.
2. Payment Service persists a `payment_order` row in state `NOT_STARTED` and generates/forwards an **idempotency key**.
3. Payment Service calls the PSP to create a charge, passing the idempotency key and a return URL.
4. PSP (with hosted fields / 3-D Secure) collects card details directly from the user's browser, authorizes, and captures.
5. PSP calls back asynchronously via **webhook** with the result (success/failure).
6. On success: Payment Service updates the payment order to `SUCCESS`, writes **double-entry ledger** records, and updates the **wallet** balance.
7. Order service is notified; order is fulfilled.

### Why a hosted PSP instead of touching cards ourselves

Handling raw card numbers drags you into full **PCI DSS Level 1** scope — expensive audits, network segmentation, encryption-at-rest of PANs. Using a PSP with **client-side tokenization** (Stripe Elements, hosted payment pages) keeps card data off our servers entirely. We receive a token; the PSP holds the sensitive data.

---

## Step 3 — Deep Dive

### Double-entry bookkeeping (the ledger)

The ledger is the accounting backbone. The rule: **every transaction touches at least two accounts, and the sum of debits equals the sum of credits.** Balance is never edited in place — you append balancing entries.

Example: buyer pays merchant $100.

| Account              | Debit | Credit |
|----------------------|-------|--------|
| Buyer (cash in)      | $100  |        |
| Merchant payable     |       | $100   |

Sum of debits ($100) = sum of credits ($100). This **self-checking invariant** means a corrupted ledger is detectable: if debits ≠ credits, something is wrong. It also gives a complete audit trail — you can replay entries to recompute any balance at any point in time.

Properties to enforce:

- **Append-only / immutable.** Never UPDATE or DELETE a ledger row. Corrections are *reversing entries*, not edits.
- **Monetary precision.** Store money as integer minor units (cents) or fixed-point `DECIMAL`. Never floats.
- **Currency-aware.** Each entry carries a currency; cross-currency moves go through an FX account.

### Wallet vs Ledger

- The **ledger** is the immutable journal of movements (the "what happened").
- The **wallet/account** holds the current **balance** (the "where we are now").
- The balance can always be *recomputed* by summing ledger entries. The wallet is effectively a materialized view kept for fast reads. When in doubt, the ledger wins.

### Idempotency — the heart of exactly-once

Networks fail. A client may retry. A PSP webhook may be delivered more than once (most webhook systems guarantee *at-least-once* delivery). Without protection, retries double-charge.

**Idempotency key**: a unique ID attached to a logical operation. The first request with key `K` performs the work and records the result keyed by `K`. Any later request with the same `K` returns the *stored* result without re-executing.

- Generate the key on the client (or order service) — e.g., a UUID per checkout attempt — so a retry of the *same* attempt reuses it.
- Store `(idempotency_key, request_hash, response, status)` in a table with a **unique constraint** on the key.
- On insert conflict, return the prior response.
- Stripe's own API takes an `Idempotency-Key` header for exactly this reason — propagate yours through to it.

Database-level enforcement is what makes this robust: a `UNIQUE` index on the idempotency key means even a race between two concurrent retries can only insert once; the loser gets a conflict and reads the winner's result.

### Exactly-once = at-least-once delivery + idempotent processing

There is no magic "exactly-once" over an unreliable network. The practical recipe:

1. **At-least-once delivery** — keep retrying until acknowledged (so nothing is lost).
2. **Idempotent receivers** — de-duplicate using the idempotency key (so nothing is doubled).

Together they yield exactly-once *effect*.

### Retries, backoff, and the Dead Letter Queue

When a PSP call or downstream step fails transiently:

- **Retry with exponential backoff + jitter** to avoid thundering herds. E.g., 1s, 2s, 4s, 8s … with random jitter.
- Distinguish **retryable** (timeout, 5xx, network) from **non-retryable** (declined card, 4xx validation) errors. Never blindly retry a hard decline.
- Cap retries. After N failures, route the message to a **Dead Letter Queue (DLQ)** for manual/automated investigation instead of looping forever.
- All retries must carry the **same idempotency key** so they don't multiply charges.

A DLQ keeps the main pipeline healthy: poison messages get parked rather than blocking everything behind them, and on-call engineers can inspect, fix, and replay them.

### Handling PSP communication: synchronous vs webhook

A charge can take seconds and the connection might drop *after* the PSP processed it but *before* we got the response. Two complementary mechanisms close the gap:

1. **Webhooks** — the PSP pushes the authoritative outcome asynchronously. Treat webhooks as the source of truth for final state.
2. **Polling / reconciliation** — if a webhook is missed, periodically query the PSP for the status of pending payments using our reference ID.

Always verify webhook **signatures** and treat webhook handlers as idempotent (the same event may arrive twice).

### Reconciliation

Even with idempotency, our records and the PSP's can diverge: missed webhooks, partial failures, timing skews, fees, FX rounding.

**Reconciliation** is a scheduled (typically daily) batch job that compares the PSP's **settlement file / report** against our internal ledger:

- **Matched**: amounts agree — no action.
- **Classifiable mismatch**: e.g., known PSP fee — auto-adjust with a ledger entry.
- **Unclassifiable mismatch**: flag for manual review / finance ops.

Reconciliation is the safety net that catches whatever idempotency and retries missed. It is non-negotiable in any real payment system.

### Consistency across services

Money movement spans multiple stores (payment DB, ledger, wallet). Options:

- **Single database transaction** when ledger + wallet live in the same RDBMS — simplest and strongly consistent. Given the low TPS, this is often the right call.
- **Saga / orchestration** when services are separate: a coordinator drives steps with **compensating transactions** to undo on failure (e.g., reverse a ledger entry). Eventual consistency, but every step is idempotent and recoverable.
- **Transactional outbox**: write the business change and an "event to publish" in the *same* DB transaction; a relay reads the outbox and publishes to the message queue. This avoids the dual-write problem (DB committed but event lost, or vice versa).

### Handling failures — a checklist

| Failure | Mitigation |
|---------|------------|
| Client retries / double submit | Idempotency key + unique constraint |
| Webhook delivered twice | Idempotent webhook handler, dedupe on event ID |
| Webhook never delivered | Polling/reconciliation fallback |
| PSP call times out (unknown outcome) | Query status by reference ID before retrying; same idempotency key |
| Downstream (ledger/wallet) write fails | Outbox + retry; saga compensation |
| Poison message | Dead Letter Queue + alerting |
| Records drift from PSP | Daily reconciliation |
| Hard decline | Mark failed, notify user — do NOT retry |

### Security and compliance

- **PCI DSS**: keep card data out of scope via tokenization/hosted fields.
- **Encrypt** sensitive data at rest and in transit (TLS everywhere).
- **Least privilege & audit logs** on the ledger and admin actions.
- **Idempotency + signed webhooks** also defend against replay attacks.
- **AML / fraud / risk checks** before completing high-risk payments.

---

## Step 4 — Wrap Up

### Key takeaways

- A payment system is **correctness-first, throughput-second**. ~120 TPS is trivial; never double-charging is hard.
- The **double-entry ledger** is the immutable, self-checking source of truth; the **wallet** is a fast-read balance derived from it.
- **Exactly-once = at-least-once delivery + idempotent processing.** Enforce idempotency at the database with a unique key.
- **Retries** need exponential backoff, jitter, retryable/non-retryable classification, and a **Dead Letter Queue** as the escape hatch.
- **Webhooks** give the authoritative PSP outcome; **polling + daily reconciliation** catch what webhooks miss.
- Solve the dual-write problem with a **transactional outbox** or **saga** with compensating transactions.
- Tokenize cards through a **PSP** to stay out of heavy PCI scope.

### If asked to scale further

- Shard the ledger/wallet by account ID once a single RDBMS is saturated; keep each money movement within one shard where possible.
- Multi-PSP routing for redundancy, cost, and regional coverage; abstract behind a common interface.
- Move toward **event sourcing** (see the digital wallet chapter) for full reproducibility and audit at very high scale.
- Separate hot read paths (balance lookups) from write paths with CQRS.
