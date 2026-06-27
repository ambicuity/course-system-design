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

---

## Back-of-the-Envelope Math (Extended)

### Throughput math, done honestly

| Scenario | Daily transactions | Avg TPS | Peak (10×) TPS | Peak (50×) TPS |
|----------|--------------------|---------|----------------|----------------|
| Small e-commerce | 10,000 | 0.12 | 1.2 | 6 |
| Mid-size SaaS billing | 1,000,000 | 12 | 120 | 600 |
| Marketplace (Uber / DoorDash scale) | 10,000,000 | 116 | 1,160 | 5,800 |
| PSP itself (Stripe public scale) | ~hundreds of millions | ~thousands | ~tens of thousands | ~hundreds of thousands |

The "peak factor" is not a fixed constant. It depends on the daily curve:

- **Consumer e-commerce** peaks during lunch and evening; 5–10× average is realistic.
- **B2B billing** is concentrated on the 1st and 15th of the month; peak vs average can exceed 50× on those days.
- **Marketplaces** (rideshare, food delivery) peak during commute and meal hours; lunch + dinner dinner rush + Friday evening ≈ 10–20× average.
- **Real-time gaming** is the most extreme — 100× peaks during tournaments.

Plan capacity for the **peak** number, not the average. The 10× rule is a starting point, not a ceiling.

### Storage math

For 1M transactions/day with double-entry bookkeeping:

- Each transaction: 2 ledger rows, ~120 bytes each.
- Daily ledger volume: 1M × 2 × 120 = 240 MB/day.
- Annual ledger volume: ~88 GB/year. Small.
- With indexes and audit metadata: ~3–5× that. ~300–500 GB/year.
- 7-year retention (regulatory): ~2.5 TB. Two orders of magnitude bigger, but still fits on a single $200/month general-purpose database.

The bigger storage cost is **cold-path** — event logs, webhooks, and PSP API call records. Budget 5–10× the ledger size for the audit trail and reconcile buffer.

### Latency math, broken down

A synchronous checkout path: client → edge → payment service → PSP API → PSP processing → PSP response → us → client. Latency budget at the 95th percentile:

| Stage | P95 budget | Notes |
|-------|-----------|-------|
| TLS + edge auth | 30 ms | CDN-fronted; geographically close |
| Payment service auth + idempotency lookup | 10 ms | In-memory cache hit |
| PSP API call (network RTT) | 50 ms | Single region, premium peering |
| PSP processing (auth + 3DS) | 1,500 ms | 3-D Secure adds 800–1,500 ms; without 3DS, 200–500 ms |
| PSP response + ledger write | 50 ms | Single DB transaction |
| Response to client | 30 ms | Edge response |
| **Total** | **~1.7 s** | With 3DS |

Without 3DS (e.g., low-risk repeat customer): **~370 ms**. The 3DS step is the dominant cost. Some PSPs offer 3DS in a non-blocking flow that the user may complete asynchronously, allowing the charge to proceed under "liability shift" with deferred 3DS — but this requires careful handling of the failure mode where 3DS is later denied.

### Money-precision math

A subtle bug source: `0.1 + 0.2 != 0.3` in IEEE 754 floats.

```python
>>> 0.1 + 0.2
0.30000000000000004
```

If you store money as `float` and compute tax, fee, or split-pay math, you will accumulate rounding error. Worse, some errors *favor the customer* (you charge $9.99 instead of $10.00) and over a year, that's real money lost.

The fix is universal in financial systems: store money as **integer minor units** (cents for USD, fen for CNY) or fixed-point `DECIMAL(19, 4)`. Example schema:

```sql
CREATE TABLE ledger_entry (
  id BIGSERIAL PRIMARY KEY,
  account_id BIGINT NOT NULL,
  currency CHAR(3) NOT NULL,           -- 'USD', 'EUR', 'JPY'
  amount_minor BIGINT NOT NULL,        -- 100 = $1.00; 1 = $0.01
  direction CHAR(1) NOT NULL,          -- 'D' (debit) or 'C' (credit)
  txn_id BIGINT NOT NULL REFERENCES transaction(id),
  posted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Sum-of-debits-equals-sum-of-credits is then integer arithmetic — exact, fast, and audit-friendly. For currencies that don't have minor units (JPY, KRW), the "minor unit" is just the whole unit; the field still works.

---

## ASCII Architecture Diagrams

### Diagram 1 — Pay-in flow with idempotency, webhook, and reconciliation

```
  User          Order           Payment          PSP            Idempotency       Ledger        Wallet
   │           Service         Service          (Stripe)         Store            Service       Service
   │              │               │                │                │               │              │
   │  checkout    │               │                │                │               │              │
   │─────────────►│               │                │                │               │              │
   │              │  POST /payments               │                │               │              │
   │              │  {order_id, amount,           │                │               │              │
   │              │   idem_key=UUID}              │                │               │              │
   │              │──────────────────────────────►│                │               │              │
   │              │               │  INSERT idem_key, status=NEW  │               │              │
   │              │               │────────────────────────────────►│              │              │
   │              │               │  200 OK {payment_id}          │               │              │
   │              │               │◄───────────────────────────────│               │              │
   │              │               │                │                │               │              │
   │              │               │  POST /charges                │               │              │
   │              │               │  {idem_key, amount, token}    │               │              │
   │              │               │──────────────────────────────►│               │              │
   │              │               │                │  auth+capture │               │              │
   │              │               │                │  (3DS)        │               │              │
   │              │               │  200 charge_id                │               │              │
   │              │               │◄─────────────────────────────│               │              │
   │              │               │                │                │               │              │
   │              │  awaiting PSP │                │                │               │              │
   │              │  webhook      │                │                │               │              │
   │              │               │                │                │               │              │
   │              │               │  webhook: charge.succeeded    │               │              │
   │              │               │  (signed by PSP)              │               │              │
   │              │               │◄─────────────────────────────│               │              │
   │              │               │                │                │               │              │
   │              │               │  verify signature + lookup idem_key             │              │
   │              │               │  if NEW: process; if DONE: return prior result │              │
   │              │               │                │                │               │              │
   │              │               │  in single DB tx:              │               │              │
   │              │               │    update idem_key -> DONE     │               │              │
   │              │               │    insert 2 ledger rows        │               │              │
   │              │               │    update wallet balance       │               │              │
   │              │               │───────────────────────────────────────────────►│              │
   │              │               │──────────────────────────────────────────────────────────────►│
   │              │               │                │                │               │              │
   │              │  notify: paid  │                │                │               │              │
   │              │◄──────────────│                │                │               │              │
   │              │               │                │                │               │              │
   │  "Paid!"     │               │                │                │               │              │
   │◄─────────────│               │                │                │               │              │
```

Note the **idempotency store is the linchpin**: every state transition checks it. The same webhook arriving twice → same result, no double-charge. The same client retry → same response, no second PSP call.

### Diagram 2 — Ledger (double-entry) write anatomy

```
  payment_succeeded event
        │
        ▼
  ┌──────────────────────────────────────────────────────┐
  │ single DB transaction (PostgreSQL: SERIALIZABLE)     │
  │                                                      │
  │  1. INSERT ledger_entry                              │
  │     (account=cash_pool, direction=D, amount=10000)   │  ← $100.00 debit
  │                                                      │
  │  2. INSERT ledger_entry                              │
  │     (account=merchant:42, direction=C, amount=10000) │  ← $100.00 credit
  │                                                      │
  │  3. UPDATE wallet SET balance=balance+10000          │
  │     WHERE user_id=42                                  │
  │                                                      │
  │  4. UPDATE payment_order SET status='SUCCESS'        │
  │                                                      │
  │  5. INSERT outbox(event='order.paid', payload)       │
  │                                                      │
  │  COMMIT                                              │
  └──────────────────────────────────────────────────────┘
        │
        ▼
  INVARIANT CHECK: SUM(debits) == SUM(credits) for the txn
        │
        ▼
  Outbox relay → Kafka → notification service → email/SMS
