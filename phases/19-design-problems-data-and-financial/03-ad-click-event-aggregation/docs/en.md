# Ad Click Event Aggregation

## Background

Digital advertising relies on **RTB (Real-Time Bidding)**, the process where digital ad inventory is bought and sold in well under a second. Online advertising's key benefit is measurability, quantified by core metrics such as **click-through rate (CTR)** and **conversion rate (CVR)**. Ad click event aggregation plays a critical role in measuring ad effectiveness and influences how advertisers bid and pay.

## Step 1: Understand the Problem and Establish Design Scope

### Functional Requirements
- Aggregate the number of clicks of a given `ad_id` in the last M minutes
- Return the top 100 most-clicked `ad_id` every minute
- Support **filtering** by attributes (e.g., `ip`, `user_id`, `country`) along the above queries
- Dataset volume is at Facebook/Google scale

### Non-Functional Requirements
- Correctness of aggregation result is important (data used for billing/RTB)
- Properly handle delayed or duplicate events
- Robustness — the system should be resilient to partial failures
- Latency requirement: end-to-end latency should be a few minutes at most

### Back-of-the-Envelope Estimation
- **1 billion DAU**, each user clicks ~1 ad/day → **1 billion ad click events/day**
- Average ad click QPS = 1B / 10^5 sec ≈ **10,000 QPS**
- Peak QPS ≈ 5× average = **50,000 QPS**
- Assume one ad click event is ~0.1 KB → daily storage = **100 GB/day**, monthly ≈ 3 TB

### Single Ad Click Event Fields
| Field | Description |
|-------|-------------|
| ad_id | The clicked ad |
| click_timestamp | When the ad was clicked |
| user_id | User who clicked |
| ip | IP address |
| country | Country |

---

## Step 2: High-Level Design

### Query API Design
The system answers two main aggregation queries:
1. **Aggregate clicks of `ad_id` in the last M minutes.**
2. **Top N most-clicked `ad_ids` in the last M minutes** (N=100, M=1).

Both support filtering by an arbitrary attribute (filtering is applied to a pre-defined set of filtering ids).

### Data Model

**Raw data vs. aggregated data — store both:**

| | Raw data | Aggregated data |
|---|---|---|
| Pros | Full detail, supports filtering and recalculation; good for debugging | Smaller dataset, fast queries |
| Cons | Huge storage, slow to query | Derived/lossy; aggregation must be correct |

Decision: **store both.** Keep raw data as backup and source of truth (for recomputation/reconciliation); serve queries from aggregated data.

**Aggregated table example:**
| ad_id | click_minute | count |
|-------|--------------|-------|
| ad001 | 202101010000 | 5 |
| ad001 | 202101010001 | 7 |

To support filtering, add a `filter_id` dimension (each row maps to a filter such as `region=US` or `device=mobile`), a technique called the **star schema** with filtering as additional dimensions.

**Top-N table example:**
| update_time_minute | most_clicked_ads | filter_id |
|--------------------|------------------|-----------|

### Why Not a Database Only?
Storing every raw event in a relational database and aggregating with queries at read time does not scale to 50,000 QPS writes and minute-level top-N. A **stream processing** approach is required.

### High-Level Architecture (Streaming)

```
Log Watcher / Producers
        │ (ad click events)
        ▼
   Message Queue #1 (Kafka)  ── raw click events
        │
        ▼
  Aggregation Service (stream processing, e.g., Apache Flink)
        │
        ▼
   Message Queue #2 (Kafka)  ── ad_id minute counts + top-N
        │
        ▼
  Database Writer ──► Aggregation Database (queried by users)
```

**Why two message queues?** A single database cannot meet both write (raw ingestion) and read demands at scale, and decoupling lets the aggregation be reprocessed. The first queue stores raw events; the second stores aggregation results so the database write path is decoupled from computation.

**Why message queue (Kafka) instead of writing aggregation results directly to DB?** Decoupling producers/consumers, buffering bursts, enabling replay, and providing at-least-once delivery semantics.

### Aggregation Service Internals
- Uses the **MapReduce** mental model: **Map** node reads from data source and routes/filters; **Aggregate** node counts ad clicks in memory by minute; **Reduce** node reduces results from all aggregate nodes to a final result (e.g., top-N).
- The map node may repartition events by `ad_id` so the same ad always lands on the same aggregate node.

---

## Step 3: Design Deep Dive

