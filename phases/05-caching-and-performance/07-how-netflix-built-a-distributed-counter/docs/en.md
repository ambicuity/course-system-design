# How Netflix Built a Distributed Counter

> 75K counter operations per second at single-digit millisecond latency — the architecture behind one of the most-used abstractions in any system.

**Type:** Learn
**Prerequisites:** Distributed systems basics, time-series data concepts
**Time:** ~15 minutes

---

## The Problem

Counters are everywhere. Page views, video plays, likes, error counts, rate-limit buckets, login attempts, search impressions. Every system needs to count things, often in real time, often at very high scale.

A single-server counter is trivial: `INCR key` in Redis, or `UPDATE counter SET value = value + 1`. Done.

But production counters are not trivial. They need to:

- Handle billions of events per day
- Return counts in real time with sub-millisecond latency
- Be accurate (or at least eventually accurate)
- Survive node failures without losing events
- Scale horizontally as load grows

The naive approach (one node doing all the counting) becomes a bottleneck. The distributed approach (many nodes counting independently) becomes a consistency problem. Netflix's Distributed Counter Abstraction is the architecture that solves both.

---

## The Concept

### What a distributed counter must do

```
   A distributed counter is a system where the responsibility
   of counting events is spread across multiple servers or nodes
   in a network. It must:

     - Accept a write (AddCount) at very high rate
     - Return a current value (GetCount) at very low latency
     - Survive individual node failures
     - Provide eventually consistent results across the cluster
     - Scale horizontally with load
```

Netflix's counter handles **75,000 requests per second at single-digit millisecond latency** — that is the bar to aim for.

---

### Netflix's four-layer architecture

```
   ┌─────────────────────────────────────────────────────────────┐
   │                                                             │
   │   1. Client API Layer                                       │
   │      User-facing entry point                                │
   │      ↓                                                     │
   │   2. Event Logging & TimeSeries Storage                     │
   │      Persistent record of every increment                   │
   │      ↓                                                     │
   │   3. Rollup Pipeline (Aggregation)                          │
   │      Batch-process events into time-windowed sums           │
   │      ↓                                                     │
   │   4. Read Optimization (Cache + Query Handling)             │
   │      Serve reads from in-memory cache                       │
   │                                                             │
   └─────────────────────────────────────────────────────────────┘
```

Each layer has a specific role. Together they deliver the throughput and latency guarantees.

---

### Layer 1: Client API Layer

The user-facing API exposes three operations:

```
   AddCount(counter_name, amount, event_id)
   GetCount(counter_name)
   ClearCount(counter_name)
```

The API is served through the **Netflix Data Gateway**, which routes requests, applies authentication, and forwards to the appropriate backend service.

**Properties:**

- Stateless; scales horizontally
- Routes to one of many counter service instances
- Each request carries an `event_id` for **idempotency** (deduplication)

**Why idempotency matters:** if a network blip causes the client to retry an AddCount, the system must not double-count. The event_id is used downstream to deduplicate.

---

### Layer 2: Event Logging and TimeSeries Storage

Every AddCount request is logged as an event to Netflix's **TimeSeries Abstraction** storage, which is built on **Cassandra**.

```
   AddCount(video_id=42, amount=1, event_id=abc-123)
        │
        ▼
   ┌─────────────────────────────────────────────┐
   │  TimeSeries event:                           │
   │    counter: "video_42_plays"                │
   │    amount: 1                                │
   │    timestamp: 2024-12-01T14:30:00Z          │
   │    event_id: abc-123                        │
   └─────────────────────────────────────────────┘
```

**Why an event log:**

- **Durability** — every count is recorded before being acknowledged
- **Recovery** — if the rollup pipeline fails, events can be re-processed
- **Audit** — a complete history of every change is available

**Bucketing for write efficiency:**

Events are grouped into **time partitions (buckets)** to avoid contention on a single row in Cassandra. A bucket might hold all events for a specific counter in a specific minute. New events append to the current bucket; old buckets are immutable.

```
   Buckets:
     video_42_plays:2024-12-01-14-29  →  [events...]
     video_42_plays:2024-12-01-14-30  →  [events...]
     video_42_plays:2024-12-01-14-31  →  [events...]  ← current, append-only
```

When the current minute ends, the bucket is closed. New events go to the next bucket. Closed buckets are processed by the rollup pipeline.

---

### Layer 3: Rollup Pipeline (Aggregation)

