# How Netflix Built a Distributed Counter?

> Counting reliably at 75,000 requests per second means you cannot afford a single shared counter — you need to rethink what "counting" means at scale.

**Type:** Learn
**Prerequisites:** Caching Strategies, CAP Theorem, Cassandra Data Modeling
**Time:** ~25 minutes

---

## The Problem

Incrementing a counter sounds trivial. But at Netflix's scale — hundreds of millions of users streaming, skipping, pausing, rating, and searching simultaneously — a naive counter becomes a bottleneck that can take down an entire service.

Consider what Netflix needs to count in real time: how many times a title has been played this hour (to drive recommendations), how many users are actively watching a stream (for capacity planning), how many times an A/B test variant was shown (for experimentation), and how many times a push notification was delivered (for throttling). Each of these counters receives millions of increments per minute from thousands of servers across multiple regions.

A single database row with a `count` column protected by transactions would serialize all writes. At 75,000 writes per second, that one row becomes a global hot spot. Distributed lock managers fail under this load too — the coordination overhead dominates the actual work. Even Redis's single-threaded INCR, while fast, creates a single point of failure and does not scale horizontally without sharding complexity. The real challenge is: how do you count exactly-once semantics from a distributed, retry-happy client pool, serve reads at sub-millisecond latency, and stay eventually consistent rather than strongly consistent — all without any single server becoming a bottleneck?

---

## The Concept

Netflix's solution is called the **Distributed Counter Abstraction**. Instead of maintaining one authoritative counter that every writer must touch, the system decomposes the problem into three independent concerns: **writing events** (fast, idempotent, append-only), **aggregating events** (batched, asynchronous, eventually consistent), and **reading counts** (cached, refreshed in the background). These three concerns run on separate infrastructure and are loosely coupled through queues.

### The Four Layers

```
┌─────────────────────────────────────────────────────────┐
│                    CLIENT API LAYER                     │
│   AddCount(id, delta)  GetCount(id)  ClearCount(id)     │
│              Netflix Data Gateway (routing)             │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│           EVENT LOGGING & TIMESERIES STORAGE            │
│                                                         │
│  Event: { counter_id, event_id, delta, timestamp }      │
│  Partitioned into TIME BUCKETS (e.g., per-minute)       │
│  Stored in: Netflix TimeSeries Abstraction → Cassandra  │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼ (async via Rollup Queue)
┌─────────────────────────────────────────────────────────┐
│             ROLLUP PIPELINE (AGGREGATION)               │
│                                                         │
│  Batch-reads events per time bucket                     │
│  Sums deltas → immutable rollup value per window        │
│  Writes rollup to: Cassandra Rollup Store               │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│          READ OPTIMIZATION (CACHE & QUERY)              │
│                                                         │
│  Aggregated values cached in EVCache (Netflix's Redis)  │
│  Stale cache → background rollup refresh triggered      │
│  GetCount = cache hit or fast Cassandra Rollup read     │
└─────────────────────────────────────────────────────────┘
```

### Idempotency via Event IDs

Every `AddCount` call carries a client-generated **Event ID** (a UUID). When the event is written to the TimeSeries store, Cassandra's `INSERT IF NOT EXISTS` (lightweight transactions) or simple upsert-by-primary-key semantics ensure that a retried write with the same Event ID is a no-op. This means clients can retry aggressively without double-counting. The pattern trades write amplification (checking uniqueness) for correctness.

### Time Buckets

Rather than appending all events to one unbounded log, the system groups events into **time-partitioned buckets** (e.g., one Cassandra partition per counter per minute). This is the key insight:

| Without buckets | With buckets |
|-----------------|--------------|
| One hot partition per counter | Many partitions, spread across nodes |
| Write contention grows with throughput | Write contention is bounded by bucket size |
| Old data mixed with new data | Old buckets become immutable — safe to roll up |
| Compaction pressure everywhere | Compaction focused on old buckets |

A bucket becomes "closed" once its time window passes. Closed buckets will never receive new writes, so the aggregation pipeline can safely compute a final, immutable rollup for them.

### Rollup Pipeline

The rollup is an **async aggregation job** that runs continuously. It reads events from closed time buckets, sums the deltas, and writes a single rolled-up value into the Cassandra Rollup Store. Once a rollup exists for a window, the raw events for that window can be deleted (or archived), keeping storage bounded.

```
Time:      |--- T-2 ---|--- T-1 ---|--- NOW ---|
Buckets:   [closed]    [closed]    [open]
Rollup:    done        done        pending (raw events still accumulating)

GetCount(counter_id):
  = rollup(T-2) + rollup(T-1) + raw_events(NOW, not yet rolled up)
```

The "current" count requires reading both the latest rollup and the still-open bucket's raw events — a small fan-out that is handled at query time.

### EVCache Read Layer

EVCache is Netflix's distributed caching layer built on Memcached. Aggregated counter values are stored there with a short TTL. A `GetCount` request hits EVCache first:

- **Cache hit:** return immediately (sub-millisecond).
- **Cache miss:** read from Cassandra Rollup Store, populate cache, return.
- **Stale cache:** a background thread triggers a rollup refresh; the stale value is served until the refresh completes (read-around, not read-through).

This makes reads scale independently of writes. Read throughput is limited by EVCache cluster size, not by Cassandra node count.

---

## In Depth

### Walking Through an AddCount Call

**Step 1 — Client sends AddCount**

```
POST /counter/add
{
  "counter_id": "play_count:title_123",
  "event_id":   "a3f9c1d2-...",   // client-generated UUID
  "delta":      1,
  "timestamp":  1700000000000
}
```

**Step 2 — Data Gateway routes the request**

Netflix Data Gateway acts as the API layer. It validates the request, determines the correct time bucket, and writes the event to Cassandra via the TimeSeries Abstraction.

**Step 3 — Cassandra write (idempotent)**

The partition key is `(counter_id, bucket_id)` where `bucket_id = floor(timestamp / BUCKET_DURATION_MS)`.

```
-- Cassandra table (simplified)
CREATE TABLE counter_events (
  counter_id  TEXT,
  bucket_id   BIGINT,           -- e.g., minute epoch
  event_id    UUID,
  delta       INT,
  PRIMARY KEY ((counter_id, bucket_id), event_id)
);

INSERT INTO counter_events (counter_id, bucket_id, event_id, delta)
VALUES ('play_count:title_123', 28333333, a3f9c1d2-..., 1)
IF NOT EXISTS;
```

The `IF NOT EXISTS` guarantees idempotency. A retry with the same `event_id` does nothing.

**Step 4 — Rollup Queue receives a signal**

After the write, a message is placed on a Rollup Queue (Kafka or a similar durable log). The message says: "bucket `(play_count:title_123, 28333333)` has new events."

**Step 5 — Rollup pipeline aggregates the closed bucket**

When bucket `28333333` closes (the minute passes), the pipeline:
1. Reads all events for `(play_count:title_123, 28333333)`.
2. Sums the deltas: `Σ delta`.
3. Writes to Cassandra Rollup Store.
4. Invalidates or updates the EVCache entry.

```python
# Pseudocode for rollup worker
def rollup_bucket(counter_id, bucket_id):
    events = cassandra.query(
        "SELECT delta FROM counter_events WHERE counter_id=%s AND bucket_id=%s",
        counter_id, bucket_id
    )
    total = sum(e.delta for e in events)

    cassandra.execute(
        "INSERT INTO counter_rollups (counter_id, bucket_id, total) VALUES (%s, %s, %s)",
        counter_id, bucket_id, total
    )
    evcache.invalidate(f"counter:{counter_id}")
```

**Step 6 — GetCount assembles the answer**

```python
def get_count(counter_id):
    cached = evcache.get(f"counter:{counter_id}")
    if cached is not None:
        return cached

    rollups = cassandra.query(
        "SELECT SUM(total) FROM counter_rollups WHERE counter_id=%s", counter_id
    )
    open_bucket_events = cassandra.query(
        "SELECT SUM(delta) FROM counter_events WHERE counter_id=%s AND bucket_id=%s",
        counter_id, current_bucket_id()
    )
    total = rollups.total + open_bucket_events.delta
    evcache.set(f"counter:{counter_id}", total, ttl=5)  # 5-second TTL
    return total
```

### Why Cassandra?

Cassandra's data model maps cleanly to this pattern:

- **Partition key** `(counter_id, bucket_id)` distributes writes across the ring — no hot partitions.
- **Clustering key** `event_id` provides cheap deduplication within a partition.
- **Tunable consistency** — writes at `LOCAL_QUORUM`, reads at `LOCAL_ONE` for low latency.
- **Multi-region replication** — Netflix runs active-active across AWS regions; Cassandra's multi-datacenter replication matches that topology.

### Performance at Scale

| Metric | Value |
|--------|-------|
| Write throughput | 75,000 req/s sustained |
| Write latency (p99) | single-digit ms |
| Read latency (cache hit) | < 1 ms |
| Read latency (cache miss) | < 10 ms (Cassandra Rollup read) |
| Consistency model | Eventual (seconds behind) |
| Idempotency guarantee | Exactly-once counting |

---

## Use It

### When to use this pattern

The Netflix Distributed Counter pattern is appropriate when:

- Write throughput exceeds what a single RDBMS row or Redis key can handle.
- Exact strong consistency is not required — a few seconds of staleness is acceptable.
- Idempotent writes matter (retrying clients, at-least-once delivery).
- Reads vastly outnumber writes (cache tier pays off).

### Technology Mapping

| Component | Netflix's choice | Alternatives |
|-----------|-----------------|--------------|
| Append-only event store | Cassandra (TimeSeries Abstraction) | DynamoDB, ScyllaDB, ClickHouse |
| Async rollup queue | Internal queue (Kafka-like) | Apache Kafka, AWS SQS, Pulsar |
| Rollup store | Cassandra | DynamoDB, PostgreSQL, Redis sorted sets |
| Read cache | EVCache (Memcached-backed) | Redis Cluster, Memcached |
| API gateway | Netflix Data Gateway | Envoy, Kong, custom gRPC service |