```

The single-transaction write gives atomicity across ledger + wallet + status + outbox. SERIALIZABLE isolation prevents two concurrent payments from racing on the same wallet. The outbox is a row in the *same* transaction, so a successful commit guarantees the event will eventually be published (the relay polls the outbox).

### Diagram 3 — Refund flow (compensating entry, not a delete)

```
  Original txn (Feb 1):
    DR cash_pool         $100
       CR merchant:42       $100

  Refund (Feb 5) — generates REVERSING entries, never deletes:
    DR merchant:42      $100       (merchant's payable goes back down)
       CR refunds_outstanding $100  (cash to be returned to buyer)

  Refund settlement (Feb 6):
    DR refunds_outstanding $100
       CR buyer_payment_method $100  (actual money movement via PSP refund)
```

The original Feb 1 entries are still there. Three new rows are appended Feb 5–6. The audit trail is complete: any auditor can replay all entries and reconstruct the merchant's balance at any point in time, including "what was their balance the day before the refund was issued?"

### Diagram 4 — Daily reconciliation pipeline

```
  PSP Settlement File (SFTP, daily 02:00 UTC)
        │
        │  (delayed: 12-48h after transaction day)
        ▼
  ┌─────────────────┐     ┌──────────────────┐
  │  Ingestion      │     │  Internal Ledger │
  │  service        │     │  (yesterday's    │
  │  parses PSP     │     │   entries)       │
  │  CSV/JSON       │     └────────┬─────────┘
  └────────┬────────┘              │
           │                       │
           ▼                       ▼
  ┌──────────────────────────────────────────────┐
  │ Reconciler: per transaction, match on:        │
  │   (psp_txn_id, amount, currency, fee, net)    │
  └──────────────────┬───────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
    MATCHED      KNOWN_FEE     UNKNOWN
    (no-op)     (auto-         (alert +
                adjust          ops queue)
                ledger)
```

Reconciliation is the safety net that catches everything idempotency and retries missed. The "known fee" path is fully automated; the "unknown" path is the queue finance ops actually look at every morning. In a healthy system, the unknown rate should be < 0.01% of transactions.

---

## Trade-off Tables

### PSP integration model

| Approach | PCI scope | Engineering effort | Latency | Cost per txn | When to use |
|----------|-----------|--------------------|---------|--------------|-------------|
| Full card storage, self-process | PCI DSS Level 1 | High (audits, network seg.) | Lowest | ~$0.05 + interchange | Avoid; legacy banks |
| PSP with redirect (hosted page) | Level 1 (PSP) | Low | Highest (full page reload) | ~$0.30 + % | Legacy UX acceptable |
| PSP with client tokenization (Stripe Elements) | Level 1 (PSP), Level 2 or 3 (you) | Medium | Low (in-page iframe) | ~$0.30 + % | Default modern choice |
| PSP with server-to-server (no card UI) | Level 1 (PSP), you handle tokens | High | Lowest (no client step) | ~$0.30 + % | Subscription / saved cards |
| Direct card-network API (Visa Token Service, Mastercard MDES) | Reduced scope | Very high | Low | Interchange + ~$0.10 | Wallets, large issuers |

### Idempotency scope

| Scope | Replay protection | Trade-off |
|-------|-------------------|-----------|
| Per HTTP request | High (same client retry returns same response) | Doesn't help if a *new* request is sent for the same logical action |
| Per logical operation (order_id) | Higher (any new HTTP request for the same order returns the stored result) | Requires client to send the logical ID, not just the retry key |
| Per money movement (transaction_id) | Highest (each unique money movement has a key; impossible to double-apply) | Most complex; you have to model "transaction" as a first-class entity |

### Strong vs eventual consistency across services

| Option | Consistency | Throughput | Complexity | When to pick |
|--------|-------------|-----------|-----------|--------------|
| Single RDBMS, ACID transaction | Strong | Low (~10k TPS) | Low | Default for < 10k TPS |
| Saga with compensation | Eventual | High | High | Microservices, cross-store |
| Event sourcing + CQRS | Eventual, with read-your-writes | Very high | Highest | Auditing, very high scale |
| Two-phase commit (XA) | Strong | Low | High | Legacy systems, existing XA infrastructure |
| Outbox + relay | Eventual | High | Medium | Decoupling services without 2PC |

### Storage of ledger

| Option | Pros | Cons | When |
|--------|------|------|------|
| Single Postgres with `DECIMAL` | Simple, ACID, mature | Single-writer bottleneck | < 10k TPS, all money in one region |
| Postgres + read replicas | Read scale | Replication lag on reads; writes still single node | Mixed read/write, geo-distributed reads |
| Sharded Postgres (Citus) | Write scale | Cross-shard transactions hard | Sharding by account_id works |
| Event-sourced (Kafka + projector) | Extreme audit, infinite replay | Complexity, eventual consistency | Strict regulatory, very high TPS |
| Purpose-built (e.g., Stripe's internal ledger) | Tuned to payment semantics | Vendor lock-in, ops burden | Hyperscale, deep domain |

### Refund / chargeback handling

| Mechanism | When | Money flow | Time |
|-----------|------|-------------|------|
| Refund (merchant-initiated) | Buyer returns goods / cancels | PSP refunds cardholder; merchant balance debited | Days to weeks (depends on issuer) |
| Chargeback (cardholder-initiated) | Buyer disputes with their bank | Funds withdrawn from merchant immediately, held in escrow | 60–90 day dispute window |
| Reversal (PSP-initiated) | Fraud detected after the fact | Funds forcibly pulled back; merchant learns via webhook | Hours to days |
| Adjustment (manual ledger entry) | Internal error, goodwill credit | Ledger-only, no card movement | Same day |

### Retry strategy

| Setting | Aggressive | Conservative |
|---------|-----------|--------------|
| Backoff base | 100 ms | 1 s |
| Backoff factor | 2× | 3× |
| Max retries | 10 | 3 |
| Jitter | 100% (full randomization) | 25% (mild randomization) |
| DLQ threshold | 5 | 3 |
| Idempotency scope | Per HTTP request | Per money movement |
| Cost | Higher retry storm risk | Slower recovery from transient PSP outages |

---

## Real-World Case Studies

### Stripe — idempotency keys as a first-class API feature

Stripe was one of the first payment APIs to expose idempotency as a public primitive. Their API:

- Accepts an `Idempotency-Key: <UUID>` header on `POST` endpoints (charges, refunds, payouts).
- The first request with key K performs the work; the response is stored for 24 hours.
- Any subsequent request with the same K (matching the body hash) returns the **stored response** with a 200 status, *not* a duplicate 4xx.
- If the body doesn't match the stored request, Stripe returns a 400 — the same key was used for a different operation, which is a client bug.
- Internally, Stripe uses a PostgreSQL-backed idempotency store. The key is the primary key; race conditions are resolved by the unique constraint at insert time.

Stripe also publishes extensive design notes on **exactly-once** semantics. Their public position: there is no real exactly-once over the network; the practical pattern is at-least-once with idempotency, which they document as the standard.

### PayPal — IPN, webhooks, and the early lessons

PayPal's **Instant Payment Notification (IPN)** was one of the first widely-deployed webhook systems. It is also a case study in the failure modes of webhooks:

- **At-least-once delivery** by design. Merchants received the same IPN multiple times if their server was slow to respond 200 OK.
- **Replay protection** had to be implemented by the merchant (de-dupe on `txn_id`).
- PayPal added **retries with exponential backoff** for non-200 responses, but no upper bound on total attempts (merchants got IPN days after the original event for very long outages).

Modern webhook best practices — idempotent handlers, signature verification, bounded retry windows, and dead-letter queues — are largely lessons learned from IPN-era integrations.

### Square (Block) — Bitcoin, Cash App, and ledger-first design

Block (formerly Square) processes payments for millions of small merchants. Their public engineering talks describe:

- A **central ledger** that records every money movement as an immutable journal.
- The **Cash App balance** as a derived wallet, with the ledger as the source of truth.
- The same ledger service backs **Square seller payments**, **Cash App peer-to-peer transfers**, and (formerly) **Bitcoin buys/sells** — a single accounting backbone for many product surfaces.
- **Reconciliation against the bank** happens daily. Square was one of the first to publish metrics on "ledger accuracy" (mismatches per million transactions) as a top-level reliability metric.

The pattern: a single ledger service, product-specific wallets, idempotent PSP integrations, daily bank reconciliation. A textbook application of the chapter's design.

### Adyen — single platform, multiple PSPs

Adyen operates as both a **payment processor** (it talks directly to card networks) and an **aggregator** (it offers Stripe-like unified APIs). Notable design choices:

- A **single integration** for the merchant, but **multi-acquirer routing** under the hood. If a transaction fails on one acquirer (e.g., Chase), Adyen retries on another (e.g., Worldpay) automatically, with the same merchant-visible order ID.
- **Dynamic risk scoring** per transaction, including network-token usage where the issuer supports it.
- **Real-time dashboards** showing per-acquirer decline rates — exposing the kind of operational visibility that justifies a multi-PSP design.

Adyen's lesson: even at single-merchant scale, multi-PSP isn't just redundancy; it's also **cost optimization** (different PSPs have different fee schedules per card type / region / volume) and **regional coverage** (some PSPs don't accept certain cross-border cards).

### Visa / Mastercard rails

A real PSP sits on top of a card-network **acquirer**. The flow:

1. **Card network authorization**: PSP → acquirer → card network → issuer. Real-time, ~200 ms. Returns approve/decline + auth code.
2. **Capture**: PSP explicitly captures the authorized amount later (or it auto-captures at auth time). Some businesses authorize on order, capture on shipment — to avoid capturing a payment for an order that was never fulfilled.
3. **Clearing**: the day's transactions are batched and exchanged between acquirers. Happens overnight in the US; near-real-time in some regions (Visa Direct, Mastercard Send).
4. **Settlement**: the acquirer wires the net amount to the merchant's bank account. T+1 to T+3 in the US.

PSP APIs abstract all of this. The merchant sees `charge.succeeded`; the PSP handles the rest. But if you're a PSP, this is the depth you operate at.

### ACH and SEPA

For non-card payments, the rails are different:

- **ACH (US)**: bank-to-bank transfers, batched and processed by the Federal Reserve / Nacha. Settlement T+1 to T+2. Much cheaper than cards (a few cents vs ~2.9% + 30¢). Slow and high-failure-rate (1–3% returns for invalid account numbers).
- **SEPA (EU)**: similar to ACH but pan-European. SEPA Credit Transfer (SCT) settles same-day; SEPA Instant settles in < 10 seconds (with a 100k EUR cap in 2024, raised to 1M in 2025+).
- **Wire transfers**: real-time, expensive, used for high-value or international transfers.

PSP APIs (Stripe, Adyen, Braintree) wrap ACH/SEPA the same way they wrap cards. The merchant sees `charge.pending` → `charge.succeeded`; the PSP handles the bank integration, retry logic for returns, and micro-deposit verification.

### Braintree — gateway with multi-acquirer history

Braintree (acquired by PayPal) is notable for **multi-acquirer routing** at the gateway level. A merchant using Braintree can:

- Configure a **primary acquirer** (e.g., Chase) and a **fallback** (e.g., First Data).
- Braintree routes a transaction to the primary; if the primary declines for a non-permanent reason, Braintree transparently retries on the fallback with the same merchant order ID.
- The merchant sees a single `transaction_id`; the routing is internal.

The lesson: idempotency keys need to be **propagated across acquirers** if you have multiple, otherwise the fallback becomes a "new transaction" rather than a retry.

### PCI-DSS and the scope gradient

PCI DSS has four levels based on transaction volume:

- **Level 1**: > 6M transactions/year. Full on-site audit by a QSA (Qualified Security Assessor), quarterly network scans, penetration test, formal compliance report.
- **Level 2**: 1–6M transactions/year. Annual self-assessment, quarterly scans.
- **Level 3**: 20k–1M e-commerce transactions/year. Annual self-assessment.
- **Level 4**: < 20k e-commerce or < 1M total. Annual self-assessment, lighter requirements.

The **scope of compliance** depends on what systems touch card data. If you use Stripe Elements, the iframe is served by Stripe; your servers only see a token. Your PCI scope is dramatically reduced (potentially SAQ A, the lightest self-assessment). If you POST the raw PAN to your own server, you're Level 1, full audit, ~$100k/year in compliance overhead.

The interview-grade answer: "Use a PSP with client-side tokenization to drop to SAQ A scope; this is the default for any new system."

### Chargeback flows in practice

A chargeback is a **cardholder-initiated dispute**. The flow:

1. Cardholder calls their bank, disputes a charge.
2. The card network notifies the merchant's acquirer; the acquirer pulls the funds from the merchant immediately.
3. The merchant's PSP receives a `charge.dispute.created` webhook.
4. The merchant submits evidence (receipts, shipping, communication logs).
5. The issuer reviews and either reverses the chargeback (merchant wins) or upholds it (merchant loses the funds + a $15–25 fee).

Important: **funds are debited from the merchant immediately**, not at dispute resolution. A merchant with high chargeback rates can be put in a **monitoring program** by the card networks (Visa VAMP, Mastercard MCFP) and lose the ability to process cards entirely if rates stay high.

Engineering implications: dispute webhooks are first-class events. They must update the ledger (debit merchant, credit dispute-outstanding), notify the merchant's ops team, and track evidence submission deadlines (usually 7–14 days).

---

## Common Pitfalls & Failure Modes

### Pitfall 1 — "We use retries, so we're safe"

A naive retry without an idempotency key will **multiply charges**. A 3× retry multiplier on a $100 charge during a 10-minute PSP outage is $3M in duplicate charges for a $1M/day business. The fix: **idempotency key on every PSP call, and that key must be generated at the level of the user action, not the HTTP request.** A retry of the same user action reuses the key; a *new* user action (same user, different cart) gets a new key.

### Pitfall 2 — Trusting "succeeded" before the ledger is written

A subtle bug: the PSP says `charge.succeeded`, your code sends "thanks!" to the customer, but the ledger write fails (DB down). The customer thinks they paid; the merchant has no record; reconciliation finds the gap days later. The fix: **the user-visible "payment complete" must be sent only after the ledger commit succeeds.** Make this a strict ordering in your state machine, not a coincidence of code structure.

### Pitfall 3 — "The webhook didn't fire, so the charge didn't happen"

A common on-call scenario: customer says "I paid but my order isn't placed." The team checks PSP dashboard, sees the charge succeeded, reprocesses — and now the customer is double-charged.

The correct flow:

1. **Never trust the absence of a webhook** as evidence of failure. Webhooks can be lost.
2. **Query the PSP for the status** using the order ID before reprocessing. The PSP returns the definitive state.
3. **If the PSP says the charge succeeded**, locate the original payment_order and re-drive the downstream side effects (ledger, wallet, notification). Use the same idempotency key.
4. **Only create a new charge** if the PSP confirms there is no record.

This is a 2-minute process; double-charging is a customer-trust event.

### Pitfall 4 — Float, fees, and currency rounding

A $100 sale might net you $97.20 (after interchange ~1.5% + 30¢ + assessment ~0.15%). The ledger must record the **gross** ($100 to merchant payable), the **PSP fees** ($2.80 debit to fees expense), and the **net** ($97.20 to merchant bank). If you conflate gross and net in the ledger, your reconciliation will be off by thousands of dollars in fees over a month.

Cross-currency is worse: a €100 sale at 1.08 EUR/USD converts to $108.00 gross, but the FX provider charges a spread, so the merchant receives $107.85. The 15¢ difference is real money and a reconciliation line item.

### Pitfall 5 — Race conditions on balance updates

Two concurrent transfers from the same wallet can race:

```
T0: SELECT balance FROM wallet WHERE user_id = 'A'   →  $100
T1: SELECT balance FROM wallet WHERE user_id = 'A'   →  $100  (concurrent)
T2: UPDATE wallet SET balance = 100 - 60 WHERE ...   →  $40
T3: UPDATE wallet SET balance = 100 - 50 WHERE ...   →  $50  (lost update!)
```

The fix is one of:

- **Single UPDATE with arithmetic** in a transaction with row-level lock: `UPDATE wallet SET balance = balance - 60 WHERE user_id = 'A' AND balance >= 60`. The DB serializes the writes; the second sees the post-first state.
- **SERIALIZABLE isolation** with retry on serialization failure.
- **Optimistic concurrency** with a `version` column: increment on update, retry if version mismatch.

Most payment systems use the first approach — the conditional update is both correct and easy to reason about.

### Pitfall 6 — Hard-decline retry storms

A "card declined" response is **not retryable**. Retrying it will fail again, potentially getting the card flagged for fraud by the issuer. Distinguish:

- **Soft decline** (insufficient funds, try again later): retryable after a delay.
- **Hard decline** (stolen card, do not honor): permanent, do not retry.
- **Network error / timeout**: unknown outcome, query the PSP for status before retrying.

Classify at the PSP response level and never blindly retry.

### Pitfall 7 — Clock skew breaking the ledger

If two services stamp ledger entries with `now()` from their local clocks, and those clocks drift, the audit trail's ordering is unreliable. A two-month-old transaction may appear to post before a same-day one. The fix: **use a single source of truth for timestamps** — either a single DB's `now()`, or — at scale — a logical clock (sequence number from a sequencer) instead of wall-clock time.

### Pitfall 8 — "Refunds are just negative charges"

Refunds are **not** negative charges. They are a separate money movement with a separate PSP call, a separate set of ledger entries (debit merchant, credit refund-outstanding, then on settlement, debit refund-outstanding, credit cardholder), and a separate idempotency key. A double-refund is a real money loss; "negative charge" thinking hides this because it suggests subtraction, not a distinct event.

### Pitfall 9 — Not handling 3-D Secure failures

3-D Secure (3DS) adds an authentication step to the flow. The PSP returns one of:

- **Authenticated**: proceed.
- **Not enrolled**: proceed under no liability shift (you eat chargebacks).
- **Failed**: do not proceed. The cardholder's bank denied the auth.

The "not enrolled" case is the trap. Many merchants proceed anyway because "the customer is right there." This is sometimes the right call (friction vs chargeback risk), but it must be a **deliberate policy decision**, not a silent default. Different PSPs expose this differently; read your PSP's docs.

### Pitfall 10 — Assuming a payment is "complete" when the PSP says so

For card payments, `charge.succeeded` means **authorized and captured**. For ACH, it means **submitted to the bank** — actual settlement is days later and can still return. Don't release goods on ACH "succeeded" unless your risk policy says so (usually: only for repeat, trusted customers). For SEPA Instant, settlement is in seconds; for wire transfers, it's same-day.

The interview-grade framing: "succeeded" is a **state in the payment lifecycle**, not a final state. The lifecycle is `initiated → authorized → captured → clearing → settled → reconciled`. Each step has its own failure mode.

---

## Interview Q&A

### Q1 — "Walk me through what happens when a user clicks 'Pay' at checkout."

The scripted answer:

1. **Client side**: The order service generates a payment intent with a unique `idempotency_key` (UUID), the order ID, amount, currency, and the buyer's payment method token (from the PSP's client SDK).
2. **Edge**: The Payment Gateway validates auth, rate limits, and the order's preconditions (cart not expired, amount matches).
3. **Payment Service**: Inserts a `payment_order` row in `PENDING` state with the idempotency key. Returns a `payment_intent_id` to the client immediately.
4. **PSP interaction**: The client's PSP SDK confirms the payment method (3DS challenge if needed). The PSP calls back asynchronously via webhook.
5. **Webhook handler**: Verifies the PSP signature, looks up the `payment_order` by PSP reference, checks the idempotency store, and (in a single DB transaction) writes 2 ledger rows, updates the wallet, marks the payment `SUCCESS`, and inserts an outbox event.
6. **Outbox relay**: Publishes `order.paid` to Kafka. The order service consumes it and marks the order `CONFIRMED`.
7. **Customer notification**: Email/SMS via a notification service consuming the same event.

Total latency to the customer: 1–3 seconds for card with 3DS, 200–500 ms without.

### Q2 — "How do you make sure a customer is never double-charged?"

The defensive answer layers four mechanisms:

1. **Idempotency key** at the API level (Stripe-style) — replays return the stored response, not a new charge.
2. **Unique constraint** on the idempotency key in the database — even a race between concurrent retries can only insert one row.
3. **PSP-side idempotency** — we pass our key to Stripe; Stripe de-duplicates on their side too. (They can be replayed across our two systems.)
4. **Reconciliation** — if all three somehow fail, the daily reconciliation against the PSP's settlement file catches the discrepancy, and finance ops issue a refund.

In practice, layers 1+2 are sufficient > 99.99% of the time. Layer 3 protects against bugs in our code. Layer 4 is the safety net that catches what no software can prevent.

### Q3 — "How would you scale to 100x — 100M transactions/day?"

The math: 100M/day = 1,157 TPS average, 11,570 TPS peak (10×). This is still small for the ledger itself (a single Postgres can do 10k TPS with the right schema). The real scaling questions:

1. **Shard the ledger** by `account_id`. Most queries are "give me account X's history," which is single-shard. Cross-account transfers (e.g., buyer → merchant) become a saga.
2. **Sharded wallets**: same key, same shard as the user's ledger. Balance read is a single-shard lookup.
3. **Outbox → Kafka** is mandatory at this scale. Synchronous notifications don't fit.
4. **Reconciliation parallelism**: split by PSP, by region, by currency. Multiple reconcilers run in parallel.
5. **Multi-region**: US, EU, APAC. Each region has its own ledger shard. Cross-region transfers are a saga with eventual consistency.

At 1B+ TPS, you leave RDBMS and go event-sourced (Chapter 28's approach). But at 100M/day, the RDBMS-centric design holds.

### Q4 — "What happens during a PSP outage?"

A 30-minute PSP outage during a sale is a real scenario. The response:

1. **Buffer**: queue payment intents in a local store (Postgres outbox + Kafka). Customers see "payment pending" rather than failure.
2. **No synchronous retries** against the down PSP — that amplifies the outage.
3. **Exponential backoff with circuit breaker**: after N failures, the circuit opens; all calls fail fast for a cooldown period; the system retries with backoff.
4. **Fallback PSP**: if the integration supports multi-PSP, route to the secondary. This is why the abstraction layer (a `PaymentProvider` interface) matters even for a single-PSP integration.
5. **Webhook catch-up**: when the PSP comes back, query the status of all in-flight payment_orders and reconcile.
6. **Customer communication**: the order confirmation email includes "your payment is being processed" — not "your payment succeeded" — until the PSP confirms.

A circuit breaker around the PSP call is the single most important resilience pattern here. Without it, the payment service will pile up requests, exhaust its own connection pool, and cascade-fail.

### Q5 — "How do you handle cross-currency payments?"

Three models, in increasing complexity:

1. **Single currency at the merchant**: convert at the PSP's published rate at charge time. The merchant sees one currency; we record both in the ledger for audit.
2. **Multi-currency wallet**: hold balances in multiple currencies. A `EUR → USD` transfer goes through an FX account, recording both the EUR debit and the USD credit plus a small FX fee.
3. **Stablecoin / crypto**: out of scope for most systems but possible. The ledger's "currency" field accepts any string; the FX account handles the conversion.

For each model, the rule is the same: **never silently round or float**. Record every conversion at a precise rate with a timestamped FX rate snapshot, and the audit trail lets you recompute any balance exactly.

### Q6 — "How would you test a payment system?"

Six categories of test, with concrete examples:

1. **Unit**: ledger entry generation, idempotency key handling, retry classification. Pure functions, no I/O.
2. **Integration with PSP sandbox**: every PSP has a sandbox (Stripe test mode, Adyen test). Run the full happy path against it.
3. **Failure injection**: kill the PSP mock mid-call; verify the outbox, the retry, and the eventual success. Simulate webhook delivery twice — verify single application. Simulate webhook *never* delivered — verify reconciliation catches it.
4. **Concurrency**: 100 parallel requests with the same idempotency key — exactly one PSP call, all 100 return the same result. 100 parallel transfers from the same wallet — final balance is the sum of all transfers.
5. **Property-based**: invariant checks on the ledger. For every transaction, debits == credits. For every account, balance == SUM(ledger entries). Run as a continuous check.
6. **Reconciliation drill**: deliberately mis-record 5 transactions; verify reconciliation flags them; verify auto-correction works for known-fee mismatches.

The most valuable test is the **property-based** one: it asserts the ledger's correctness invariant for *every* test run, not just for hand-picked scenarios. QuickCheck-style testing for payments is a known pattern in finance.

### Q7 — "Where does event sourcing fit in, and when would you use it?"

Event sourcing is the right answer when:

- **Audit is non-negotiable** (regulated industries: banking, healthcare, gambling).
- **The state is rich and the queries are varied** (you need arbitrary historical views).
- **Scale demands** a streaming write path (Kafka + projector) over a row-update RDBMS.

For most e-commerce and SaaS billing, the **immutable ledger + idempotency + reconciliation** design is sufficient and simpler. The event-sourced approach (Chapter 28) becomes necessary at 1M+ TPS or when the same money movement has many downstream views (fraud, analytics, settlement, audit, ML features).

---

## Key Terms / Glossary

| Term | Definition | Common misconception |
|------|------------|----------------------|
| **Idempotency key** | A unique identifier on a logical operation; replays return the stored response. | "It's the same as a request ID" — request IDs correlate logs; idempotency keys prevent duplicate side effects. |
| **Exactly-once** | A property of *effect*, not delivery: with at-least-once delivery + idempotent receivers, you get exactly-once effect. | "Exactly-once delivery is a thing" — over a network, no. |
| **At-least-once** | The message will be delivered one or more times; duplicates are possible. The default for most message systems. | "It's a bug" — at-least-once + idempotency is the standard pattern. |
| **At-most-once** | The message is delivered zero or one times; loss is possible. Used when duplicates are worse than loss. | "It's the safe default" — usually the opposite; loss is harder to detect than duplication. |
| **Double-entry bookkeeping** | Every money movement touches ≥ 2 accounts; sum of debits = sum of credits. Self-checking. | "It's a redundant safety measure" — it is the only safety measure; single-entry ledgers cannot be audited. |
| **PSP (Payment Service Provider)** | Third party that processes card / bank payments on your behalf. Stripe, Adyen, Braintree, Square. | "It's the same as a payment gateway" — gateway = the API; PSP = the entity behind it. Many gateways are run by PSPs. |
| **Acquirer** | Bank that processes card transactions on a merchant's behalf. | "The PSP is the acquirer" — sometimes, but Stripe uses multiple acquirers per region. |
| **Issuer** | Bank that issued the card to the cardholder. | "The card network" — Visa/Mastercard are networks, not issuers. |
| **Card network** | Visa, Mastercard, Amex, Discover. Routes authorization and clearing. | "Networks process payments" — networks route; banks process. |
| **Authorization** | The cardholder's bank reserves funds on a card. Holds the money, doesn't transfer it. | "Auth = capture" — they're separate. Capture can be later. |
| **Capture** | The actual transfer of authorized funds. Auth + capture is the full charge. | "Auth is the charge" — auth can expire (usually 7 days) before capture. |
| **Settlement** | The acquirer wires the net amount to the merchant's bank. T+1 to T+3. | "Settlement = capture" — capture is between PSP and acquirer; settlement is between acquirer and merchant bank. |
| **Webhook** | An HTTP callback the PSP makes to your server to notify you of events. | "Webhooks are reliable" — they're at-least-once; you must handle dedupe and missed deliveries. |
| **Reconciliation** | Comparing internal records against an external source (PSP settlement file, bank statement) to find discrepancies. | "Reconciliation is optional" — it is the safety net; non-optional in production. |
| **Dead Letter Queue (DLQ)** | A queue where messages that fail processing N times are parked for manual inspection. | "It's a failure state" — it's a feature. DLQ keeps the main pipeline healthy. |
| **Idempotent receiver** | A handler that, given the same input event, produces the same effect at most once. | "Idempotency is the sender's job" — it is primarily the receiver's job. |
| **Outbox pattern** | Write a business state change and an "event to publish" in the same DB transaction; a relay publishes asynchronously. | "It's the same as CDC" — outbox is *designed* to avoid CDC's dual-write problem; CDC is a derivative. |
| **Saga** | A sequence of local transactions with compensating transactions for rollback. | "Saga = 2PC" — saga is eventually consistent with compensations; 2PC is strongly consistent with locks. |
| **PCI DSS** | Payment Card Industry Data Security Standard. The compliance regime for handling card data. | "Using a PSP makes me PCI compliant" — it reduces your *scope*; you still have to follow PCI for the parts you handle. |
| **PAN (Primary Account Number)** | The 16-digit card number. The thing PCI DSS exists to protect. | "The CVV is the sensitive part" — both are sensitive; PAN exposure is the larger risk. |
| **3-D Secure (3DS)** | An authentication protocol (Verified by Visa, Mastercard SecureCode, etc.) that adds a challenge step. | "3DS eliminates chargebacks" — it shifts *liability* to the issuer, but chargebacks can still occur. |
| **Chargeback** | A cardholder-initiated dispute that reverses a charge. Funds are debited immediately from the merchant. | "The merchant can refuse" — they can dispute (with evidence), but funds are debited upfront. |
| **Interchange fee** | The fee paid from the acquirer to the issuer, set by the card networks. The largest component of "merchant discount." | "It's set by the merchant's bank" — set by the network per card type, region, and merchant category. |
| **PSP fee / merchant discount** | The total fee the merchant pays the PSP, including interchange + assessment + PSP markup. | "Stripe charges 2.9% + 30¢" — that's the published rate; the actual cost includes interchange, which varies. |
| **Fraud scoring** | A risk model (often ML) that scores each transaction for fraud probability. | "It's deterministic" — most fraud systems are ML-based and probabilistic; false positives and negatives are expected. |
| **AML (Anti-Money Laundering)** | Regulatory regime requiring monitoring and reporting of suspicious money movements. | "It's the same as fraud" — AML is regulatory; fraud is loss-prevention. Both are risk checks, but AML has legal reporting requirements. |
| **Settlement file** | A daily file the PSP produces listing all settled transactions, fees, and net amounts. | "It's the source of truth" — the PSP's file is the PSP's truth; the ledger is *your* truth. Reconciliation is the comparison. |
| **Multi-PSP routing** | Sending a transaction to one of several PSPs based on rules (cost, region, redundancy). | "It's just failover" — failover is one mode; cost-based and region-based routing are equally common. |
| **Currency / minor unit** | The smallest unit of a currency (cent, fen, pence). Money should be stored as integer minor units, not floats. | "DECIMAL is enough" — DECIMAL is correct, but integer minor units are simpler and faster. |
| **Replay attack** | An attacker resubmits a captured valid request to repeat the action. Idempotency keys + signed webhooks defend against this. | "TLS prevents it" — TLS prevents network eavesdropping, not application-level replay. |
