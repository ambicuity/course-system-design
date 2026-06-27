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

---

## Back-of-the-Envelope Math (Extended)

### Throughput math

A single modern exchange's typical day, broken down:

- **US equities volume (NYSE + Nasdaq + other)**: ~10–15 billion shares/day, ~3–5 million trades/day (one trade ≈ 200–500 shares). Across ~3,000 listed symbols.
- **Peak order rate**: during the open and close auctions, an exchange can see hundreds of thousands of orders per second.
- **Per-symbol peak**: a hot symbol (SPY, AAPL, NVDA) at peak can see 50,000+ orders/second.

For a design interview, "1M orders/sec" is a fair assumption for a top-tier exchange at peak. The math:

- 1,000,000 orders/sec ÷ 3,000 symbols = ~333 orders/sec/symbol average.
- Hot symbols: 50,000/sec/symbol.
- A single-threaded matching engine handles 1M+ orders/sec on commodity hardware for typical workloads (limit orders at top of book); a hot symbol's 50k/sec is comfortable.
- Across 3,000 symbols × 1M/sec/symbol = 3 billion orders/sec, you'd need horizontal sharding by symbol group.

### Latency math, broken down

A "wire-to-wire" latency budget from client send to client receive on a fill:

| Stage | P50 | P99 | Why |
|-------|-----|-----|-----|
| Network: client → gateway | 1–10 µs | 5–20 µs | Co-located, kernel bypass |
| Gateway parse + validate | 1 µs | 3 µs | Pre-compiled FIX parser, hot path |
| Risk check | 0.5 µs | 2 µs | In-memory account state |
| Sequencer | 0.5 µs | 2 µs | Single-threaded FIFO |
| Matching engine (match + emit) | 0.5–2 µs | 5–10 µs | Single-threaded, hot in L1/L2 cache |
| Market data fan-out | 1 µs | 5 µs | Multicast, kernel bypass |
| Network: gateway → client | 1–10 µs | 5–20 µs | Same as above |
| **Total wire-to-wire** | **~5–25 µs** | **~25–65 µs** | |

A 2020s HFT shop typically reports **3–10 µs wire-to-wire** to the exchange's matching engine, with sub-µs internal matching. Compare to a 2010s system: ~50–100 µs. Compare to 2000s: 1–10 ms. The trend is one order of magnitude per decade, driven by kernel-bypass networking, faster CPUs, and tighter code.

### Storage math, per symbol

For a hot symbol (AAPL):

- Order book at any time: 100,000 resting orders, ~50,000 on each side.
- Each order in memory: ~256 bytes (order_id, price, size, timestamp, account_id, status, location pointers).
- Order book memory: 100,000 × 256 = 25.6 MB.
- Event log per day (orders + cancels + trades): 50,000 ops/sec × 6.5 hours × 3,600 = 1.17 billion events/day. At 100 bytes/event, 117 GB/day. **The log is the dominant storage cost.**
- 7-year retention: 117 GB × 252 trading days × 7 = 206 TB. Per symbol.

For 3,000 symbols, this scales. The exchange spends more on log storage than on order book memory.

### Network math

Market data fan-out at peak:

- 1,000,000 orders/sec × ~3 events per order (new + book update + trade) = 3M events/sec.
- Average event size: 50 bytes.
- Throughput: 150 MB/sec outbound. Easy for a 10 Gbps NIC (which carries ~1.2 GB/sec).
- **The constraint is connection count, not bandwidth.** A 10 Gbps NIC can handle 10,000+ market-data subscribers; the exchange's connection-tiering (direct, consolidated, public) keeps individual subscribers in their own pipe.

### Order book data structure math

Common implementations:

- **Array of price levels, each a doubly linked list of orders**: O(1) best-price read; O(1) add/remove at a level; O(log P) for price level lookup (P = number of distinct prices). Fast for liquid symbols; P is small (~10–1000) so a sorted array is fine.
- **Hash map of price → list, plus a min/max heap**: O(1) best-price read; O(log P) for level operations. Slower than the array for the common case but more flexible.
- **Tree of orders (red-black or similar)**: O(log N) for all operations. Slowest, but works for very deep books.

The "two-skip-list" approach used by LMAX and others (one for bid side, one for ask side) is the gold standard for O(1) best-price + O(log N) level operations. The `order_id → (side, price, position-in-list)` index is a separate hash map for cancel-by-id.

### The 0.001% tail

For HFT, the latency target is **not the P50**. It's the P99.99 — the worst 0.01% of orders. A trader submitting 1,000 orders/sec sees 1 outlier per second at P99.9, and 1 per 10 seconds at P99.99. If those outliers happen during a market-moving event, the trader loses money.

The exchange's job is to make the **P99.99 / P50 ratio** as close to 1 as possible. This is the "latency determinism" goal. A typical exchange reports:

- P50: 5 µs
- P99: 8 µs
- P99.9: 15 µs
- P99.99: 30 µs

The ratio P99.99 / P50 = 6×. A poorly-tuned system can show 50× or worse, with a long tail of GC pauses, network retransmissions, and cache misses.

---

## ASCII Architecture Diagrams

### Diagram 1 — Order-to-fill sequence diagram

```
  Client       Gateway      Risk      Sequencer    Matching      Market Data    Event Log
                (FIX)       Check                    Engine         Publisher
    │            │            │           │             │              │              │
    │  NewOrder  │            │           │             │              │              │
    │  Single    │            │           │             │              │              │
    │  (FIX)     │            │           │             │              │              │
    │───────────►│            │           │             │              │              │
    │            │  parse +   │           │             │              │              │
    │            │  validate  │           │             │              │              │
    │            │            │           │             │              │              │
    │            │  risk      │           │             │              │              │
    │            │  check     │           │             │              │              │
    │            │───────────►│           │             │              │              │
    │            │            │  OK       │             │              │              │
    │            │            │  (or Reject)            │              │              │
    │            │◄───────────│           │             │              │              │
    │            │            │           │             │              │              │
    │            │  assign seq_no=N       │             │              │              │
    │            │───────────────────────►│             │              │              │
    │            │            │           │  enqueue event            │              │
    │            │            │           │  (order, seq=N)            │              │
    │            │            │           │─────────────►             │              │
    │            │            │           │             │              │              │
    │            │            │           │             │  match       │              │
    │            │            │           │             │  (in-memory) │              │
    │            │            │           │             │              │              │
    │            │            │           │             │  emit fill   │              │
    │            │            │           │             │─────────────►│              │
    │            │            │           │             │              │              │
    │            │            │           │             │  append event │              │
    │            │            │           │             │  (seq=N, fill)              │
    │            │            │           │             │─────────────────────────────►
    │            │            │           │             │              │              │
    │            │            │           │             │  publish     │              │
    │            │            │           │             │  trade+book  │              │
    │            │            │           │             │              │  multicast  │
    │            │            │           │             │              │─────────────►
    │            │            │           │             │              │              │
    │            │  ExecutionReport        │             │              │              │
    │            │◄─────────────────────────────│             │              │              │
    │            │            │           │             │              │              │
    │  fill ack  │            │           │             │              │              │
    │◄───────────│            │           │             │              │              │
```

