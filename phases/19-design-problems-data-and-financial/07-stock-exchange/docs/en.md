# Design a Stock Exchange

A stock exchange matches buyers and sellers of securities. It is one of the most demanding latency- and correctness-sensitive systems in existence: orders must match **fairly**, **deterministically**, and in **microseconds**, while the system stays auditable and recoverable. The crown jewel is the **matching engine** operating on an **order book**.

---

## Step 1 — Understand the Problem and Scope

### Functional requirements

- Accept **orders**: place, cancel, and (sometimes) modify.
- Support **order types**: at minimum **limit orders** (buy/sell at a specified price or better) and **market orders** (execute immediately at best available price).
- **Match** orders via a matching engine and an order book per symbol.
- Run **risk checks** (buying power, position limits, validity) before an order enters the book.
- Publish **executions** (fills) back to clients and a **market data feed** (order book updates, trades) to participants.
- Persist everything for **audit, recovery, and reproducibility**.

### Non-functional requirements

- **Ultra-low latency**: matching in microseconds; latency *determinism* (predictable tail latency) often matters more than raw average.
- **High throughput**: hundreds of thousands to millions of orders/second at peak.
- **Determinism & fairness**: given the same input sequence, the engine always produces the same output (price-time priority). No participant is unfairly advantaged.
- **Durability & recoverability**: every order/event is persisted; the engine can be rebuilt exactly after a crash.
- **High availability**: trading halts cost millions.
- **Correctness**: no lost, duplicated, or out-of-order matches.

### Back-of-the-envelope estimation

- Peak: assume ~**1,000,000 orders/sec** across the exchange at busy moments.
- Latency budget: **tens of microseconds** end-to-end inside the matching path.
- These numbers force the core to be **in-memory**, **single-threaded per symbol**, and free of network/disk in the hot path.

---

## Step 2 — High-Level Design

### Components and order lifecycle

```
Client ─FIX─► Gateway ─► Order Manager ─► Risk Check ─► Sequencer ─► Matching Engine
                                                                          │
                                                            ┌─────────────┼──────────────┐
                                                            ▼             ▼              ▼
                                                       Executions    Market Data    Event Store
                                                        (to client)    Feed          (persist)
```

1. **Client gateway** — terminates client connections, typically speaking the **FIX protocol** (or a binary variant). Parses and normalizes orders.
2. **Order manager** — tracks order state (new, partially filled, filled, canceled, rejected).
3. **Risk / pre-trade checks** — buying power, position/credit limits, price collars, fat-finger checks. Reject before the order reaches the book.
4. **Sequencer** — assigns a single, monotonically increasing global sequence number to every inbound event, imposing **one canonical order** on all events.
5. **Matching engine** — the core. Maintains the order book per symbol and matches orders deterministically.
6. **Market data publisher** — broadcasts trades and order-book changes to participants.
7. **Event store** — durably records the ordered event stream for persistence, audit, and recovery (event sourcing).

### The order book

A per-symbol data structure holding all **resting** (unmatched) orders:

- Two sides: **bids** (buy orders, sorted by price descending) and **asks** (sell orders, sorted by price ascending).
- Within a price level, orders are ordered by arrival time — this is **price-time priority** (a.k.a. FIFO at each price).
- The **best bid** (highest buy) and **best ask** (lowest sell) form the top of book; the gap between them is the **spread**.

Common implementation: an array/map of **price levels**, each level holding a FIFO queue of orders. Price levels are kept in sorted order so the best price is O(1) to read. Cancels need fast lookup, so an `order_id → location` index is maintained alongside.

### Matching rules

- **Limit buy** at price P matches any resting ask with price ≤ P, cheapest first, until filled or no more eligible asks; remainder rests in the book.
- **Limit sell** at price P matches resting bids ≥ P, highest first; remainder rests.
- **Market order**: match against the best available prices immediately, walking the book until filled (or until liquidity runs out). It never rests.
- Each match produces a **trade/fill** at the resting (passive) order's price (price improvement for the aggressor).
- Partial fills are normal: a large order may match several smaller resting orders.

---

## Step 3 — Deep Dive

### Determinism and the sequencer

Fairness and reproducibility demand that the matching engine be **deterministic**: the same ordered input always yields the same trades.

- The **sequencer** is the linchpin. It takes all inbound events (new orders, cancels) from multiple gateways and stamps each with a **global, monotonic sequence number**, producing a single total order.
- Downstream, the matching engine consumes this ordered stream **single-threaded per symbol**. No locks, no thread scheduling nondeterminism, no race conditions — just a deterministic function of the input sequence.
- Because the engine is a deterministic state machine over an ordered log, you can **replay** the log to rebuild exact state, run **hot/warm standby** replicas that stay bit-for-bit identical, and **verify** behavior offline.

This is essentially **state-machine replication**: ship the same sequenced log to replicas; each independently reaches identical order-book state.

### Why single-threaded in-memory wins

It feels counterintuitive, but a **single-threaded, in-memory** matching engine outperforms a multithreaded one here:

- No lock contention, no cache-line bouncing between cores, no nondeterministic interleavings.
- The entire order book fits in RAM and in CPU cache; matches are pointer/array operations measured in nanoseconds.
- Determinism is preserved for free.
- Parallelism is achieved **across symbols** (shard symbols to different engine instances/cores), not within a symbol.

### Low-latency engineering

To hit microsecond latencies, the hot path avoids everything slow:

- **Keep the matching path in memory**; no synchronous disk or network I/O inside it.
- **Mechanical sympathy**: cache-friendly data structures, preallocated object pools, **no garbage collection pressure** (off-heap or zero-allocation steady state), avoid pointer chasing.
- **Lock-free ring buffers** (e.g., the LMAX Disruptor pattern) to pass events between stages without locks.
- **Kernel bypass networking** (DPDK, Solarflare/OpenOnload), busy-polling instead of interrupts.
- **Binary protocols** over FIX-text on the fast path; pin threads to cores; disable power-saving/CPU frequency scaling.
- Optimize for **tail latency / jitter**, not just mean — predictable 99.99th percentile matters more than average to traders.

### Persistence and event sourcing

We cannot afford to lose orders or let state diverge, yet we can't block matching on disk writes. The reconciliation:

- The **sequenced event stream is the source of truth** and is persisted (event sourcing). Current order-book state is a **deterministic fold** of these events.
- Persist via **sequential append** (fast), often with **batched/group commit** and replication to standbys *off* the critical matching path or pipelined so latency stays low.
- **Snapshots** of order-book state are taken periodically so recovery doesn't replay from the beginning — restart = load latest snapshot + replay the tail of the log.
- Recovery and the existence of an immutable, ordered log give **reproducibility** and a complete **audit trail** (regulators require this).

### Risk checks (pre-trade)

Risk runs **before** an order reaches the book so a bad order never matches:

- **Buying power / credit**: does the account have funds/margin?
- **Position & exposure limits.**
- **Price collars / fat-finger**: reject orders absurdly far from the market.
- **Order validity**: symbol exists, size/lot valid, market open.

These must be fast (they're in the latency path) but conservative; rejected orders never touch the matching engine.

### FIX protocol

**FIX (Financial Information eXchange)** is the industry-standard messaging protocol for orders and executions:

- Tag-value encoded messages: `NewOrderSingle`, `ExecutionReport`, `OrderCancelRequest`, etc.
- Session layer handles sequencing, heartbeats, and gap-fill/resend for reliability.
- Many exchanges accept FIX at the gateway but translate to a compact **binary internal format** for the low-latency core, and offer binary feeds (e.g., ITCH/OUCH-style) for the fastest participants.

### Market data feed

After matching, the exchange disseminates data:

- **Trade feed**: executed trades (price, size, time).
- **Order book / depth feed**: changes to bid/ask levels (full depth or top-of-book).
- Delivered via **low-latency multicast** so all subscribers receive updates simultaneously (fairness).
- Tiered products: ultra-low-latency direct feeds vs. consolidated/delayed public feeds.
- Must be **deterministic and ordered**, derived from the same sequenced event stream the engine uses.

### Performance optimization summary

| Technique | Why |
|-----------|-----|
| In-memory order book | Avoid disk seeks in hot path |
| Single-threaded per symbol | No locks, deterministic, cache-hot |
| Shard across symbols | Parallelism without losing per-symbol determinism |
| Sequencer / total order | Determinism, fairness, replay |
| Lock-free ring buffers (Disruptor) | Low-latency inter-stage handoff |
| Kernel-bypass networking | Cut syscall/interrupt overhead |
| Zero-allocation / no GC | Avoid pause-induced jitter |
| Event sourcing + snapshots | Durability, audit, fast recovery |
| Batched/replicated log off hot path | Durability without latency cost |

---

## Step 4 — Wrap Up

### Key takeaways

- The heart is a **deterministic matching engine** over a per-symbol **order book** using **price-time priority**.
- A **sequencer** imposes a single total order on all events, which makes the engine a deterministic state machine — enabling **reproducibility, replication, and audit**.
- Run the engine **single-threaded and in-memory per symbol**; get scale by **sharding across symbols**, not threading within one.
- **Ultra-low latency** comes from keeping the hot path free of disk/network, lock-free handoffs, kernel-bypass networking, and zero-GC discipline — and from optimizing **tail latency / jitter**.
- **Limit vs market orders**: limits rest in the book at a price; markets sweep the book immediately.
- **Risk checks** run pre-trade so bad orders never match.
- **FIX** is the standard client protocol; the internal core uses compact binary formats.
- Durability and recovery use **event sourcing** (sequenced log as source of truth) plus **snapshots**; the **market data feed** is derived from that same ordered stream and multicast for fairness.

### Common follow-ups

- **Failover**: hot standby replicas consuming the same sequenced log; promote on failure with no state divergence.
- **Auctions** (open/close): batch matching at a single clearing price rather than continuous matching.
- **Self-trade prevention**, iceberg/hidden orders, stop orders — extensions layered on the same engine.
- **Clearing & settlement** happen downstream (T+1/T+2); the exchange's job ends at the match/execution report.