The rollup pipeline reads raw events from closed buckets, aggregates them into time-windowed sums, and writes the results to a separate **Rollup Store**.

```
   Bucket (1 minute of events)
        │
        ▼
   Rollup Pipeline:
     Sum events per counter for the window
     Emit one record per (counter, window) with the total
        │
        ▼
   ┌─────────────────────────────────────────────┐
   │  Rollup record:                             │
   │    counter: "video_42_plays"                │
   │    window: 2024-12-01-14-29                │
   │    count: 1487                              │
   │    aggregated_at: 2024-12-01T14:30:30Z     │
   └─────────────────────────────────────────────┘
```

**Properties:**

- **Immutable time windows** — each rollup covers a fixed period; no re-aggregation needed
- **Eventually consistent** — fresh events are still in the bucket; rollups lag by 1–2 minutes
- **Idempotent** — the pipeline can re-process a bucket if needed; event_id prevents double counting

**Why batched:**

Processing one event at a time is expensive at scale. The rollup pipeline reads millions of events in batches and aggregates them in memory. The cost per event is far lower than per-event processing.

**Why this matters:**

- Real-time counts serve fresh-but-approximate values
- Rollup counts serve accurate historical values
- The two views are reconciled eventually

---

### Layer 4: Read Optimization (Cache + Query Handling)

