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
