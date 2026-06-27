# Design a Digital Wallet

A digital wallet (think PayPal, Alipay, Venmo balances, or an in-app coin balance) holds value for users and lets them move it around. The interesting engineering problem is the **balance transfer**: atomically moving money from one wallet to another, correctly, under high throughput, with a complete audit trail — and eventually doing it at **1,000,000 transactions per second**.

---

## Step 1 — Understand the Problem and Scope

### Functional requirements

- Each user has a wallet with a balance.
- Support **balance transfer** between two wallets within the platform (A pays B).
- Support querying current balance and transaction history.
- (Out of scope but adjacent: top-up/withdrawal via the payment system, FX.)

### Non-functional requirements

- **Correctness / strong consistency** of balances. No money created or destroyed. A transfer either fully happens or not at all.
- **Atomicity**: debit sender and credit receiver as a single logical unit.
- **Durability**: a committed transfer survives crashes.
- **Reproducibility / auditability**: we can reconstruct any balance at any past point in time and prove how it got there.
- **Idempotency**: retries don't double-apply.
- **High availability** and ultimately **~1M TPS**.

### Back-of-the-envelope estimation

- Target: **1,000,000 TPS**. This is the headline constraint and it changes everything.
- A single relational DB node does maybe a few thousand write TPS. So 1M TPS implies massive horizontal scale, in-memory processing, and/or batching — a naive "one row update per transfer" cannot get there.

The chapter builds up in stages: first a correct single-node design, then distributed transactions, then a high-performance event-sourced design that can reach 1M TPS.

---

## Step 2 — High-Level Design (build up in stages)

### Stage 0: In-memory map (and why it fails)

The simplest idea: keep balances in a hash map and apply transfers in memory.

- A transfer = `balances[A] -= amount; balances[B] += amount`.
- **Problems**: not durable (crash loses everything), no atomicity across a real distributed system, no audit trail, single point of failure. Good for intuition, unusable in production.

### Stage 1: Single database, ACID transactions

Put both wallets in one relational database and wrap the transfer in a single ACID transaction:

```sql
BEGIN;
UPDATE wallet SET balance = balance - 100 WHERE user_id = 'A' AND balance >= 100;
UPDATE wallet SET balance = balance + 100 WHERE user_id = 'B';
COMMIT;
```

- Atomicity, consistency, isolation, durability all handled by the DB.
- The `balance >= 100` guard prevents overdraft.
- **Limitation**: works only while both accounts live in one database. It does not scale to 1M TPS, and it breaks once wallets are sharded across nodes.

### Stage 2: Wallets on different databases → distributed transactions

When A and B live on different database nodes/services, a single local transaction no longer covers both. We need a **distributed transaction**. Three classic approaches:

---

## Step 3 — Deep Dive

### Distributed transaction options

#### 2PC — Two-Phase Commit

A coordinator drives all participants through two phases:

1. **Prepare**: ask every participant to do the work and lock resources, then vote "yes/can commit" or "no".
2. **Commit/Abort**: if all voted yes, tell everyone to commit; otherwise abort everywhere.

- **Pros**: strong consistency; conceptually simple.
- **Cons**: **synchronous and blocking** — participants hold locks until the coordinator decides. If the **coordinator crashes** after prepare, participants are stuck holding locks (blocking problem). Poor availability and throughput. Bad fit for 1M TPS.

#### TCC — Try-Confirm/Cancel

An application-level, business-aware version of 2PC with three explicit operations:

1. **Try**: reserve resources (e.g., freeze $100 in A's wallet).
2. **Confirm**: commit the reservation (move the frozen funds).
3. **Cancel**: release the reservation if anything failed.

- **Pros**: no long-held DB locks; each phase is a normal short local transaction; more available than 2PC.
- **Cons**: you must implement Try/Confirm/Cancel for every operation, and each must be **idempotent** (Confirm/Cancel may be retried). More code, more states to reason about.

#### Saga

Break the distributed transaction into a sequence of **local transactions**, each with a **compensating transaction** that undoes it.

- Execute step by step (orchestration via a central coordinator, or choreography via events).
- If step *k* fails, run compensations for steps *k-1 … 1* in reverse.
- **Pros**: highly available, no global locks, scales well.
- **Cons**: only **eventual** consistency; you can briefly observe intermediate states; compensations must exist and be idempotent.

**Comparison**

| | 2PC | TCC | Saga |
|---|-----|-----|------|
| Consistency | Strong | Strong-ish | Eventual |
| Locks | Long (blocking) | Short | None |
| Availability | Low | Medium | High |
| Complexity | Medium | High | High |
| 1M TPS fit | Poor | Limited | Good (with the design below) |

### The high-performance design: Event Sourcing + CQRS

To hit 1M TPS while keeping perfect auditability, the canonical answer is **event sourcing**, often paired with **CQRS**.

#### Event sourcing

Instead of storing *current balance* and mutating it, store the **immutable, ordered log of events** (commands/state changes). The current state is a **fold** (replay) of all events.

- Events: `TransferRequested`, `BalanceDebited`, `BalanceCredited`, etc.
- The **event log is the source of truth**; balances are derived.
- Four conceptual pieces often described:
  1. **Command** — the intent ("transfer $100 from A to B").
  2. **Event** — the immutable fact of what happened, appended to the log.
  3. **State** — current balances, computed by applying events in order.
  4. **State machine** — deterministic logic that, given current state + an event, produces the next state.

**Reproducibility / audit** falls out for free: replay the log from the beginning (or a snapshot) and you reconstruct *every* historical balance exactly. This is exactly what auditors and reconciliation need.

#### Determinism is the key property

The state machine that applies events must be **fully deterministic**: same starting state + same ordered events ⇒ same resulting state, every time, on every replica. Determinism is what makes the log the single authority and enables:

- **Replay** to rebuild state after a crash.
- **Replication** by shipping the *same ordered log* to followers, which independently arrive at identical state (state-machine replication, à la Raft).
- **Verification**: re-run the log to detect bugs or corruption.

To keep it deterministic, push nondeterminism (timestamps, random IDs, external calls) *outside* — resolve them when creating the command, then the event carries fixed values.

#### CQRS — Command Query Responsibility Segregation

Separate the **write model** from the **read model**:

- **Write side**: append events to the log as fast as possible (sequential, append-only — extremely fast).
- **Read side**: asynchronously project events into query-optimized views (current balance per user, transaction history). Reads never touch the write hot path.

This split lets the write path be a tight, in-memory, append-only loop (great for throughput) while reads are served from materialized projections.

#### Why this reaches 1M TPS

- **Append-only sequential writes** to a log are far faster than random row updates.
- **In-memory state machine** processes events without per-event disk seeks; durability comes from the persisted log (often with batched/group commit).
- **Snapshots** periodically capture state so you don't replay from genesis every restart.
- **Sharding/partitioning** the wallet space (e.g., by user/account) lets many independent state machines run in parallel; cross-shard transfers fall back to Saga/TCC.

### Redis vs RDBMS — the durability trap

A tempting shortcut is to keep balances in **Redis** for speed.

- **Redis pros**: blazing in-memory ops, easily handles huge read/write rates.
- **Redis cons for money**: it is primarily an in-memory store; default persistence (RDB snapshots / AOF) can **lose recent writes** on crash, and it lacks rich multi-key ACID transactions across a cluster. Using Redis as the *system of record* for balances risks losing money — unacceptable.
- **RDBMS pros**: real ACID, durability, constraints. **Cons**: lower raw throughput.

**Resolution**: don't choose Redis *or* RDBMS as the truth — make the **append-only event log** the durable source of truth, keep **in-memory state** for speed, and use durable storage (and snapshots) so nothing is lost. Redis, if used, serves derived read projections (a cache/read model), never the authoritative balance.

### Idempotency

Same discipline as the payment system:

- Each transfer carries a unique **transaction ID / idempotency key**.
- The state machine records applied IDs and **ignores duplicates**, so a retried command does not double-apply.
- Because events are immutable and ordered, deduplication is a natural fit — an event with an already-seen ID is dropped.

### Reliability of the log itself

- Replicate the log across nodes via a **consensus protocol (Raft/Paxos)** so a committed event survives node failure and all replicas apply it in the same order (deterministic replay → identical state).
- A new or recovering replica catches up by replaying from the latest **snapshot** plus the tail of the log.

---

## Step 4 — Wrap Up

### Key takeaways

- The core problem is an **atomic balance transfer** that never creates or loses money.
- Start simple: a **single-DB ACID transaction** is correct but doesn't scale or span shards.
- For cross-node transfers, pick a **distributed transaction** model:
  - **2PC** = strong but blocking, poor availability.
  - **TCC** = reservation-based, idempotent, more available.
  - **Saga** = local steps + compensations, highly available, eventually consistent.
- For **1M TPS + full audit**, use **event sourcing**: an immutable, ordered, append-only event log as the source of truth; current balance is a deterministic replay.
- **Determinism** of the state machine is what enables replay, replication (Raft), and verification.
- **CQRS** separates the fast append-only write path from query-optimized read projections.
- Don't trust **Redis** as the system of record for money — durability gaps can lose funds; the durable log is the truth, in-memory state is for speed, snapshots bound recovery time.
- **Idempotency keys** plus immutable ordered events give exactly-once application and protect against retries.

### Trade-off summary

| Goal | Mechanism |
|------|-----------|
| Atomicity (1 node) | ACID transaction |
| Atomicity (N nodes) | 2PC / TCC / Saga |
| Throughput (1M TPS) | Append-only log + in-memory state machine + sharding |
| Durability | Persisted, consensus-replicated log + snapshots |
| Auditability / reproducibility | Event sourcing (replay the log) |
| Fast reads | CQRS read projections |
| Exactly-once | Idempotency key + dedupe on immutable events |

---

## Back-of-the-Envelope Math (Extended)

### 1M TPS, taken apart

| Layer | Required throughput | Per-node capacity | Nodes needed |
|-------|--------------------|--------------------|---------------|
| API ingest | 1M TPS | 50k TPS (4-core Go service) | 20 |
| Validation / idempotency lookup | 1M TPS | 100k TPS (Redis cluster, hash-routed) | 10 |
| Event log writes | 1M TPS | 100k–500k writes/sec per partition (Kafka) | 5–10 partitions (with replication factor 3) |
| State machine (in-memory) | 1M events/sec | 1M+ events/sec per node (deterministic, single-threaded per shard) | 20 (one per wallet shard) |
| Read projections | 100M QPS (read-heavy) | 50k QPS per Redis node | 2,000 (served from materialized views) |
| Snapshot / replay | 1 snapshot per shard per hour | — | — |

The number that matters most is the **state machine** throughput. A single-threaded, in-memory state machine doing pure event application typically hits 1M+ events/sec on commodity hardware. Sharding 1B wallets into 1,000 shards gives 1,000 TPS per shard — well within capacity. The **append-only log** is the next constraint; Kafka and similar systems are designed for this throughput class.

### Storage math

For 1B users with an average of 100 transfers/user over a year:

- Events: 1B × 100 = 100B events/year.
- Per event: ~250 bytes (type, txn_id, from, to, amount, currency, ts, version).
- Yearly volume: 100B × 250 = 25 TB/year.
- 7-year retention: 175 TB. With 3x replication: 525 TB.

Storage is **not** the constraint. HDD-backed object storage at $20/TB/month is $350/month for 525 TB. The constraints are:
- **Tail latency** on the hot write path.
- **Recovery time** from a snapshot (must replay 1 hour of events in seconds).
- **Cross-shard transfers** (a tiny fraction of total — design around them).

### Cross-shard transfer math

If wallets are sharded by `user_id % N`, a transfer between A and B is single-shard only when `A_shard == B_shard`. For random distribution, that's a 1/N probability. With 1,000 shards, 99.9% of transfers are cross-shard.

Two ways to handle this:

1. **Two-phase saga across shards**: debit A (with a reservation), credit B (with a reservation), commit both. The saga overhead adds 2–3 round trips; acceptable for the 0.1% of transfers that are single-shard *and* the 99.9% that are cross-shard.
2. **Co-locate users who transfer to each other**: graph-based sharding places frequently-interacting users on the same shard. Complex, but reduces cross-shard traffic to < 5%.

In practice, the saga overhead is small compared to the 1M TPS target, and most systems just accept the cross-shard cost.

### Snapshot and recovery math

A snapshot captures the state machine's current state for all wallets in a shard. Per wallet: ~200 bytes (user_id, balance, currency, last_event_seq).

- 1M wallets per shard: 200 MB per snapshot.
- Snapshot every 1 hour: 24 snapshots/day × 200 MB = 4.8 GB/day per shard.
- 1,000 shards: 4.8 TB/day. Storable in object storage at trivial cost.

Recovery time: load latest snapshot (200 MB) + replay 1 hour of events (say 360M events at 1M/sec sustained per shard) = 360 seconds. **6 minutes** to recover from a 1-hour-old snapshot. To improve: snapshot more frequently (e.g., every 5 minutes → 36-second recovery).

### Latency budget

| Stage | P50 | P99 |
|-------|-----|-----|
| API edge | 1 ms | 5 ms |
| Idempotency check (Redis) | 0.5 ms | 2 ms |
| Saga step 1 (debit A) | 2 ms | 10 ms |
| Saga step 2 (credit B) | 2 ms | 10 ms |
| Event log append (Kafka) | 5 ms | 20 ms |
| Saga confirm | 2 ms | 10 ms |
| **Total** | **~12 ms** | **~57 ms** |

Compare to a card payment (1.7 seconds with 3DS): wallet-internal transfers are 30–100x faster because there's no external network call.

---

## ASCII Architecture Diagrams

### Diagram 1 — Event-sourced wallet write path

```
  Client         API         Command      State Machine     Event Log
                 Edge        Validator    (per-shard,        (Kafka /
                              + Idem       in-memory)          RDBMS)
   │              │              │              │                │
   │  POST /      │              │              │                │
   │  transfers   │              │              │                │
   │  {from,to,   │              │              │                │
   │   amount,    │              │              │                │
   │   txn_id}    │              │              │                │
   │─────────────►│              │              │                │
   │              │  forward     │              │                │
   │              │─────────────►│              │                │
   │              │              │  validate    │                │
   │              │              │  amount,     │                │
   │              │              │  balance,    │                │
   │              │              │  idempotency │                │
   │              │              │              │                │
   │              │              │  build cmd:  │                │
   │              │              │  TransferReq │                │
   │              │              │  (resolved)  │                │
   │              │              │              │                │
   │              │              │  apply cmd   │                │
   │              │              │  in-memory:  │                │
   │              │              │  emit events │                │
   │              │              │─────────────►│                │
   │              │              │              │  append events │
   │              │              │              │  (Raft-replicated)
   │              │              │              │───────────────►│
   │              │              │              │                │
   │              │              │              │  ack           │
   │              │              │◄─────────────│◄───────────────│
   │              │              │              │                │
   │              │  202 Accepted│              │                │
   │              │  {txn_id}    │              │                │
   │◄─────────────│◄─────────────│              │                │
   │              │              │              │                │
   │  query       │              │              │                │
   │  status      │              │              │                │
   │─────────────►│  read        │              │                │
   │              │  projection  │              │                │
   │              │──────────────────────────────────────────────►
   │              │              │              │  balance view  │
   │  {pending}   │              │              │                │
   │◄─────────────│              │              │                │
```

Note the API returns **202 Accepted** with a `txn_id` immediately, then the user polls (or subscribes) for status. The actual settlement happens asynchronously. The state machine is **single-threaded per shard**; the API is **stateless and horizontally scaled**.

### Diagram 2 — CQRS read projection pipeline

```
   Event Log (Kafka)
        │
        │  topic: wallet.events
        │  partition by wallet_id (so a wallet's events are ordered)
        │
        ├─────────────────────────────┬──────────────────────────────┐
        ▼                             ▼                              ▼
   ┌─────────────┐             ┌─────────────┐              ┌─────────────┐
   │ Balance     │             │ History     │              │ Fraud       │
   │ Projector   │             │ Projector   │              │ Detector    │
   │ (in-memory  │             │ (writes to  │              │ (streaming  │
   │  hash +     │             │  ClickHouse │              │  rules)     │
   │  Redis)     │             │  / Druid)   │              │             │
   └──────┬──────┘             └──────┬──────┘              └──────┬──────┘
          │                           │                            │
          ▼                           ▼                            ▼
   ┌─────────────┐             ┌─────────────┐              ┌─────────────┐
   │ GET /balance│             │ GET /history│              │ risk_score  │
   │ (Redis,     │             │ (analytical │              │ (per user,  │
   │  ~1ms P99)  │             │  store)     │              │  cached)    │
   └─────────────┘             └─────────────┘              └─────────────┘
```

Three independent consumers of the same log, each with its own storage choice optimized for its read pattern. The write path doesn't know or care that they exist; the read path doesn't see the write path's complexity. That's CQRS in one picture.

### Diagram 3 — Saga for cross-shard transfer

```
  Coordinator                  Shard A (sender)             Shard B (receiver)
      │                              │                              │
      │  Saga: Transfer(A→B, $100)   │                              │
      │                              │                              │
      │  Try: reserve $100 in A      │                              │
      │─────────────────────────────►│                              │
      │                              │  freeze balance,             │
      │                              │  emit Reserved(A, $100)      │
      │  ack                         │                              │
      │◄─────────────────────────────│                              │
      │                              │                              │
      │  Try: credit B              │                              │
      │─────────────────────────────────────────────────────────────►
      │                              │                              │  credit balance,
      │                              │                              │  emit Credited(B, $100)
      │  ack                         │                              │
      │◄─────────────────────────────────────────────────────────────│
      │                              │                              │
      │  Confirm: commit both        │                              │
      │─────────────────────────────►│                              │
      │                              │  release reserved → debit,   │
      │                              │  emit Debited(A, $100)       │
      │  ack                         │                              │
      │◄─────────────────────────────│                              │
      │                              │                              │
      │  Confirm: commit B           │                              │
      │─────────────────────────────────────────────────────────────►
      │                              │                              │  commit pending credit,
      │                              │                              │  emit Confirmed
      │  done                        │                              │
      │                              │                              │
      │  Failure case: B's Try failed                               │
      │  Cancel A's reservation (idempotent)                        │
      │─────────────────────────────►│                              │
      │                              │  release frozen $100,         │
      │                              │  emit Released(A)             │
```

The saga is **idempotent at every step**: a retried "Try" against a shard that already accepted the reservation sees the prior state and proceeds. A retried "Cancel" against a shard that already released the reservation is a no-op.

### Diagram 4 — Snapshot and replay recovery

```
  ┌────────────────────────┐         ┌────────────────────────┐
  │   In-memory state      │         │   Persisted snapshot   │
  │   (volatile)           │         │   + event log tail     │
  │                        │         │   (durable)            │
  │   wallet_A: $100       │         │                        │
  │   wallet_B: $50        │         │   snapshot at seq=9999:│
  │   last_seq: 10500      │         │     wallet_A: $100     │
  │                        │         │     wallet_B: $50      │
  └────────────────────────┘         │   event log: 10000..∞  │
            │                        └────────────────────────┘
            │                                  │
            │  crash                            │  restart
            ▼                                  ▼
       (lost)                          ┌──────────────────────┐
                                       │  load snapshot       │
                                       │  → wallet_A: $100    │
                                       │  → wallet_B: $50     │
                                       │  → last_seq: 9999    │
                                       │                      │
                                       │  replay events       │
                                       │  10000..15000        │
                                       │  → wallet_A: $80     │
                                       │  → wallet_B: $70     │
                                       │  → last_seq: 15000   │
                                       │                      │
                                       │  resume              │
                                       └──────────────────────┘
```

The duration of the replay is bounded by the snapshot interval. Snapshot every 5 minutes → worst case 5 minutes of replay, at 1M events/sec/shard = 300M events to replay. 300M events for a single-shard state machine (which applies each in microseconds) is recoverable in 5–30 seconds, depending on the complexity of the state transition.

---

## Trade-off Tables

### Atomicity strategy for transfers

| Strategy | Consistency | Throughput | Code complexity | Use when |
|----------|-------------|-----------|-----------------|----------|
| Single-DB ACID | Strong | ~10k TPS | Low | < 10k TPS, single region, single DB |
| 2PC across shards | Strong | ~5k TPS (locks) | Medium | Few shards, low contention, latency-tolerant |
| TCC (Try-Confirm-Cancel) | Strong-ish | ~50k TPS | High (3 ops per action) | Need to span services, can afford app-level logic |
| Saga with compensations | Eventual | ~500k TPS | High | High TPS, can accept brief inconsistency |
| Event sourcing + CQRS | Eventual (with read-your-writes via projection) | 1M+ TPS | Very high | Need 1M TPS + full audit |
| Hybrid: in-shard ACID + cross-shard saga | Strong in-shard, eventual cross-shard | ~200k TPS | Medium | Most production systems |

### Storage of the event log

| Option | Throughput (writes/sec) | Durability | Ordering | Cost | When |
|--------|------------------------|------------|----------|------|------|
| Local NVMe + fsync | ~100k | High (single node) | Per-shard only | $ | Single-node, low scale |
| Kafka (replicated) | ~1M per cluster | High (replication factor 3) | Per-partition | $$ | Default; most production systems |
| Pulsar / Redpanda | ~1M+ per cluster | High | Per-partition | $$ | Kafka alternative; tiered storage |
| FoundationDB RecordLayer | ~100k with transactions | High | Global | $$ | Need transactions over the log |
| Custom Raft log | 100k–500k per group | High | Per-group | High (ops) | Custom consensus needs |
| AWS Kinesis / GCP Pub/Sub | ~1M+ (managed) | High | Per-shard | $$$ | Cloud-native, prefer managed |

### Read projection storage

| Projection type | Read latency | Storage cost | Best for |
|-----------------|--------------|--------------|----------|
| In-memory hash (per process) | < 1 ms | RAM (~$10/GB/month) | Current balance, hot data |
| Redis (clustered) | 1–5 ms | RAM | Current balance, small history |
| Postgres (single) | 5–20 ms | Disk (~$0.10/GB/month) | Per-user history, medium scale |
| ClickHouse / Druid | 50–500 ms | Disk (columnar, compressed) | Analytical queries over history |
| S3 / Parquet + Athena | seconds | Object storage (~$0.02/GB/month) | Cold / audit / compliance |
| ElasticSearch | 10–100 ms | Disk | Full-text search over transaction memos |

### Snapshot strategy

| Strategy | Recovery time | Storage cost | Best when |
|----------|---------------|--------------|-----------|
| No snapshots (replay from genesis) | Hours-to-days | Trivial | Never in production |
| Snapshot every 1 hour | 1 hour replay bound | Low | 1M TPS, few hours' replay is acceptable |
| Snapshot every 5 minutes | 5 minutes replay bound | Medium | 1M TPS, < 1 minute recovery target |
| Snapshot every 1 minute | 1 minute replay bound | Medium | Sub-minute recovery SLA |
| Snapshot on every N events (event-count based) | Bounded by N / event rate | Variable | Predictable recovery regardless of rate |
| Tiered snapshots (full + delta) | Fast (load full + apply delta) | Higher | Very large state machines |

### Sharding strategy

| Strategy | Cross-shard transfer frequency | Rank/aggregation cost | When |
|----------|-------------------------------|----------------------|------|
| By user_id (hash) | 1/N (random) | High | Default; uniform distribution |
| By region | High within region, low cross-region | Medium | Multi-region, regulatory residency |
| By account type (merchant vs consumer) | Low | Low | Clear separation |
| Graph-based (cluster related users) | Low | Very high (re-shard on graph change) | Highly connected clusters |
| By currency | None within currency, all cross-currency | Low | Multi-currency wallets |
| Hybrid: hash + secondary index | Tunable | Medium | Default with a tunable hot/cold balance |

### In-memory state machine implementation

| Approach | Throughput | Latency | When |
|----------|-----------|---------|------|
| Single-threaded, lock-free per shard | ~1M events/sec/shard | µs | Default; maximizes determinism |
| Actor model (Akka / Erlang) | ~100k–500k events/sec/node | ms | Distributed state, fault tolerance |
| Disruptor pattern (LMAX-style) | 10M+ events/sec/node | ns–µs | Extreme throughput per node |
| CRDT (conflict-free replicated data type) | ~50k events/sec/node | ms | Multi-master, no coordination |
| Stream processing (Flink / Kafka Streams) | ~100k events/sec/job | ms | Existing streaming infra |

### Event format

| Format | Size | Schema evolution | When |
|--------|------|------------------|------|
| JSON | Largest | Easy to evolve | Debugging, small scale |
| Avro | Small | Schema registry, backward/forward compat | Default for Kafka, recommended |
| Protobuf | Small | Field numbers, schema rules | Cross-language, low latency |
| Custom binary | Smallest | Manual, brittle | Hyper-optimized, internal only |

---

## Real-World Case Studies

### PayPal — the original digital wallet at scale

PayPal's wallet is the canonical example of a digital wallet at internet scale. Public engineering talks and patent disclosures describe:

- An **account balance** stored in a relational database (originally MySQL, later sharded).
- A **transaction log** that records every balance change.
- **Idempotency keys** on every API call — PayPal was an early adopter of idempotency for payment operations.
- **Massively sharded** ledger databases by account ID; cross-account transfers use 2PC (historically) or saga-like patterns.
- **Daily reconciliation** against bank settlement files and partner PSPs.

PayPal's lesson: even at 10k+ TPS (their published scale at peak), a **sharded RDBMS with strong consistency per shard** is the right design. Event sourcing only becomes necessary when the read-side complexity or the audit requirements exceed what a relational model can serve. Most wallets do not need full event sourcing.

### Apple Pay — tokenization, not a wallet balance

Apple Pay is a **payment network tokenization** layer, not a stored-balance wallet. When a user adds a card to Apple Wallet:

1. The card is sent to the issuer (via Apple Pay's secure element).
2. The issuer returns a **Device Account Number (DAN)** — a tokenized PAN.
3. At payment, the device generates a **dynamic cryptogram** (CVV-equivalent) for the transaction.
4. The merchant receives a normal card charge; the network routes it to the issuer with the token; the issuer maps the token to the real PAN.

The interesting engineering is the **secure element** (a hardware chip on the device) and the **dynamic cryptogram** (a per-transaction CVV that prevents replay). Apple Pay does not store user balances; it stores tokens. The balance lives at the issuer.

The lesson for wallet design: the **hard part of mobile payments is not the balance — it's the device, the cryptography, and the network round-trips**.

### Google Pay — HCE and the Secure Element split

Google Pay supports two modes:

1. **Secure Element (SE)**: a hardware chip on the device (older Android, mostly carriers). Same model as Apple Pay.
2. **Host Card Emulation (HCE)**: tokenization happens in software on the device, with the actual PAN stored at the network (Visa Token Service, Mastercard MDES). The device sends a tokenized cryptogram per transaction.

HCE made mobile payments work on devices without a secure element. The engineering trade-off:

- **HCE pros**: works on more devices, easier updates, no carrier gatekeeping.
- **HCE cons**: more attack surface (the token is in software, not hardware), requires the network to do the real-time token-to-PAN lookup (latency).

Google Pay's published performance targets: < 500 ms tap-to-acknowledge. They achieve this with a **tokenized cryptogram + a low-latency token vault lookup** at the network.

### PayPal vs Venmo vs Cash App — wallet UX differences

- **PayPal**: full e-commerce wallet. Holds balance, supports P2P, integrates with merchants. Settlement in 1–3 days to bank.
- **Venmo**: P2P-focused. Social feed (a UX decision, not technical). Balance is held by PayPal's banking partner (a real, FDIC-insured bank); Venmo is the user-facing app.
- **Cash App** (Block): P2P + investing + Bitcoin. Single integrated wallet with multiple "sub-balances" (USD, Bitcoin). Each sub-balance is a separate ledger.

The engineering difference: Venmo's ledger is simpler (one currency, two sides), Cash App's is multi-asset. The UX surfaces are very different but the underlying ledger model is similar: **append-only log + double-entry + idempotent transfers**.

### Alipay and WeChat Pay — wallet + payment network in one

Alipay and WeChat Pay are not just wallets — they are **payment networks with their own wallet products**. The architecture:

- **Wallet balance** held in a separate entity (Alipay's bank partner, or in-house for the licensed entities).
- **Payment network** connects merchants to the wallet via QR codes (China's de facto standard) or app-to-app APIs.
- **Settlement** happens in real time for QR payments; in batch for larger flows.

Alipay and WeChat Pay are widely cited as the highest-throughput payment systems in the world, with public reports of **hundreds of thousands of TPS** during Chinese New Year peaks. The architectures are not public in detail, but the published principles are:

- **In-memory state** for the hot path.
- **Append-only log** as the durable record.
- **Massive sharding** by user/merchant.
- **Real-time risk** scoring per transaction.

The takeaway: a wallet at Alipay/WeChat scale looks structurally similar to the event-sourced design — even if the implementation is a mix of legacy banking systems and modern infrastructure.

### India's UPI — interoperability as a design constraint

UPI (Unified Payments Interface) is a public infrastructure that lets any bank wallet interoperate. Engineering design points:

- **Bank-to-bank** transfers in real time (typically < 5 seconds end-to-end).
- **Single API** that any participating bank implements.
- **Two-phase flow**: debit A's bank, credit B's bank; both banks confirm via UPI before the user's app shows "success."
- **Idempotency** on every transaction via UPI's reference IDs.
- **Daily settlement** between banks via the Reserve Bank of India.

UPI's public scale: > 10 billion transactions/month in 2024 — averaging ~3,800 TPS, with peaks above 50,000 TPS. The lesson: **interoperability does not require losing consistency** — the two-phase flow with bank confirmations gives strong end-to-end semantics.

### M-Pesa — wallet on feature phones

M-Pesa (Kenya, started 2007) is a digital wallet that runs on **SMS / USSD** — feature phones with no internet. Engineering design:

- **Balance stored centrally** at Safaricom (the operator).
- **STK push** or USSD menu for the user to confirm.
- **Real-time ledger** updates on every transfer.
- **Agent network** for cash-in / cash-out (the most distinctive feature).

M-Pesa's design teaches that a digital wallet is not a mobile app; it's a **balance + transfer + cash-in/cash-out system**. The mobile app is just one client. The core engineering is the ledger and the agent network — the latter being a non-software challenge (logistics, fraud, training) that most digital wallet discussions ignore.

### Wallet security — tokenization, HCE, secure element

The security of a digital wallet rests on three layers:

1. **Authentication**: how the user proves identity (PIN, biometrics, device unlock).
2. **Tokenization**: how the card / account is represented in transactions.
3. **Cryptography**: how the transaction is signed and verified.

The classic security architecture:

- **Secure Element (SE)**: a tamper-resistant chip in the device. Stores the real PAN and signing keys. Performs crypto in hardware.
- **Host Card Emulation (HCE)**: software-only tokenization. The device stores a token; the network stores the PAN. The transaction is signed with a per-device key.
- **Tokenization**: replace the PAN with a token (e.g., a Device Account Number). The token is what travels over the air; the real PAN never leaves the issuer's vault.

Each of these has different threat models. The interview-grade answer: "a digital wallet must protect against device theft (SE), software compromise (HCE), and network interception (tokenization + TLS). The combination is what makes mobile payments safe."

---

## Common Pitfalls & Failure Modes

### Pitfall 1 — Using Redis as the system of record for balances

This is the most common error. Redis is fast, easy, and supports basic transactions. It does not support **durable, multi-key ACID transactions** with strong isolation across a cluster. A Redis `MULTI/EXEC` block across multiple shards is not atomic the way a SQL `BEGIN/COMMIT` is.

The failure: under load, two concurrent transfers both see a balance of $100, both decrement, both succeed, and the balance goes to -$100. Or: a Redis crash loses the most recent N seconds of writes (RDB snapshot window).

The fix: **Redis is a cache, not a ledger**. The ledger is a durable, append-only log (RDBMS or Kafka + projector). Redis serves the materialized balance view; the log is the truth.

### Pitfall 2 — "We have ACID, so we're safe"

A single-DB ACID transaction is correct **only when both accounts are in the same database**. The moment you shard by user_id, a transfer between users in different shards is no longer a single ACID transaction. This is when 2PC, TCC, or saga enter the picture — and where most systems make mistakes:

- Using 2PC across a high-traffic system and discovering the lock contention kills throughput.
- Using saga without idempotent compensations and discovering that a retried compensation double-undoes.
- Using TCC without making the Cancel operation idempotent and discovering that a retried cancel on an already-cancelled reservation is a bug.

The right path: **shard by user_id; make intra-shard transfers ACID; make cross-shard transfers a saga with idempotent Try/Confirm/Cancel.** Document the consistency model explicitly: "intra-shard strong, cross-shard eventual."

### Pitfall 3 — Race condition: concurrent transfers exceeding balance

Even with `WHERE balance >= amount`, there are subtle race conditions:

```sql
-- T0: A's balance is 100
-- T1: Transfer 1: A → B, $80
UPDATE wallet SET balance = balance - 80 WHERE user_id = 'A' AND balance >= 80;  -- succeeds
-- T2: Transfer 2: A → C, $80
UPDATE wallet SET balance = balance - 80 WHERE user_id = 'A' AND balance >= 80;  -- fails (balance now 20)
```

This is correct. But the **application logic** that decides "this user has enough" must use the same check, not a separate `SELECT`. The pattern:

```python
# WRONG: TOCTOU race
balance = db.query("SELECT balance FROM wallet WHERE user_id = 'A'")  # read
if balance >= amount:
    db.execute("UPDATE wallet SET balance = balance - ? WHERE user_id = 'A'", amount)  # write

# RIGHT: conditional update
result = db.execute(
    "UPDATE wallet SET balance = balance - ? WHERE user_id = 'A' AND balance >= ?",
    amount, amount
)
if result.rowcount == 0:
    raise InsufficientFunds()
```

The first is a textbook Time-Of-Check-To-Time-Of-Use (TOCTOU) bug. The second uses the database to serialize the check and the write.

### Pitfall 4 — Event sourcing without determinism

Event sourcing works **only if the state machine is deterministic**. A state machine that uses `datetime.now()` or `random.random()` or calls an external API during event application is **not deterministic**, and the system's reproducibility guarantee is broken. Two replicas applying the same event sequence will diverge.

The discipline: **resolve all nondeterminism in the command**, before the event is generated. The event carries resolved values (a specific timestamp, a specific ID, a specific external result). The state machine consumes only the event.

### Pitfall 5 — Snapshots that don't capture the in-memory state correctly

A snapshot is a checkpoint of the state machine. If the snapshot is taken concurrently with event application, the snapshot may capture a state that **does not correspond to any prefix of the event log**. On recovery, the replay produces a different state than the snapshot, and the bug is subtle.

The discipline:

- **Pause event application** (e.g., drain the in-memory queue).
- Take the snapshot.
- Capture the last-applied sequence number with the snapshot.
- Resume event application.

Or use a **copy-on-write** state with a single global version number; the snapshot is a consistent view at version V.

### Pitfall 6 — Overdraft logic that only checks the sender

```python
# WRONG: only checks sender
if sender.balance >= amount:
    debit(sender, amount)
    credit(receiver, amount)

# Edge case: receiver's account is frozen
# Edge case: receiver's currency doesn't match
```

A complete transfer check must verify:

- Sender has sufficient balance.
- Sender's account is in a valid state (not frozen, not closed).
- Receiver's account is in a valid state.
- Currency matches (or a valid FX rate is in place).
- Both accounts are within the same regulatory jurisdiction (if applicable).

### Pitfall 7 — In-memory state without memory bounds

An in-memory state machine holding all wallets needs to fit in RAM. At 1B wallets × 200 bytes = 200 GB. Plus event log buffering, plus projection materialization. A typical high-memory node has 1–2 TB; a 1B-wallet deployment needs sharding by design.

The pitfall is forgetting to **cap the state machine's working set** and ending up with an out-of-memory crash under load. The mitigation: **shard from day one**, with the shard count chosen for the projected 12-month wallet count, not the current count.

### Pitfall 8 — Saga compensations that don't exist or aren't tested

A saga's value is in its compensations. The pitfall is shipping a saga with steps that **look** correct but whose compensations are:

- Unimplemented ("we'll add it later").
- Not idempotent (a retried compensation over-applies).
- Not tested in production-like conditions.

The fix: **define the saga and its compensations together**. A step without a compensation is not a saga step; it's a partial implementation. Test compensations explicitly: simulate a failure at each step and verify the system recovers to a consistent state.

### Pitfall 9 — Forgetting to handle the "log is corrupted" case

The append-only log is the source of truth. What if it's corrupted? Two defenses:

1. **Replication**: 3+ replicas via Raft/Paxos. A single corrupted node is replaced; the others have the correct data.
2. **Checksums**: every entry carries a checksum; the projector verifies on replay. A corrupted entry is detected, and the projector can fall back to a snapshot.

The pitfall is to assume "the log can't be corrupted" because the storage is reliable. Disk corruption, bugs in serializers, and human error are all real.

### Pitfall 10 — Confusing "the wallet is empty" with "the wallet is closed"

A user with $0 in their wallet is not the same as a user whose account is closed. The former can receive funds; the latter cannot. The state machine must distinguish:

- `ACTIVE`: normal wallet, can debit and credit.
- `FROZEN`: cannot debit (regulatory hold), can credit.
- `CLOSED`: cannot debit or credit; the balance must be $0.

A saga that doesn't check the receiver's state may attempt to credit a closed wallet. The system must have a well-defined behavior for this: reject the transfer, or refund the sender. Either is fine; not handling it is not.

---

## Interview Q&A

### Q1 — "Walk me through what happens when a user transfers $100 to another user."

The expected answer:

1. **Client** generates a transfer request with a `txn_id` (UUID), `from_user`, `to_user`, `amount`.
2. **API edge** authenticates, rate-limits, and forwards to the wallet service.
3. **Wallet service** validates: `from_user` exists, has balance, not frozen; `to_user` exists, not closed; `amount` > 0; currency matches.
4. **Idempotency check**: if `txn_id` was already processed, return the stored result.
5. **Sharding**: route the transfer to the shard handling `from_user` (or to a coordinator if cross-shard).
6. **Saga (if cross-shard)**:
   - Try: debit `from_user` (reserve $100). Emits `BalanceReserved(from, $100)`.
   - Try: credit `to_user` ($100). Emits `BalanceCredited(to, $100)`.
   - Confirm: commit both. Emits `BalanceDebited(from, $100)` and `BalanceCommitted(to, $100)`.
   - On failure at any step, Cancel idempotently.
7. **Event log** (Kafka) is appended with all events, ordered by sequence number.
8. **Read projection** updates the in-memory balance view (Redis) and the history view (ClickHouse).
9. **API returns 202 Accepted** with the `txn_id`. The user polls for status or receives a push.

Total latency: ~10–50 ms. Throughput per shard: ~1M events/sec. The transfer is **strongly consistent within a shard** and **eventually consistent across shards** (typically < 100 ms).

### Q2 — "How do you handle a node crash mid-transfer?"

Three cases:

1. **Crash before the event is appended to the log**: the transfer never happened. The user's `txn_id` is unknown to the system. A retry from the client with the same `txn_id` is a fresh transfer. **No data loss.**

2. **Crash after append, before confirm**: the log has `BalanceReserved`. On recovery, the state machine replays the log. The reservation is still there. The system runs the saga's recovery: if both Trys are in the log, run Confirm; if only one is, run Cancel on the other. **Idempotent saga recovery.**

3. **Crash after confirm, before projection updates**: the in-memory state has the new balance; the projection does not. The system rebuilds the projection from the log on restart. **No data loss; the projection converges.**

In all three cases, the **append-only log is the contract**. As long as the log is correct, the system is correct.

### Q3 — "How would you scale to 10x — 10M TPS?"

The single-shard state machine hits ~1M events/sec. 10x is 10x the shards. With 1B wallets, that's 10,000 shards, each handling 1,000 TPS — easy. The new concerns:

1. **Shard count** increases the cross-shard transfer rate. With 10,000 shards, 99.99% of transfers are cross-shard. Saga overhead grows.
2. **Snapshot/recovery** time grows linearly with state size per shard. With more shards, snapshotting is parallel, so wall-clock time stays similar.
3. **Replica count** for the consensus log grows. Each Raft group has 3–5 nodes; 10,000 shards × 3 replicas = 30,000 nodes. That's a real ops burden.

The next architectural shift: **regional sharding** (US, EU, APAC) so each region has its own Raft cluster; cross-region transfers are eventual-consistency via an inter-region event bus.

### Q4 — "Why event sourcing over a sharded RDBMS with strong consistency per shard?"

The answer depends on the read patterns:

- **RDBMS sharding** is sufficient when the read patterns are "give me the current balance" and "give me my last N transactions." Both are single-shard queries.
- **Event sourcing** becomes necessary when:
  - You need **arbitrary historical queries** ("show me A's balance on March 1, 2024, at 14:23 UTC").
  - You have **many diverse read consumers** (analytics, fraud, ML) that benefit from a single log.
  - **Regulatory requirements** demand complete reproducibility.

For a PayPal-style wallet serving 10k TPS, the RDBMS approach is simpler and sufficient. For an Alipay-style system at 100k+ TPS with regulatory demands, event sourcing is the right answer.

### Q5 — "How do you ensure exactly-once transfer application?"

Same answer as the payment system: **at-least-once delivery + idempotent receivers**.

In event sourcing, idempotency is **built in** because the state machine keeps a set of applied `txn_id`s. An event with a duplicate `txn_id` is dropped on the floor. The dedup set is small (just the recent events' IDs), and it can be checked in O(1) per event.

The "exactly-once" property here is **per-txn** (a given `txn_id` is applied at most once), not **per-event** (an event may be delivered multiple times; only the first delivery has effect). This is the practical definition that matters.

### Q6 — "What if a user disputes a transfer after the fact? How does the event-sourced system support a chargeback?"

The event log is the perfect support for a chargeback investigation:

1. **Replay the log** for the user to compute their balance at any historical point.
2. **List all events** with timestamps and originating saga IDs.
3. **Identify the disputed event** by `txn_id` and inspect its full chain of cause and effect.

A chargeback is a **new event** (`BalanceDebited, $100, reason=chargeback`) that is appended to the log. It does not modify prior events; it adds a new one. The new event's effect propagates through the projections. The audit trail is complete: every prior event, plus the chargeback, with no data loss or tampering.

This is the **reproducibility** property of event sourcing in action — what auditors and finance teams actually want.

### Q7 — "How would you handle a regulatory freeze on a user's wallet?"

A regulatory freeze is a state change on the wallet, not a balance change. The state machine has multiple state dimensions:

- `BALANCE`: integer.
- `STATUS`: ACTIVE / FROZEN / CLOSED.
- `REGULATORY_HOLD`: amount frozen (can be a subset of balance).

A freeze command (`FreezeWallet(user_id, reason, regulator_id)`) appends an event. The state machine processes it: sets `STATUS = FROZEN` and records the regulator and reason. Subsequent transfer commands are rejected by the state machine (insufficient permissions given the status).

The projection sees the new event and updates the read view. The user sees their wallet as "frozen" with the regulator's name and the date. A subsequent `UnfreezeWallet` event reverses the status change.

The event log has the full history of freezes and unfreezes — exactly what a regulator would request in an audit.

---

## Key Terms / Glossary

| Term | Definition | Common misconception |
|------|------------|----------------------|
| **Wallet** | A user's balance and account metadata; the user-facing surface of a value-holding system. | "It's a database row" — a wallet is a logical concept; the storage may be a row, an in-memory state, or a derived projection. |
| **Balance** | The current amount in a wallet. In event-sourced systems, derived from the log; in RDBMS, a column. | "It's the source of truth" — the log is the truth; the balance is a projection. |
| **Ledger** | The append-only record of all money movements. The system's source of truth. | "It's the same as the transaction history" — the ledger is the journal; history is a read view of the ledger. |
| **Event sourcing** | Architectural pattern: state changes are appended as immutable events; current state is a fold of events. | "It's a queue" — a queue is for transport; event sourcing is the data model. The log is the database. |
| **State machine** | Deterministic function: given current state + event, produce next state. The core of an event-sourced system. | "It's where the business logic lives" — the state machine applies events; the business logic generates them. |
| **Determinism** | Property: same inputs always produce the same outputs, on any replica, at any time. Required for replay and replication. | "It's about avoiding randomness" — it's also about avoiding timestamps, external calls, and uninitialized state. |
| **Snapshot** | A persisted checkpoint of the state machine's current state. Bounded-replay recovery. | "It replaces the log" — the log is still the truth; the snapshot is a fast-start optimization. |
| **CQRS** | Command-Query Responsibility Segregation: separate the write model from the read model. | "It's the same as event sourcing" — they're complementary; CQRS without event sourcing is possible (e.g., a denormalized read table). |
| **2PC (Two-Phase Commit)** | Distributed transaction protocol with a coordinator; all-or-nothing across participants. | "It's the only way to be consistent" — 2PC is one way; saga is another, eventually consistent. |
| **Saga** | Sequence of local transactions with compensations. Eventually consistent, no global locks. | "It's a hack" — saga is a deliberate trade-off; high availability over strong consistency. |
| **TCC (Try-Confirm-Cancel)** | Application-level distributed transaction with explicit reservation semantics. | "It's a special case of 2PC" — TCC has no coordinator; each service implements its own Try/Confirm/Cancel. |
| **Idempotency** | Operation has the same effect whether applied once or many times. | "It's the same as dedupe" — dedupe is a mechanism; idempotency is the property. |
| **Idempotency key** | Unique ID on a logical operation; de-duplicates retries. | "It's a UUID" — it's an opaque identifier that the client generates once and reuses on retry. |
| **Append-only log** | Data structure where entries are only added, never modified or deleted. The basis of event sourcing. | "It's the same as a database" — append-only logs are typically not relational; the read model is derived. |
| **Raft / Paxos** | Consensus protocols for replicating a log across nodes with a majority quorum. | "They're the same" — Paxos is the more general algorithm; Raft is a more understandable subset. |
| **Group commit** | Batching multiple log writes into a single fsync. Improves throughput at small latency cost. | "It's a hack" — group commit is the standard pattern for high-throughput durable logs. |
| **Recovery / replay** | Rebuilding state by applying events from a snapshot plus the tail of the log. | "It's a backup strategy" — it's a primary correctness strategy, not just disaster recovery. |
| **Cross-shard transfer** | A transfer where source and destination are in different shards. Requires saga, TCC, or 2PC. | "It's the same as cross-region" — cross-region implies cross-shard, but cross-shard doesn't require cross-region. |
| **RDBMS ACID** | Atomicity, Consistency, Isolation, Durability — the four guarantees of a single relational database transaction. | "It scales linearly" — single-RDBMS write throughput is bounded by the node; scaling requires sharding, which breaks ACID across shards. |
| **Compensation** | A local transaction that undoes a prior local transaction's effect. The reverse step in a saga. | "It's a rollback" — rollback is a DB primitive; compensation is an application-level undo that may involve new business logic. |
| **Wallet status** | A separate dimension from balance: ACTIVE, FROZEN, CLOSED. Determines whether transfers are allowed. | "Frozen = balance 0" — frozen means transfers blocked, not balance zero. A frozen wallet can still have a non-zero balance. |
| **Tokenization (wallet context)** | Replacing the user's actual credential (card PAN, account number) with a token that has limited scope. | "It hides the data" — it limits the data's usefulness if stolen, but the token-to-PAN mapping must still be protected. |
| **Secure Element (SE)** | Tamper-resistant hardware chip on a device that stores credentials and performs crypto. | "It's the same as HCE" — SE is hardware; HCE is software emulation of the SE. |
| **HCE (Host Card Emulation)** | Software-based tokenization where the device emulates a contactless card without a secure element. | "It's less secure" — HCE relies on the network's token vault; SE is device-local. The threat model differs. |
| **DAN (Device Account Number)** | Tokenized card number used by Apple Pay / Google Pay instead of the real PAN. | "It's encrypted" — it's a token, not an encryption. The PAN-to-DAN mapping is held by the issuer or the network. |
| **Cryptogram (dynamic CVV)** | A per-transaction code generated by the secure element, replacing the static CVV. | "It's a one-time password" — it's a per-transaction cryptogram; the bank verifies it, not the user. |
| **Wallet service** | The system that owns wallet state and orchestrates transfers. | "It's the API" — the service is the brain; the API is the entry point. |
| **State store** | The store holding the current state of the state machine — typically in-memory for speed, with a snapshot for durability. | "It's a cache" — it's the working state, with explicit snapshotting for recovery. |
| **Read model / projection** | A query-optimized view derived from the event log. | "It's a database" — it's a derived view; rebuilding it from the log is a defined operation. |
| **Read-your-writes consistency** | Property: after a client writes, the same client can immediately read the new value. | "It's the same as strong consistency" — RYW is a specific guarantee; strong consistency is broader. |
| **Idempotent state machine** | A state machine that, given the same event sequence, produces the same state regardless of duplicate events. | "It requires dedup tables" — it requires tracking applied IDs, but the storage can be a Bloom filter, a compact hash, or a sliding window. |
| **Wallet sharding key** | The field used to partition wallets across shards (typically `user_id` or `account_id`). | "It must be user_id" — any field with high cardinality and even distribution works; user_id is just the most common. |
| **Hot wallet** | A wallet that holds a large balance and is frequently used. Subject to extra security controls. | "It's the same as a regular wallet" — hot wallets are the highest-value targets; they need stricter auth, withdrawal delays, and monitoring. |
| **Cold wallet** | A wallet that holds funds in long-term storage (often offline). | "It's slower" — it's deliberately slow and isolated; the trade-off is security over convenience. |
| **Fiat wallet** | A wallet holding government-issued currency (USD, EUR, JPY). | "It's the only kind" — there are also crypto wallets (BTC, ETH), stablecoin wallets (USDC), and central-bank-digital-currency wallets (CBDC). |