### Simpler alternatives at lower scale

| Scale | Recommended approach |
|-------|---------------------|
| < 10K writes/s | Redis INCR with single primary |
| 10K–100K writes/s | Redis Cluster with key sharding |
| > 100K writes/s or multi-region | Netflix-style layered approach |
| Analytics-only (no real-time read) | ClickHouse / BigQuery aggregation |

For truly approximate counts (e.g., "roughly how many unique viewers"), **HyperLogLog** in Redis is orders of magnitude cheaper and still precise to ±0.81%.

---

## Common Pitfalls

- **Skipping idempotency keys.** Without event IDs, any client retry (due to network flakiness or timeout) double-counts. Always generate a stable, client-side UUID per logical event and enforce deduplication at the storage layer.

- **Using a single Cassandra partition per counter.** Writing all events for `play_count:title_123` into one partition creates a hot partition that will overwhelm one Cassandra node and cause write rejections. Time-bucketing is not optional — it is the entire reason the system scales.

- **Rolling up open (still-receiving) buckets.** Aggregating a bucket before its window closes produces an incorrect, permanently undercount rollup. Always wait until `current_time > bucket_end_time` before rolling up. Build in a small grace period (e.g., 30 seconds) to absorb clock skew.

- **Conflating strong and eventual consistency.** A freshly incremented counter will not appear in `GetCount` immediately. If a feature requires "does this user have at least N plays right now?", the eventual consistency model is wrong for that use case — you need a strongly consistent check instead (e.g., a Redis counter with synchronous writes).

- **Not bounding Cassandra partition size.** In a long-lived system, rollup data grows unboundedly unless you also implement time-to-live (TTL) policies on old rollup rows or archive them to cheaper storage. A counter that has existed for years with per-minute buckets accumulates millions of rollup rows.

---

## Exercises

1. **Easy** — Draw the sequence diagram for a single `AddCount` call from a mobile app to the point where EVCache is updated. Label each component (Data Gateway, TimeSeries Abstraction, Rollup Queue, Rollup Worker, EVCache). Identify where idempotency is enforced.

2. **Medium** — Netflix runs active-active in three AWS regions (us-east-1, eu-west-1, ap-southeast-1). A user in Singapore plays a title. An engineer in Virginia reads the play count 500 ms later. Describe how the system reconciles counts across regions. What consistency level should the Cassandra cross-datacenter writes use, and what trade-offs does that create?

3. **Hard** — Design a `ClearCount(counter_id)` operation that resets the counter to zero. Your design must be: (a) idempotent, (b) safe to call while new `AddCount` events are still arriving, and (c) correct after rollup workers re-process old events. Sketch the data model changes and the new rollup logic required to support a "clear epoch" concept.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|------------------------|
| Distributed Counter | A counter replicated across nodes | A system that spreads write responsibility across nodes and reconciles values asynchronously |
| Idempotency | "No duplicate requests" | The same request can be applied N times safely — the result is identical to applying it once |
| Time Bucket | A caching concept | A partition boundary that groups events by time window so old windows become immutable and safe to aggregate |
| Rollup | A summary/report | An aggregation computed over a closed, immutable time window and stored permanently |
| EVCache | A Netflix caching product | Netflix's Memcached-based distributed cache, deployed across AWS regions for low-latency reads |
| Eventual Consistency | "The data will be wrong for a while" | Writes propagate to all readers within a bounded time window (seconds), but there is no synchronous global lock |
| Hot Partition | A busy database server | A single Cassandra partition key that receives a disproportionate share of writes, exhausting one node's I/O |

---

## Further Reading

- [Netflix Tech Blog — Distributed Counter Abstraction](https://netflixtechblog.com/distributed-counter-abstraction-9a6e8e4bf1e0) — The primary source; covers the exact architecture described in this lesson.
- [Netflix Tech Blog — EVCache: Distributed In-Memory Datastore](https://netflixtechblog.com/announcing-evcache-distributed-in-memory-datastore-for-cloud-3f500af04a6b) — How Netflix's caching layer works.
- [Cassandra Data Modeling — Effective Partition Design](https://cassandra.apache.org/doc/latest/cassandra/data_modeling/intro.html) — Official Cassandra docs on partition key design; critical background for the bucketing strategy.
- [Designing Data-Intensive Applications, Chapter 10 — Batch Processing](https://dataintensive.net/) — Martin Kleppmann's treatment of aggregation pipelines underpins the rollup model.
- [HyperLogLog in Practice (Google Research)](https://research.google/pubs/hyperloglog-in-practice-algorithmic-engineering-of-a-state-of-the-art-cardinality-estimation-algorithm/) — For cases where exact counting is not needed; the approximate alternative Netflix uses for unique-user counts.