### Streaming vs. Batching
- This is a **near-real-time** system best served by stream processing, but a batch (offline) path is kept for recalculation.
- **Lambda architecture**: two paths — batch (accurate, slow) + streaming (fast, approximate). Downside: maintain two codebases.
- **Kappa architecture**: single stream-processing path handles both real-time and reprocessing (replay from the log). **Recommended** — the design unifies the real-time aggregation and historical recalculation in one path. Raw data is replayed through the same aggregation logic for recalculation.

### Time: Event Time vs. Processing Time
- **Event time:** when the click actually happened (in the event payload).
- **Processing time:** when the aggregation server processes the event.
- Aggregating by **event time** is more accurate but must wait for late/out-of-order events; aggregating by **processing time** is simpler but inaccurate when events are delayed.
- Recommendation: aggregate by **event time** and handle lateness with a **watermark**.

### Watermark
A watermark defines how long the system waits for late events before finalizing a window. A short watermark reduces latency but may drop late events (lower accuracy); a longer watermark increases accuracy but adds latency. The window is finalized when the watermark passes the window end.

### Window Types
- **Tumbling (fixed) window:** non-overlapping fixed intervals (e.g., per-minute counts). Best fit for "clicks per minute".
- **Sliding window:** overlapping windows for queries like "clicks in the last M minutes".

### Delivery Guarantees & Exactly-Once
- **At-least-once** is the default from Kafka and may double count.
- For billing-grade correctness, aim for **exactly-once** semantics.
- Achieved with: **distributed transactions / two-phase commit** between Kafka offsets and the aggregation state store, or **idempotent** writes keyed by `(ad_id, minute, partition)` plus offset tracking.
- The aggregation result and the consumer **offset** must be committed atomically so a crash-and-restart does not double-count or lose data.

### Deduplication
- Events can be duplicated by an upstream producer retry or a consumer that crashes after writing results but before committing offsets.
- Detect duplicates via a unique event id; track processed offsets durably; commit offset and result together.

### Reconciliation
- A **reconciliation** (batch) job runs daily: it re-aggregates raw events from a partitioned store (e.g., HDFS) and compares to the streaming results. Discrepancies are corrected.
- This is the safety net that justifies storing raw data.

### Scalability
- **Message queue:** scale by adding Kafka **partitions**; partition by `ad_id` for locality. Hash-based partitioning spreads load.
- **Aggregation service:** scale horizontally; each node owns a set of partitions; use a resource manager (YARN/Kubernetes) to allocate map/aggregate/reduce nodes.
- **Database:** the aggregation database (e.g., Cassandra) scales by sharding/partitioning on `ad_id` + time; supports high write throughput and time-series access.

### Hotspot / Hot ad_id Problem
A celebrity or viral ad can create a hot partition. Mitigations:
- **Split a hot key** across multiple aggregation nodes by appending a random suffix (`ad_id_1`, `ad_id_2`, …) and merging in the reduce step.
- Allocate more resources to nodes processing popular ads.

### Fault Tolerance
- Aggregation is **stateful** (counts held in memory). On node failure, recover by **replaying** events from the message queue, using saved offsets/checkpoints.
- Take periodic **snapshots/checkpoints** of the aggregation state so recovery replays only since the last checkpoint, not from the beginning.

### Monitoring & Alerting
- Monitor latency (events spend time in queues + processing), message queue size (backpressure indicator), and aggregation node CPU/memory.
- Alert on growing lag or correctness drift detected by reconciliation.

---

## Step 4: Wrap Up

### Summary of Components
- **Log watcher / producers** → emit click events
- **Kafka (queue 1)** → durable raw event log
- **Aggregation service (Flink/MapReduce model)** → event-time aggregation with watermarks, tumbling windows, exactly-once
- **Kafka (queue 2)** → aggregation results
- **Database writer → Aggregation DB (Cassandra)** → serves queries
- **Raw data store (HDFS) + reconciliation job** → recomputation and correctness backstop

### Key Talking Points
- Store both raw and aggregated data; raw enables recomputation and debugging.
- Use Kafka + stream processing (Kappa architecture) for near-real-time aggregation.
- Aggregate by **event time** with **watermarks** to handle late/out-of-order events.
- Achieve **exactly-once** via atomic offset+result commits; deduplicate.
- **Reconciliation** batch job guarantees long-term correctness for billing.
- Handle **hotspots** by splitting hot keys; ensure fault tolerance via replay + checkpoints.