Reads (GetCount) are served from **EVCache** (Netflix's distributed cache), which holds the latest aggregated counts.

```
   GetCount("video_42_plays")
        │
        ▼
   EVCache lookup
        │
        ├── HIT  → return value (single-digit ms)
        │
        └── MISS → query Rollup Store → populate cache → return
```

**Properties:**

- Single-digit millisecond latency for typical reads
- Cache is periodically refreshed from the Rollup Store
- If the cache value is stale (e.g., a rollup arrives late), a background refresh updates it

**Why cache matters:**

Reads are 10–100× more frequent than writes in most counter workloads (you increment once, you read many times). Optimizing reads is high-leverage.

---

## Build It / In Depth

### The full flow of a single AddCount

```
   Client: AddCount("video_42_plays", 1, event_id=abc-123)
        │
        ▼
   [1] Data Gateway
       - Authenticates the request
       - Routes to a counter service instance
        │
        ▼
   [2] Counter service
       - Validates the event_id (deduplication check)
       - Writes the event to TimeSeries (Cassandra bucket)
       - Returns success to client
        │
        ▼
   [3] Rollup Pipeline (async, in background)
       - Bucket closes (e.g., minute ends)
       - Reads events from the bucket
       - Aggregates: sum(amount) per counter
       - Writes rollup record to Rollup Store
        │
        ▼
   [4] Cache Refresh (async)
       - Reads rollup value
       - Updates EVCache entry
        │
        ▼
   Future GetCount:
       - EVCache HIT → return rollup value
```

Latency of AddCount: a few ms (network + Cassandra write).
Latency of GetCount: single-digit ms (EVCache hit).

---

### Why this design works

**Decoupling write and aggregation:**

- Writes are fast (single Cassandra append).
- Aggregation is heavy (sum of millions of events), but runs in the background.
- Reads serve the latest aggregated value, not a real-time sum.

**Idempotency via event_id:**

- Client retries are deduplicated downstream.
- The pipeline can re-process a bucket safely.

**Bucketed writes:**

- Cassandra row contention is avoided (each bucket is a separate row).
- Hot counters do not cause write contention.

**Eventually consistent reads:**

- Recent counts may lag the actual current value by minutes.
- For real-time accuracy, count from the live bucket; for accuracy, use the rollup.
- Most use cases tolerate a few minutes of lag.

---

### Design alternatives and why Netflix chose this

| Alternative | Why not |
|---|---|
| Single Redis `INCR` | Cannot scale beyond one node's write rate; loses data on node loss |
| Distributed counter per partition | Cross-partition queries are slow; aggregation is complex |
| Real-time aggregation (per-event) | Expensive at scale; latency dominated by per-event network hop |
| Streaming (Kafka + Flink) | Possible but more complex; Netflix's design achieves the same with simpler components |

Netflix's design is optimized for **eventual consistency with strong durability** — fits the way counters are actually used (you want the count to be right *eventually*, not necessarily at every millisecond).

---

## Use It

### When to use this pattern

| Situation | Use a distributed counter like this |
|---|---|
| Real-time counters at very high scale | Yes |
| Counters must survive failures | Yes |
| Tolerable lag: minutes | Yes |
| Need strong per-event durability | Yes (event log) |
| Need real-time exact counts | No — different design (single-node counter or sync replication) |

### When NOT to use this pattern

| Situation | Simpler alternative |
|---|---|
| Low scale (< 10K ops/sec) | Redis `INCR` |
| Need exact real-time counts | Single-node counter or strong consistency DB |
| Counters never queried historically | In-memory counter (lose on restart, but simple) |
| Counter values are derived from event stream | Compute from the stream (e.g., Kafka + Flink) |

---

### Implementing a simpler version yourself

For a smaller scale (10K–100K ops/sec), you can adopt the same four layers with simpler components:

```python
# Layer 1: API
@app.post("/counter/{name}/incr")
def increment(name: str, amount: int = 1):
    event = {"counter": name, "amount": amount, "ts": now()}
    redis.xadd(f"events:{name}", event)  # append to stream
    return {"ok": True}

# Layer 2: Event log (Redis Streams)
# Events append to per-counter streams with timestamp bucketing

# Layer 3: Rollup (background job, runs every minute)
async def rollup():
    for counter in active_counters:
        events = redis.xrange(f"events:{counter}", start, end)
        total = sum(e.amount for e in events)
        redis.set(f"counter:{counter}:total", total)

# Layer 4: Read (from cache)
@app.get("/counter/{name}")
def get(name: str):
    return {"value": redis.get(f"counter:{name}:total") or 0}
```

This scales to tens of thousands of ops/sec on a single Redis node. Beyond that, you need Cassandra + a real rollup pipeline.

---

## Common Pitfalls

- **Treating the counter as strongly consistent.** It is eventually consistent; reads may lag writes by minutes. Document this; design around it.

- **Skipping event_id.** Without idempotency, client retries double-count. Always include a unique event_id and deduplicate downstream.

- **Single hot bucket.** A burst on one counter writes to one bucket, which becomes a hotspot. Spread events across time buckets (e.g., per-second rather than per-minute) for very hot counters.

- **No TTL on events.** Raw events accumulate forever. Set a retention policy: keep raw events for 7 days, rollups for 90 days, aggregates forever.

- **Cache that never invalidates.** If the cache does not refresh, GetCount returns stale values forever. Wire the rollup pipeline to refresh the cache.

- **Confusing eventual with eventual-and-immediate.** "Eventual consistency" does not mean "infinity"; define the SLO (e.g., reads are accurate within 2 minutes).

- **Building it when you do not need to.** Most counters can be a Redis `INCR` and a simple `GET`. Reach for the four-layer architecture only when you measure the need.

---

## Exercises

1. **Easy** — In one sentence each, describe the role of the four layers in Netflix's distributed counter architecture.

2. **Medium** — Design a distributed counter for a product that needs to track 1 million events per second. Specify each layer's technology and the trade-offs you accept. How would you scale to 10× load?

3. **Hard** — A counter system must be **strongly consistent** at query time. Modify Netflix's design to deliver this. What do you lose? What does it cost?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Counter | A number | A monotonically increasing (or decreasing) value used to track events |
| Distributed counter | Multiple counters | A counter whose state is spread across multiple nodes, with eventual consistency |
| Time-series storage | A database | A database optimized for time-stamped events; supports bucketing, compression, and time-range queries |
| Idempotency | The same | The property that an operation produces the same result whether applied once or many times; enabled by unique event_ids |
| Bucketing | Partitioning | Grouping events by time window so writes do not contend on a single row |
| Rollup | Aggregation | Pre-computing aggregated values over time windows so reads are fast |
| Eventual consistency | Weak consistency | The model where the system converges to the correct value given enough time without new writes; counters in this design converge within minutes |
| EVCache | Netflix's cache | Netflix's distributed in-memory cache built on Memcached; serves reads at single-digit ms latency |

---

## Further Reading

- **Netflix Tech Blog — "Building a Distributed Counter"** — the source article: https://netflixtechblog.com/building-a-distributed-counter-8c5a7b0f3ca1
- **Cassandra Documentation** — the time-series storage backing the counter: https://cassandra.apache.org/doc/latest/
- **Redis Streams** — a simpler alternative for the event log layer: https://redis.io/docs/data-types/streams/
- **Time-series databases** — InfluxDB, TimescaleDB, and the wider landscape: https://www.timescale.com/