The hot path (gateway → sequencer → matching engine → market data) is **in-memory and single-threaded per symbol**. The persistence (event log) is **out of band, pipelined**, with the engine continuing to match while the log is being written.

### Diagram 2 — Per-symbol matching engine internals

```
  Sequenced Input (per symbol S)
        │
        │   ring buffer
        ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Single-threaded matching loop (one core pinned)         │
  │                                                         │
  │  for each event:                                        │
  │    match(event)                                         │
  │      if event is BUY:                                   │
  │        while price <= best_ask AND qty > 0:             │
  │          fill at best_ask.price (passive order's price) │
  │          emit Fill(taker, maker, qty, price, seq)       │
  │        if qty remaining:                                │
  │          rest in book at event.price                    │
  │      if event is SELL:                                  │
  │        while price >= best_bid AND qty > 0:             │
  │          fill at best_bid.price                         │
  │          emit Fill                                      │
  │        if qty remaining:                                │
  │          rest in book at event.price                    │
  │      if event is CANCEL:                                │
  │        look up order_id, remove from book, emit Cancel  │
  │      if event is MODIFY:                                │
  │        (lose-time-priority or keep, exchange-specific) │
  │                                                         │
  │  append events to log (off hot path, pipelined)         │
  └─────────────────────────────────────────────────────────┘
        │
        ▼
  Order book (in-memory)
    bid side:                              ask side:
      ┌──────┐ 100.05  ← best_bid           best_ask → 100.06 ┌──────┐
      │ o_a  │                                o_x              │
      │ o_b  │                                o_y              │
      ├──────┤ 100.04                          100.07 ┌──────┤
      │ o_c  │                                o_z              │
      │ o_d  │                                              │
      └──────┘                                              └──────┘
```

The matching loop is the entire engine. It runs in microseconds per event. The bid/ask sides are separate data structures (often two skip lists). The best bid/ask is the head of each side.

### Diagram 3 — Sequencer as a single total-order bottleneck

```
                 Gateway A
                    │
                 Gateway B  ──┐
                    │        │
                 Gateway C  ──┤
                             │
                             ▼
                  ┌──────────────────────┐
                  │   Sequencer          │
                  │   (single thread,    │
                  │    one core pinned)  │
                  │                      │
                  │   incoming → seq     │
                  │   1, 2, 3, 4, ...    │
                  └──────────┬───────────┘
                             │
                  ┌──────────┼──────────┬──────────┐
                  ▼          ▼          ▼          ▼
              Symbol X   Symbol Y   Symbol Z   Symbol W
              (shard)    (shard)    (shard)    (shard)
              (single    (single    (single    (single
              thread)    thread)    thread)    thread)
```

The sequencer is the **single total-order bottleneck** for the exchange. Every event flows through it. This is deliberate: it provides:

- **Fairness**: events from different clients are ordered by arrival, not by which gateway processed first.
- **Determinism**: a single ordered stream is fed to all replicas; all replicas apply the same sequence and reach the same state.
- **Replay**: the sequenced log is the source of truth for audit and recovery.

The sequencer's throughput is the exchange's aggregate throughput. A modern sequencer handles 1M+ events/sec on one core. To scale beyond that, you **partition by symbol group** — each partition has its own sequencer, and ordering is preserved within a partition (which is what fairness requires).

### Diagram 4 — Replication and failover (hot standby)

```
  Primary                                          Hot Standby
  ┌────────────────────────┐                      ┌────────────────────────┐
  │ Sequencer             │                      │ (idle, listening)      │
  │ Matching engine S1    │                      │                        │
  │ Matching engine S2    │                      │ Matching engine S1'    │
  │ Matching engine S3    │                      │ Matching engine S2'    │
  │ Event log (writes)    │─── replicated log ──▶│ Event log (replica)    │
  └────────────────────────┘                      └────────────────────────┘
          │                                                ▲
          │         promote on failure                      │
          └────────────────────────────────────────────────►│
                                                           │
                                                   (standby takes over)
```

The standby consumes the same sequenced log. Because the matching engine is a deterministic function of the log, the standby's state is bit-for-bit identical to the primary's. On failure, the standby is promoted; clients reconnect to the new endpoint; no state divergence.

The promotion requires:

- **Heartbeat** from primary to standby (e.g., 1 ms).
- **Failure detection** (3 missed heartbeats = dead primary).
- **Quorum** (or primary-only with hot standby — see Chapter 30 for the trade-off).
- **Network cutover** (DNS or BGP).

Promotion time: ~50–500 ms in well-engineered systems. The exchange may halt trading during cutover, or run with degraded latency for a few hundred ms.

---

## Trade-off Tables

### Order book data structure

| Data structure | Best-price read | Add order | Cancel order | Memory | Best for |
|----------------|-----------------|-----------|--------------|--------|----------|
| Sorted array of price levels | O(1) | O(log P) | O(log P) | Low | Liquid symbols with few price levels |
| Skip list (per side) | O(1) | O(log N) | O(log N) | Medium | Default; large books |
| Hash map + heap | O(1) | O(log P) | O(log P) | Medium | Sparse books |
| B-tree of orders | O(log N) | O(log N) | O(log N) | High | Very deep, illiquid books |
| Two-stack (intrusive list) | O(1) | O(1) | O(1) | Low | LMAX-style, microsecond latency |
| Lock-free linked list | O(1) | O(1) | O(1) | Low | Hardest to make correct |

### Matching engine threading model

| Model | Throughput | Latency determinism | Determinism | Complexity |
|-------|-----------|---------------------|-------------|-----------|
| Single-threaded, one core per symbol | ~1M orders/sec/symbol | Best (P99 ≈ P50) | Perfect | Low |
| Multi-threaded, lock per price level | ~500k orders/sec/symbol | Worse (lock contention) | Hard (need careful ordering) | Medium |
| Actor model (per symbol as actor) | ~200k orders/sec | Good | Good (single-actor per symbol) | Medium |
| Disruptor pattern (LMAX) | ~10M events/sec/node | Excellent (lock-free) | Good (single producer) | Medium |
| FPGA / hardware-accelerated | ~10M+ orders/sec | Excellent | Hardware-dependent | Very high |

### Persistence model

| Approach | Hot-path latency impact | Durability window | Recovery time | Cost |
|----------|------------------------|--------------------|---------------|------|
| Sync fsync per event | + 1–10 ms per event | 0 events lost | Seconds | High disk IOPS |
| Group commit (e.g., 100 events / 1 ms) | + 1 ms batched | ≤ 1 ms of events | Seconds | Lower IOPS |
| Async write (pipelined) | + 0 (off hot path) | ≤ 100 ms of events | Seconds to minutes | Lowest IOPS |
| Replicated async (3 copies, async) | + 0 | 0 (with quorum) | Fast | High bandwidth |
| In-memory + periodic snapshot | + 0 | Snapshot window | Snapshot window replay | Lowest |

### Order types — exchange complexity vs trader value

| Order type | Engine complexity | Trader value | Most exchanges |
|------------|------------------|--------------|----------------|
| Market | Low (always matches) | High (urgency) | Yes |
| Limit | Low (standard) | High (price control) | Yes |
| Stop / stop-limit | Medium (triggers) | Medium | Yes |
| IOC (Immediate-or-Cancel) | Low | High | Yes |
| FOK (Fill-or-Kill) | Low | Medium | Yes |
| Iceberg (displayed + hidden) | Medium (display logic) | High for large orders | Most |
| Hidden | Low (don't display) | High for institutions | Most |
| Pegged (relative to NBBO) | Medium (NBBO feed) | High for market makers | Most |
| Reserve | Medium (displayed size) | High | Some |
| All-or-none | Low | Medium | Some |
| Auction-only | High (auction logic) | High at open/close | Yes |

### Connectivity / protocol tier

| Tier | Protocol | Latency | Cost | Participants |
|------|----------|---------|------|--------------|
| Direct feed, kernel bypass | Binary (ITCH/OUCH) | 1–5 µs | $10k+/month + colocation | HFT, market makers |
| Direct feed, TCP | Binary | 10–50 µs | $1k–10k/month | Active traders |
| FIX gateway | FIX (TCP) | 50–500 µs | $100–1k/month | Brokers, retail gateways |
| Public consolidated | SIP, delayed | Seconds | Free / low | Retail, public |
| Web / mobile | HTTP / WebSocket | 100 ms+ | Free | Retail, info sites |

### Order entry risk check placement

| Placement | What it catches | Latency cost | What it misses |
|-----------|----------------|--------------|----------------|
| At the gateway (in-line) | Fat-finger, invalid symbol, price collars | + 1–5 µs | Account-level (collateral, position) |
| At the risk engine (in-line, before sequencer) | Buying power, position limits, exposure | + 5–20 µs | Cross-symbol aggregated risk |
| At the matching engine (per-symbol) | Per-symbol market integrity (e.g., price bands) | + 0.5 µs | Account risk |
| Post-trade (out of band) | None in the hot path | 0 | All real-time risk; only for compliance |

### Failover / replication model

| Model | RPO (data loss) | RTO (downtime) | Cost | Complexity |
|-------|-----------------|----------------|------|------------|
| Cold standby (manual failover) | Snapshot window | Minutes to hours | $ | Low |
| Warm standby (async replication) | Sub-second | Seconds | $$ | Medium |
| Hot standby (sync replication) | 0 | Sub-second | $$$ | High |
| Active-active (multi-primary) | 0 | 0 | $$$$ | Highest |
| Geo-distributed (multi-region) | 0 | Sub-second | $$$$$ | Highest |

### Auction vs continuous trading

| Mode | How matching works | When | Why |
|------|---------------------|------|-----|
| Continuous (default) | Each order matches immediately against the book | Most of the day | Liquidity, fast price discovery |
| Opening auction | Single clearing price computed from order imbalance | 9:30 AM ET (NYSE) | Fair price discovery, no early advantage |
| Closing auction | Single clearing price | 4:00 PM ET (NYSE) | Reference price for benchmarks, mutual funds |
| Volatility auction (LULD) | 5-min pause if price moves > X% | Triggered | Cool-off to prevent cascades |
| IPO auction | Single price | Day 1 of trading | Initial price discovery |
| Halt / resume | No trading | News pending | Information dissemination |

### Settlement / clearing model

| Aspect | T+2 (legacy) | T+1 (current) | T+0 (future) |
|--------|--------------|---------------|--------------|
| Settlement window | 2 days | 1 day | Same day |
| Counterparty risk | Higher | Lower | Minimal |
| Capital efficiency | Lower | Better | Best |
| Margin / collateral | Higher | Lower | Lowest |
| Operational complexity | Lower | Medium | Higher |
| Real-world example | Pre-2024 US | US (May 2024+), EU | Pilot programs (some EU jurisdictions) |

---

## Real-World Case Studies

### NASDAQ's INET

NASDAQ's INET matching engine, in production since the mid-2000s and substantially re-architected in the 2010s, is the canonical example of a modern CLOB (central limit order book) at scale.

Reported design characteristics (from public SRE talks and patent disclosures):

- **In-memory** order book, single-threaded per symbol.
- **Linux-based**, with **kernel-bypass networking** (Solarflare OpenOnload, then Mellanox VMA) for sub-µs network latency.
- **Co-located** in Carteret, NJ (NASDAQ's primary data center) with HFT firms in adjacent cages.
- **Direct feeds** via the ITCH protocol (5 bytes per order-book update, push-based, multicast) and **OUCH** for order entry.
- **Sequencer** that assigns a single global sequence number; matching is purely a function of the ordered stream.
- **Hot standby** for failover; promotion within seconds.

NASDAQ handles ~10–20 billion shares/day across ~3,500 symbols, with peaks of millions of orders per second.

### NYSE's Pillar

NYSE migrated from the legacy UTP-Direct / NYSE-Order-Matching systems to the unified **Pillar** platform around 2016–2020. Pillar is the NYSE's modern CLOB, common across NYSE, NYSE Arca, NYSE American, and NYSE National.

Pillar's published design points:

- **Single code base** across all NYSE-owned exchanges — one matching engine, multiple exchange licenses.
- **In-memory** order book with **Linux kernel-bypass** networking.
- **Raft-based** replication for failover; sub-second RTO.
- **Common gateway** for FIX and proprietary protocols.

The Pillar migration is a case study in **re-platforming a regulated production system**: 4+ years of development, parallel running of legacy and new systems, regulator signoff at every stage, and zero-downtime cutover (literally, because a stock exchange cannot have downtime).

### LSE's Millennium

The London Stock Exchange's Millennium Exchange, in production since 2009 (with the MillenniumIT platform, acquired by LSE in 2009), is the dominant European CLOB. Public design notes:

- **In-memory** order book, single-threaded per instrument.
- **Sub-millisecond** matching latency.
- **MITCH** protocol for market data (binary, multicast).
- **Multi-asset**: handles equities, ETFs, bonds, and derivatives on the same core platform.

LSE's lesson: the **same matching engine can serve many asset classes** if the abstraction is right (order book per instrument; matching rules parameterized; risk checks per asset class).

### IEX — the exchange that was built to be slow

IEX (Investors Exchange), launched in 2016, is a US equities exchange that introduced a **350-microsecond delay** on every order. The delay is implemented as a **38-mile coiled fiber** that adds the delay to the wire. Why? To neutralize the speed advantage of HFT firms that were co-located in Mahwah, NJ.

IEX's design:

- **Discretionary Peg** order type: pegs to the NBBO (national best bid/offer) but only displays when the exchange is not "crumbling" (rapidly moving).
- **Speed bump**: the 350 µs delay applies to all orders (in and out), making the exchange unattractive to latency arbitrage.
- **Auction** for opening and closing.

The IEX story is a case study in **exchange design as a regulatory product**. The technical challenge was trivial; the regulatory and market-structure challenge was substantial. IEX had to win SEC approval to operate as an exchange despite the unconventional design.

### Citadel Securities — market maker at scale

Citadel Securities is one of the largest market makers in US equities (and increasingly other asset classes). Public engineering talks describe their infrastructure:

- **Co-located** in every primary US data center (Carteret, Mahwah, Aurora).
- **Direct feeds** from every exchange (ITCH, OUCH, Pillar, EDGX, etc.).
- **Sub-µs** internal processing — the fastest path between seeing a quote change and sending an order is single-digit microseconds.
- **Smart order router** that splits orders across exchanges based on price, latency, and fill probability.
- **Cross-asset** risk engine: aggregate exposure across equities, options, futures.

Citadel's lesson: at the HFT scale, the **edge is in the milliseconds** (or less), and the **exchange is one input to a larger system** (the smart router). The market maker's "view of the market" is a synthesized feed of every exchange's data; matching engines are the producers, market makers are the consumers.

### Jane Street — prop trading and the exchange problem

Jane Street is a major proprietary trading firm and market maker. Their public engineering talks emphasize:

- **OCaml** as the primary language for trading systems (functional, strong typing, high performance).
- **Determinism and reproducibility** as first-class concerns — the same input must always produce the same output, even across days.
- **In-house matching** for some products (e.g., ETF creation/redemption) where the exchange model doesn't apply.
- **Risk management** as a top-level concern: every trade is checked against position limits in real time.

Jane Street's lesson: **the exchange design pattern (deterministic matching + sequenced log) is a general pattern** for any system where fairness and reproducibility matter — including some in-house trading systems.

### FIX protocol — the lingua franca

FIX (Financial Information eXchange) has been the de facto standard for order entry since the 1990s. The protocol:

- **Tag-value** format: `8=FIX.4.4|9=178|35=D|49=CLIENT|56=EXCHANGE|...|10=000|`. Each tag has a numeric ID and a value.
- **Message types**: `D` = NewOrderSingle, `F` = OrderCancelRequest, `8` = ExecutionReport, etc.
- **Session layer**: heartbeats (`0`), sequence number tracking, gap-fill resend (`4`).
- **Versions**: FIX 4.2 (legacy), FIX 4.4 (most common), FIX 5.0 (newer; less deployed).

FIX is verbose (200+ bytes per message), slow to parse, and TCP-based. For HFT, exchanges offer **binary equivalents** (ITCH for market data, OUCH for orders) that are 10–100x smaller and faster to parse. The user-facing FIX gateway is then a translator from FIX to internal binary.

### ITCH and OUCH — NASDAQ's binary protocols

- **ITCH**: market data feed. Each message is 5–40 bytes. Types include `Add Order`, `Order Executed`, `Order Cancel`, `Order Replace`, `Trade`. Multicast UDP, push-based, no retransmission. If you miss a message, you don't get it back — you're expected to recover via snapshot + replay.
- **OUCH**: order entry protocol. Each message is smaller than FIX. Types include `Enter Order`, `Cancel Order`, `Replace Order`. TCP-based, request/response.

The ITCH/OUCH pair is NASDAQ's contribution to the protocol stack. Other exchanges have equivalents (NYSE's Pillar protocol, LSE's MITCH, etc.). All are binary, compact, and optimized for latency.

### Market data feeds — direct vs consolidated

A trader can subscribe to:

- **Direct feeds**: the exchange's native ITCH/MITCH feed. Lowest latency, full depth, but one feed per exchange.
- **Consolidated feeds (SIP)**: the SEC-mandated best-bid/best-offer + last-trade feed aggregated across exchanges. Higher latency (Reg NMS requires a specific aggregation model), but one feed covers all US exchanges.

The latency gap between direct and consolidated is in the **hundreds of microseconds to milliseconds**. HFT firms use direct feeds; retail uses consolidated. Reg NMS Rule 611 (Order Protection Rule) requires brokers to route orders to the exchange displaying the best price, which is determined by the SIP — a design that has been controversial because the SIP is the slow path.

### Co-location

Co-location is the practice of placing your trading servers in the same data center as the exchange's matching engine, with **direct cross-connects** (fiber, often 1m–10m of cable) to the exchange's network. The latency benefit:

- Network RTT from co-located to exchange: ~1–5 µs.
- Network RTT from a normal office to exchange: ~500 µs to ~5 ms.
- Difference: 100–1000x.

Co-location is expensive (rack space, power, cross-connect fees) and concentrated (every major exchange has a primary data center). HFT firms pay hundreds of thousands of dollars per month for co-located rack space.

### HFT arms race

The arms race in HFT is well-documented:

- 2005: average HFT order-to-fill latency: ~10 ms.
- 2010: ~1 ms.
- 2015: ~100 µs.
- 2020: ~10 µs.
- 2025: ~1 µs (top firms).

The latency improvements come from:

- **Custom hardware**: FPGAs and ASICs that implement matching logic in firmware.
- **Co-location**: 1m of fiber vs 10 km of fiber.
- **Kernel-bypass networking**: DPDK, OpenOnload, ef_vi.
- **Optimized protocols**: binary, fixed-format, lock-free.
- **Faster CPUs**: clock speed, IPC, cache size.
- **Tighter code**: zero-allocation, branch-free, prefetch hints.

The "latency floor" is now bounded by the speed of light through fiber (~5 ns/m) and the clock period of the matching CPU (~0.3 ns at 3 GHz). The theoretical minimum wire-to-wire is single-digit microseconds. Top-tier HFT firms operate within 2x of this theoretical floor.

### SEC Rule 15c3-5 (Market Access Rule)

Rule 15c3-5, the "Market Access Rule," requires broker-dealers that provide market access to have **controls on trading risk**. Specifically:

- **Pre-trade** risk checks: prevent the entry of orders that exceed appropriate credit or capital thresholds.
- **Duplicate order checks**: reject orders that would be obvious duplicates.
- **Erroneous order checks**: reject orders at prices or sizes that appear erroneous.
- **Financial thresholds**: aggregate credit exposure across all customers.

The rule is the **legal reason** every exchange has a pre-trade risk engine. It's why your order gets rejected with "risk limit exceeded" when you accidentally type "1000000" instead of "100."

### Reg NMS (National Market System)

Reg NMS, adopted by the SEC in 2005, has four rules:

- **Rule 611 (Order Protection Rule)**: brokers must route orders to the exchange displaying the best price. The "best price" is determined by the consolidated SIP.
- **Rule 610 (Access)**: fair access to exchange data and services.
- **Rule 612 (Sub-Penny Rule)**: minimum quote increments of $0.01 for stocks > $1.00.
- **Rule 600/603 (Market Data)**: defines the SIP and the data products.

Reg NMS is the **legal framework** that defines how US equity markets work. It's why the SIP exists, why exchanges compete on price, and why HFT firms exist (latency arbitrage on the SIP delay).

---

## Common Pitfalls & Failure Modes

### Pitfall 1 — Multi-threading the matching engine

The most common beginner mistake. "Matching is slow; let me add threads." The result: lock contention, non-determinism, debugging nightmares, and slower performance than the single-threaded version. The single-threaded design wins because:

- The matching work per event is tiny (microseconds). Lock overhead exceeds the work.
- The data structures (order book) are cache-line-shared; threads contend on cache lines even without explicit locks.
- Determinism requires a single thread anyway; multi-threading requires additional sequencing to maintain determinism, which adds latency.

The right way to scale: **shard by symbol**. One thread per symbol. 3,000 symbols = 3,000 threads = massive aggregate throughput.

### Pitfall 2 — Synchronous disk I/O on the hot path

`fsync` per event adds 1–10 ms per event. At 1M events/sec, this is 1M × 5 ms = 5,000 seconds of disk time per real second — impossible. The fix:

- **Pipeline** the log write: the matching engine appends to a ring buffer; a separate thread does the actual disk write.
- **Group commit**: batch 100 events, one fsync. ~10x throughput improvement.
- **Async replication**: write locally to NVMe, replicate to standby async, accept the small RPO risk.

The trade-off: a small RPO (recovery point objective) — typically 1–10 ms of events can be lost in a crash. For most exchanges, this is acceptable because the engine's deterministic state machine means a recovery from the log + a snapshot rebuilds state exactly.

### Pitfall 3 — GC pauses

Java and C# have garbage collectors that can pause for 10–100 ms during a full GC. For a matching engine with a P99 target of 50 µs, a 100 ms GC pause is a catastrophic tail-latency event. Mitigations:

- **Off-heap memory**: store order book data outside the JVM heap (using `DirectByteBuffer` in Java, or C/C++).
- **Zero-allocation steady state**: preallocate all order objects in pools; reuse them.
- **G1GC / ZGC tuning**: modern Java GCs have sub-millisecond pauses; not zero, but close.
- **Avoid Java entirely**: production exchanges are typically C, C++, or Rust for the hot path.

A real example: LMAX (the LMAX Exchange in London) built their matching engine in Java and achieved < 1 ms P99.99 by careful allocation discipline and tuned GC. Other exchanges (CME, NASDAQ) use C/C++ for sub-µs.

### Pitfall 4 — Non-deterministic state machine

The state machine must be a **pure function** of the event sequence. Common sources of non-determinism:

- **Timestamps**: `System.currentTimeMillis()` is not deterministic across replicas. **Use a logical clock** (the sequencer's sequence number), not a wall clock.
- **Random numbers**: never use `Math.random()` in the state machine. Generate randomness when creating the command, not when applying it.
- **External calls**: any network or disk read in the state machine is non-deterministic. Resolve all external values when creating the command.
- **Floating-point non-associativity**: `(a + b) + c != a + (b + c)` in floating point. Use integer minor units for money math.

A non-deterministic state machine causes replicas to diverge — a fatal error for state-machine replication.

### Pitfall 5 — Using wall-clock for time priority

FIFO at a price level uses the order's arrival time. If the clock is local to each gateway, two orders from different gateways at the "same time" have ambiguous priority. The fix: **assign the timestamp from the sequencer's logical clock**, not from the gateway. The sequencer's clock is the canonical clock for the exchange.

### Pitfall 6 — Sending the market data on a separate path

A naive design: matching engine writes fills to the order book, then a separate process reads the book and publishes to market data. The result: the market data is stale by the time it reaches subscribers. The fix: **derive market data from the same sequenced event stream the matching engine uses**, with the lowest possible additional latency. The market data publisher is a consumer of the event log, not a poller of the order book.

### Pitfall 7 — Skipping the sequencer and hoping for determinism

"It's all in-memory; the matching is fast; we don't need a sequencer." The result: two gateways receive orders at the same time, and the order in which the matching engine processes them is non-deterministic. Replicas diverge. The fairness guarantee is broken.

The sequencer is the simplest way to **impose a total order on all inbound events**. It is not optional.

### Pitfall 8 — Tail-latency blindness

A matching engine with P50 of 5 µs and P99.99 of 5 ms is not a 5 µs engine — it's a 5 ms engine that is fast on average. HFT participants will route around your exchange if your P99.99 is bad, because that's when the biggest market moves happen.

Tail-latency blindness is the most common cause of HFT firms avoiding an exchange. Measure P99, P99.9, P99.99, and P99.999. Optimize the tail.

### Pitfall 9 — Snapshot inconsistency

A snapshot taken concurrently with event application can capture a state that **does not correspond to any prefix of the event log**. On recovery, the replay produces a different state, and the system diverges. Mitigations:

- **Drain the in-memory queue** before snapshotting.
- **Capture the sequence number** with the snapshot.
- **Use copy-on-write** data structures where the snapshot is a consistent view at version V.
- **Verify snapshots** by replaying from the snapshot's seq and comparing to the live state at the same seq.

### Pitfall 10 — Believing "the order reached the gateway" means "the order is in the book"

In a high-throughput system with pipelined persistence, an order can be in the matching engine, on the wire to the client (ExecutionReport), and **not yet in the durable log**. A crash at this moment loses the order. The fix: **make the ExecutionReport come after the durable log write**, not before. This adds a tiny amount of latency (1–10 ms for group commit) but gives a real durability guarantee.

---

## Interview Q&A

### Q1 — "How would you ensure that two participants sending orders at the same time get fair treatment?"

Fairness in a stock exchange means **price-time priority**: among orders at the same price, the one that arrived first matches first. The "arrived first" must be defined by a single canonical clock.

The answer:

1. **Sequencer**: every order passes through a single sequencer that assigns a monotonically increasing sequence number based on arrival. The sequence number is the canonical timestamp for fairness.
2. **Order book**: within a price level, orders are ordered by sequence number, not by wall-clock. Two orders at the same price with sequence numbers 100 and 101 are ordered 100 first.
3. **Matching**: the engine always matches against the lowest sequence number at the best price, regardless of which gateway received the order.
4. **Audit**: the sequence number is included in the ExecutionReport, so the client can verify that their order was given fair treatment.

The sequencer is the **fairness primitive**. Without it, two gateways could process orders in any order, and the exchange would be vulnerable to "queue position" attacks (front-running by reaching the matching engine first).

### Q2 — "Why single-threaded when multi-threaded is faster?"

Counter-intuitive but true. The answer:

- **Lock contention**: order book operations (add, remove, match) touch shared state. Multi-threading requires locks, and lock acquisition is more expensive than the matching work itself (which is microseconds).
- **Cache contention**: even without explicit locks, multi-threaded access to the same data structure causes cache-line bouncing between cores, which is slow.
- **Determinism**: multi-threaded execution is non-deterministic by default (thread scheduling varies). The matching engine requires determinism for replay and replication. Adding synchronization to enforce determinism adds latency.
- **Parallelism is across symbols, not within**: a 3,000-symbol exchange can run 3,000 single-threaded matching engines (one per symbol), each on its own core, achieving 3,000x parallelism without any of the within-symbol problems.

The exchange's parallelism is **horizontal sharding**, not vertical threading. This is the LMAX insight (Disruptor) and the standard for any CLOB.

### Q3 — "How do you keep the matching engine fast even with risk checks?"

The key is that risk checks must be:

1. **In-memory**: account state, position limits, and exposure are all in-memory hash tables. Disk access is forbidden in the hot path.
2. **Pre-computed**: risk limits are pre-aggregated; per-order checks are O(1) or O(log N).
3. **Hierarchical**: some checks (symbol exists, order valid) are at the gateway; others (buying power) are at the risk engine; others (per-symbol) are at the matching engine. Each layer is fast.
4. **Cached**: account state is updated in real time and cached locally to the risk engine.

The risk engine is **separate from the matching engine** but on the same fast path. A risk check adds 1–5 µs to the order latency. For a 10 µs exchange, that's a 50% overhead; exchanges tune this carefully.

### Q4 — "How would you handle a market-wide crash event (e.g., 2010 Flash Crash)?"

A market-wide crash has three components:

1. **Order flow spike**: 10x normal order rate. The system must handle this without backing up. Pre-allocate capacity for 5x normal; rely on circuit breakers for the rest.
2. **Price movement**: the matching engine itself handles price movement naturally (it just matches at whatever price is offered). The issue is downstream — broker systems, market makers, retail apps — that may not handle rapid price moves.
3. **Circuit breakers**: most exchanges have **LULD (Limit Up/Limit Down)** bands that pause trading in a symbol if it moves more than X% in Y minutes. The pause gives humans time to assess.

The exchange's role is to **keep matching through the event** (with LULD pauses), maintain a complete audit trail (so post-event analysis is possible), and operate the matching engine deterministically (so the post-event state is reproducible).

The 2010 Flash Crash exposed two exchange-design issues that have since been addressed: (1) **stub quotes** (market makers displaying $0.01 / $99,999 quotes) were confusing the market; (2) **individual stock circuit breakers** were not consistently applied. The 2012 LULD rule addressed both.

### Q5 — "How would you go from 1M orders/sec to 10M orders/sec?"

Three options:

1. **More symbols**: 10M / 3,000 = ~3,300 orders/sec/symbol — still well within single-thread capacity. This is "free" if you add more listed instruments.
2. **More cores per symbol**: split a single symbol's book across multiple engines. This **breaks determinism** unless you partition by price (e.g., one engine for top-of-book, another for deeper levels) and re-merge. Complex, but possible for very hot symbols.
3. **Geographic distribution**: each region (US, EU, APAC) has its own matching engine for regional symbols. Cross-region orders are routed to the home region. This is the standard approach for global exchanges.

The 10M case is rare in practice. Even the largest US exchanges rarely sustain 5M orders/sec across all symbols.

### Q6 — "How do you test a matching engine?"

Six categories:

1. **Unit**: matching logic, price-time priority, partial fills, cancels. Pure functions, no I/O.
2. **Replay**: load a recorded event stream and verify the engine's output matches a known-good reference. This is the "golden log" test — the engine is correct iff replaying the log reproduces the expected order book and trade tape.
3. **Concurrency**: the engine is single-threaded, so "concurrency" is really "event ordering." Verify that any permutation of identical events produces the same final state (it must, because the state is a function of the log).
4. **Failure**: kill the matching engine mid-event; restart; verify the order book is restored from the log + snapshot.
5. **Performance**: measure P50, P99, P99.9, P99.99, P99.999 latency under sustained load. Use synthetic load (random orders, market orders, cancels) to stress the engine.
6. **Property-based**: for every event sequence, the invariant `sum(bids) == sum(asks) + last_trade_price` (or whatever invariant you choose) holds. Run continuously.

The golden log is the most powerful test. If you have a recorded stream of events from a known-good system (e.g., a previous day of trading), replaying it and matching the output is a near-complete correctness check.

### Q7 — "How does the exchange interact with the broker / clearing firm downstream?"

The exchange's job ends at the **execution report**. Downstream:

- **Broker**: receives the ExecutionReport, updates the client's position, may need to allocate the trade across multiple client accounts.
- **Clearing firm**: novates the trade — the original buyer and seller are replaced by the clearing firm as the counterparty to each side. This is the **novation** that makes the exchange a closed system (a trade between two clearing members is guaranteed).
- **Custodian**: holds the actual securities and cash. The clearing firm instructs the custodian to move them.
- **Settlement**: T+1 (US) or T+2 (other regions) — the actual delivery of securities and cash.

The exchange does not know about clearing, settlement, or custody. It matches orders and emits execution reports. The post-trade pipeline is its own industry.

For a design interview, the answer: "the exchange emits ExecutionReports with all the fields needed for downstream clearing (trade ID, symbol, price, size, buyer, seller, timestamp). The clearing and settlement systems consume these and complete the trade lifecycle."

---

## Key Terms / Glossary

| Term | Definition | Common misconception |
|------|------------|----------------------|
| **Order book** | Per-symbol data structure of resting limit orders, organized by price-time priority. | "It's sorted alphabetically" — sorted by price (best first), then by time within a price. |
| **CLOB (Central Limit Order Book)** | The order book maintained by a single exchange; all participants see the same book. | "It's the only order book type" — there are also dark pools, RFQ systems, and crossing networks. |
| **Price-time priority** | Matching rule: best price first; within a price, earliest arrival first. The standard for most exchanges. | "Pro-rata is the same" — pro-rata allocates proportionally to order size; used by some futures exchanges. |
| **Pro-rata matching** | Allocates a trade to all orders at the best price, proportional to their size. Used by some futures exchanges (CME). | "It's fairer" — pro-rata advantages large orders; price-time priority advantages speed. |
| **Limit order** | An order to buy/sell at a specified price or better. May rest in the book if not immediately matched. | "It always matches" — only if the price is marketable; otherwise it rests. |
| **Market order** | An order to buy/sell immediately at the best available price. Always matches (or is canceled if no liquidity). | "It always gets the best price" — it gets the best available at the time of execution, which can be a range of prices (a "sweep"). |
| **Best bid / best ask (BBO)** | The highest bid and lowest ask in the book. The "top of book." | "It's the only relevant price" — depth beyond the BBO matters for large orders. |
| **NBBO (National Best Bid/Offer)** | The best bid and offer across all US exchanges, determined by the SIP. Required for Reg NMS Rule 611 routing. | "It's the same as the BBO" — the BBO is per-exchange; the NBBO is the consolidated best. |
| **Spread** | The difference between best ask and best bid. A measure of liquidity. | "Wide spread = illiquid" — generally true, but can also indicate information asymmetry. |
| **Tick size** | The minimum price increment. $0.01 for US stocks > $1.00 (Reg NMS Rule 612). | "It's always $0.01" — sub-penny increments exist for some instruments; $0.0001 for some futures. |
| **Sequencer** | Component that assigns a single total order to all inbound events. The fairness primitive. | "It's optional" — without it, fairness is undefined. |
| **State-machine replication** | A replication technique where replicas apply the same ordered log to identical initial state, producing identical output. | "It's the same as primary-backup" — primary-backup sends the resulting state; state-machine replication sends the input. |
| **Snapshot** | A persisted checkpoint of the order book state. Bounded-replay recovery. | "It replaces the log" — the log is the truth; the snapshot is a fast-start. |
| **FIX (Financial Information eXchange)** | Industry-standard messaging protocol for orders and executions. Tag-value, TCP. | "It's the fastest" — it's the standard for compatibility, not the fastest. Binary protocols are faster. |
| **ITCH / OUCH** | NASDAQ's binary protocols for market data (ITCH) and order entry (OUCH). | "They're exchange-specific" — variants exist at most exchanges; the principle is shared. |
| **Hot standby** | A replica that consumes the same log in real time and is ready to take over on primary failure. | "It's automatic" — failover is automatic only with proper heartbeat and quorum configuration. |
| **Co-location** | Placing trading servers in the same data center as the exchange, with direct fiber cross-connects. | "It's the same as proximity hosting" — co-location is inside the exchange's data center; proximity hosting is in a nearby facility. |
| **Kernel bypass** | Networking technique that avoids the OS kernel for packet processing (DPDK, OpenOnload, ef_vi). | "It's just faster drivers" — it's a fundamentally different I/O model that bypasses the kernel entirely. |
| **Mechanical sympathy** | Designing software to align with hardware behavior (cache lines, prefetch, branch prediction). Martin Thompson's term. | "It's premature optimization" — for HFT, it's table stakes. |
| **Disruptor** | LMAX's lock-free inter-thread communication pattern. | "It's just a queue" — it's a specific ring-buffer design with predictable latency. |
| **Tail latency** | High-percentile latency (P99, P99.9, P99.99). What HFT firms care about. | "Average is enough" — average hides the outliers that matter for trading. |
| **Reg NMS** | SEC's National Market System regulations, including Order Protection Rule (611) and SIP rules. | "It applies globally" — Reg NMS is US-only; other regions have similar but different rules (MiFID II in EU). |
| **SEC Rule 15c3-5 (Market Access Rule)** | Requires pre-trade risk checks for broker-dealers providing market access. | "It's the exchange's rule" — it's a broker rule, but exchanges implement it via the matching engine's pre-trade checks. |
| **LULD (Limit Up/Limit Down)** | Volatility circuit breaker that pauses trading in a symbol if it moves more than X% in Y minutes. | "It's a circuit breaker for the whole market" — LULD is per-symbol; market-wide circuit breakers (market-wide LULD) exist too. |
| **SIP (Securities Information Processor)** | The consolidated tape that aggregates best prices across exchanges. The "slow path." | "It's a single feed" — there are two SIPs (CTA for NYSE-listed, UTP for Nasdaq-listed). |
| **Direct feed** | An exchange's native, low-latency market data feed (ITCH, MITCH, etc.). | "It's free" — direct feeds have substantial monthly fees. |
| **Auction** | A batched matching process that computes a single clearing price (open, close, volatility). | "It's the same as continuous trading" — auctions use a different algorithm; orders are accumulated and matched at one price. |
| **Opening auction** | Auction at market open to determine the opening price. | "It's instant" — auctions take several minutes to accumulate orders. |
| **Closing auction** | Auction at market close to determine the closing price. | "It's just for closing" — closing auctions set the reference price used by mutual funds and index funds; volume is large. |
| **Market maker** | A participant that continuously quotes bid and ask prices, providing liquidity. | "They take risk" — they do, but they also earn the spread; net economics depend on inventory and adverse selection. |
| **HFT (High-Frequency Trading)** | Trading with very low latency, often using algorithmic strategies and co-location. | "It's all front-running" — HFT includes market making, statistical arbitrage, and latency arbitrage; not all of it is predatory. |
| **Latency arbitrage** | Exploiting price discrepancies across exchanges caused by SIP delay. | "It's illegal" — it's legal but controversial; IEX was built specifically to make it harder. |
| **Maker-taker fee** | Fee model: makers (resting orders) get paid a rebate; takers (aggressive orders) pay a fee. | "It's a rebate" — it's a fee structure that incentivizes liquidity provision. |
| **Taker** | An order that matches immediately (removes liquidity from the book). | "Taker fees are higher" — yes; the fee structure rewards makers. |
| **Maker** | An order that rests in the book (provides liquidity). | "Makers always win" — they get the rebate, but they take the inventory risk. |
| **Self-trade prevention (STP)** | Mechanism to prevent a participant's buy and sell orders from matching each other. | "It cancels both orders" — modes vary: cancel taker, cancel maker, cancel both, or cancel smallest. |
| **Iceberg order** | Large order with a small displayed portion; the rest is hidden until the displayed portion is filled. | "It hides the full size" — yes, but the hidden portion is matched FIFO with displayed orders. |
| **Stop order** | An order that becomes a market or limit order when the price reaches a specified level. | "It always triggers" — only if the trigger price is reached; in a fast market, the trigger may be gapped through. |
| **Buying power** | The maximum amount a trader can buy (or short). | "It's just cash" — for margin accounts, it's cash + (margin × portfolio value). |
| **Fat-finger check** | Pre-trade check that rejects orders with obviously wrong prices or sizes. | "It's a real risk" — yes; an extra zero in a price is a real risk. |
| **Price collar** | A pre-trade price range; orders outside the range are rejected. | "It's the same as a limit" — a collar is an exchange-imposed safety net; a limit is a user-set price. |
| **Risk engine** | The component that performs pre-trade checks (buying power, position, exposure). | "It's at the broker" — broker risk + exchange risk; both check, sometimes redundantly. |
| **Clearing** | The process of novating a trade (replacing the original counterparties with a clearing firm). | "The exchange clears" — exchanges match; clearing firms (e.g., NSCC, OCC) clear. |
| **Settlement** | The actual delivery of securities and cash. T+1 in the US (since 2024), T+2 in EU (moving to T+1). | "It's instant" — it takes 1–2 days; T+0 is the long-term direction. |
| **DTCC** | Depository Trust & Clearing Corporation. The US central counterparty and settlement system. | "It's the exchange" — DTCC is post-trade; exchanges are pre-trade. |
| **NSCC** | National Securities Clearing Corporation. DTCC's US equities clearing subsidiary. | "It trades" — it clears (novates); trading is the exchange's job. |
| **DTC** | Depository Trust Company. The actual securities holding entity (a subsidiary of DTCC). | "It's a custodian" — it's the central securities depository; custodians are its customers. |
| **Novation** | Replacing the original counterparties in a trade with a clearing firm. | "It's a transfer" — it's a legal substitution; the original parties are released. |
| **Multi-listed security** | A security traded on more than one exchange (e.g., AAPL on NYSE and Nasdaq). | "It's the same instrument" — yes, but the order books are separate; the best price is the consolidated NBBO. |
| **Odd lot** | An order for fewer than 100 shares (the "round lot" size for US equities). | "It can't match" — odd lots can match on some exchanges; pricing rules differ. |
| **Round lot** | 100 shares for most US equities. The standard trading unit. | "It's the minimum" — it's the standard; odd lots are smaller and often have different pricing rules. |
