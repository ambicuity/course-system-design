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

---

## Deep Enrichment: Ad Click Event Aggregation

### Back-of-the-Envelope Math (Detail)

Worked numbers, step by step, assuming the chapter's headline scale (1B DAU, ~1 click/user/day, 0.1 KB/event).

**Step 1 — Convert daily volume to rates.**
- Daily events: `1 × 10^9 events/day`.
- Seconds per day: `86,400 ≈ 10^5` (use `10^5` as a clean power-of-2-adjacent estimate used in the chapter).
- Average QPS: `10^9 / 10^5 = 10,000 QPS`.
- Peak QPS (5×): `50,000 QPS`.

**Step 2 — Storage.**
- Daily: `10^9 × 0.1 KB = 100 GB/day`.
- Monthly: `100 GB × 30 = 3 TB/month`.
- Yearly: `~36 TB/year` of raw compressed events.

**Step 3 — Aggregated data size.**
Assume per-minute counts kept for 90 days:
- Distinct ads/day ≈ 10^6 active campaigns (estimate — Facebook has reported tens of millions of active ads).
- Per ad, one row per minute × 60 × 24 = 1,440 rows/day.
- Rows/day: `10^6 × 1,440 ≈ 1.44 × 10^9 rows/day`.
- Each aggregated row ≈ 64 bytes → `~92 GB/day` of aggregates.
- 90-day retention: `~8.3 TB`. Aggregates are large; partition by time and ad_id.

**Step 4 — Top-N table.**
- One row per minute per filter_id with a 100-element array: ~100 × 8 B + overhead ≈ 1 KB.
- 1440 minutes/day × ~1,000 filters = 1.44M rows/day × 1 KB ≈ 1.4 GB/day. Trivial.

**Step 5 — Reconciliation job (daily).**
- Re-aggregates 100 GB/day of raw data; fits comfortably in a Hadoop/Spark cluster of ~10 nodes for ~30 minutes (estimate; depends on cluster).

### ASCII Architecture Diagrams

#### 1) End-to-end ingestion + aggregation pipeline (Kappa)

```
+--------+        +---------+       +-----------------+       +-------------+
| Browser|<----->|  Web/App|       |   Producer SDK  |       |   Mobile    |
|  pixel | HTTPS | Server  |       | (click beacon)  |       |   App SDK   |
+--------+        +----+----+       +--------+--------+       +------+------+
                       |                     |                       |
                       v                     v                       v
                  +----+----+        +-------+-------+        +------+------+
                  | API GW  |        |   Load Balancer|        |  Mobile GW  |
                  +----+----+        +-------+-------+        +------+------+
                       \____________________ | _______________________/
                                            v
                                  +---------+---------+
                                  | Kafka cluster     |
                                  | topic: clicks.raw |
                                  | (e.g. 256 parts)  |
                                  +---------+---------+
                                            |
                                            v
                            +---------------+---------------+
                            | Flink job: aggregator        |
                            |  - source(raw)               |
                            |  - keyBy(ad_id + filter_id)  |
                            |  - window(Tumbling 1m)       |
                            |  - process(AggregateFn)      |
                            |  - sink(aggregates topic)    |
                            +---------------+---------------+
                                            |
                                            v
                                  +---------+---------+
                                  | Kafka cluster     |
                                  | topic: agg.out    |
                                  +---------+---------+
                                            |
                +---------------------------+---------------------------+
                v                           v                           v
       +----------------+         +----------------+         +----------------+
       | DB writer      |         | Top-N builder  |         | Search indexer |
       | -> Cassandra / |         | (Flink / Redis)|         | -> Druid/ES    |
       |   ClickHouse   |         +-------+--------+         +-------+--------+
       +-------+--------+                 |                          |
               |                          v                          v
               |                  +-------+--------+        +-------+--------+
               |                  | Top-N cache    |        | OLAP store     |
               |                  | (Redis)        |        | (Druid/Pinot)  |
               |                  +----------------+        +----------------+
               v
       +----------------+
       | Query API      |
       | GET /v1/...    |
       +----------------+
```

#### 2) Sequence: minute-bucket top-N read

```
Client            API GW         Query Svc       Redis (Top-N)   OLAP DB
  |                 |               |                |               |
  | GET /v1/topN?M=1&filter=US     |                |               |
  |---------------->|               |                |               |
  |                 |  validate     |                |               |
  |                 |-------------->|                |               |
  |                 |               | GET topN:US:now|               |
  |                 |               |--------------->|               |
  |                 |               |<-- [ad7,ad9,…]|               |
  |                 |               |                |               |
  |                 |               | (cache miss?)  |               |
  |                 |               |------------------------------->|
  |                 |               |<----------- aggregate rows ---|
  |                 |               |                |               |
  |<-- 200 top100 --|               |                |               |
```

#### 3) Exactly-once state commit (Flink-style checkpoint)

```
   Source           Flink Operator         Kafka tx            State Backend
     |                     |                    |                       |
     | poll + assign ts    |                    |                       |
     |-------------------->|                    |                       |
     |                     | aggregate (in mem) |                       |
     |                     |------------------->| begin tx              |
     |                     |                    | write state changes   |
     |                     |                    |---------------------->|
     |                     |                    | snapshot to S3/HDFS  |
     |                     |                    |---------------------->|
     |                     |                    | commit offsets       |
     |                     |                    |--> commit Kafka tx --|
     |                     |<--- ack -----------|                       |
```

### Trade-off Tables

#### 1) Stream processing framework choice

| Framework | Latency (p99) | Exactly-once | Operational cost | Ecosystem | Best fit |
|-----------|---------------|--------------|------------------|-----------|----------|
| Apache Flink | ~ms–s | Native (Chandy-Lamport) | High (stateful cluster) | Rich (Kafka, RocksDB) | Low-latency, stateful aggregation |
| Apache Spark Structured Streaming | ~s | Micro-batch + idempotent sinks | Medium (YARN/K8s) | Excellent (SQL, ML) | Throughput > latency |
| Kafka Streams | ~ms | Embedded transactional API | Low (no cluster) | Tied to Kafka | Lightweight services on Kafka |
| Apache Beam (portable) | Depends on runner | Runner-dependent | Medium | Portable (Flink/Spark) | Vendor-agnostic pipelines |
| Cloud-managed (Dataflow/KDA) | ms | Yes | Variable | Tight cloud integration | No-ops preference |

#### 2) Aggregation store choice

| Store | Write throughput | Query latency | Aggregation cost | Operational cost | Notes |
|-------|------------------|---------------|------------------|------------------|-------|
| Cassandra | Very high | ms | High (manual roll-up) | Medium | General wide-column |
| ClickHouse | Very high | tens of ms | Low (pre-aggregated + MergeTree) | Low–medium | Columnar OLAP, strong on append-only |
| Apache Druid | High | sub-second | Low (rollups at ingest) | High (Coordinator/MiddleManager/Historical/Broker) | Real-time OLAP, sub-second |
| Apache Pinot | High | sub-second | Low (star-tree indexes) | High | Low-latency OLAP, LinkedIn-origin |
| BigQuery / Redshift / Snowflake | Bulk-only | seconds | Lowest (serverless SQL) | Pay-per-query | Batch-only at this scale |

#### 3) Delivery semantics vs. operational complexity

| Semantics | Complexity | Correctness | Use case |
|-----------|------------|-------------|----------|
| At-most-once | Lowest | Approximate | Non-billing telemetry |
| At-least-once | Low | Approximate (duplicates) | Logs, metrics |
| Exactly-once (idempotent sink + offset) | Medium | Strong | Billing, RTB CTR |
| Exactly-once (Flink two-phase commit) | High | Strong | Stateful, low-latency |

### Real-World Case Studies

#### 1) Facebook — Scribe + Hive + Puma
Facebook's original log infrastructure used **Scribe** to aggregate logs from thousands of web/app servers into HDFS, then **Hive** for batch SQL over the petabyte-scale log store. For near-real-time dashboards, Facebook built **Puma** (and later **Stylus**) on top of HBase and a custom aggregation pipeline. The Scribe→HDFS→Hive flow was effectively a Lambda architecture: a batch path for accuracy plus a streaming path for freshness. (Sources: Facebook engineering blog, 2010–2014.)

#### 2) LinkedIn — Kafka + Gobblin + Pinot
LinkedIn invented **Apache Kafka** (originally for clickstream ingestion), built **Gobblin** to unify batch + stream ingestion into HDFS, and runs **Apache Pinot** as a real-time OLAP store powering dashboards like "site-facing analytics". Pinot's star-tree indexes let them pre-aggregate (a.k.a. roll-up) on common dimensions and serve sub-second queries over billions of events. (Sources: linkedin.github.io/Pinot, Kreps et al. "Kafka: a Distributed Messaging System for Log Processing", NetDB 2011.)

#### 3) Google Analytics / Google — Dataflow + BigQuery
Google Analytics 360 (and the underlying **Dataflow** model formalized in the *Dataflow Model* paper) popularized windowed aggregation with watermarks and exactly-once processing. Under the hood, raw events land in BigQuery (columnar, serverless) and aggregations are served via materialized views / streaming inserts. (Sources: Akidau et al. "The Dataflow Model", VLDB 2015.)

#### 4) Confluent / Apache Kafka exactly-once
Kafka added **transactional producers and read-committed consumers** (KIP-98, KIP-129) to support exactly-once stream processing end-to-end. Flink's two-phase commit sink pattern is the canonical example of stitching Kafka transactions with external systems (Cassandra, MySQL) for atomic offset + result commits. (Sources: Confluent blog "Exactly-Once Semantics Are Possible", 2017.)

#### 5) Snowplow Analytics — open-source event pipeline
Snowplow is an open-source clickstream pipeline analogous to the chapter's design: SDKs emit self-describing JSON events, a **collector** writes them to a sink (Kafka/Kinesis/SQS), **Iglu** provides schemas, and **Spark / Flink enrichment** jobs load data into warehouses (Redshift, BigQuery, Snowflake) or real-time stores (Elasticsearch, Druid). It demonstrates the **Kappa** approach: the same events drive real-time and batch. (Sources: snowplow.io docs.)

#### 6) Segment
Segment's customer data platform ingests events via SDKs, routes them through a **Segment API + message queue**, fans them out to hundreds of downstream destinations, and back-fills from object storage. It is a clear architectural analogue and an industry reference for SDK-side buffering + replay-based backfills. (Sources: Segment engineering blog.)

#### 7) Adobe Analytics / Omniture
Adobe's analytics backend uses **hit-level** event ingestion, partitioning by `reportSuite` and date, with batch roll-ups for the "reports" layer and near-real-time path for live dashboards. The classic decoupling between raw event tables and aggregated report tables is the same trade-off the chapter makes.

### Common Pitfalls & Failure Modes

#### 1) Hot-partition death spiral
**Scenario:** A celebrity or viral ad causes a 100× spike in clicks for `ad_id_popular`. Because Kafka partitioning is by `hash(ad_id)`, all events land on the same broker/partition and the same Flink subtask. The subtask falls behind, Kafka retention expires raw events, late events arrive, watermarks stall.
**Mitigation:** detect hot keys via per-subtask lag metrics; split with `_ad_id_popular_1`, `_ad_id_popular_2`, … in the keyBy function and merge at the reduce step; or use **partial aggregates** keyed by `(ad_id, minute, subkey)` and collapse downstream.

#### 2) Skewed clocks break event-time windows
**Scenario:** Mobile clients send `click_timestamp` from a device with bad NTP. Events arrive with timestamps hours in the past or future. Watermarks never advance; windows never close; aggregation latency explodes.
**Mitigation:** clamp event-time to `[now - maxOutOfOrderness, now]`; track devices with persistently bad clocks and drop or quarantine.

#### 3) Reconciliation gaps hide silent data loss
**Scenario:** Streaming job claims success, but a downstream sink is misconfigured and silently drops events. Reconciliation only compares row counts; if both row counts match the (lower) actual, the gap is invisible.
**Mitigation:** sample-level reconciliation — join a small fraction of raw events to the aggregated output by `(ad_id, event_id)` and assert `count_aggregate = count_raw` for that sample.

#### 4) Idempotency key collision in exactly-once
**Scenario:** A team uses `(ad_id, minute)` as the idempotency key. When a click event straddles a minute boundary (timestamp near minute edge) and is retried, the second write updates the wrong minute bucket.
**Mitigation:** use `(ad_id, event_time_truncated_to_minute, event_id)` with a true unique event_id; record offset and event_id together.

#### 5) Aggregation lag vs. cost trade-off goes silent
**Scenario:** Watermark set to 5 minutes to absorb late events. End-to-end latency creeps from "a few minutes" to 10+ during a network outage. Nobody pages.
**Mitigation:** emit SLO metrics for `p99 end_to_end_lag`; alert if watermark lag > 3× SLO.

#### 6) Backfill poisons the top-N table
**Scenario:** Reprocessing 30 days of raw events for a recalculation also writes top-N rows for historical minutes, overwriting live top-N cache with stale-but-bigger aggregates.
**Mitigation:** separate live and backfill Kafka topics or use a marker header; backfills must write to a different sink (e.g., a `backfill_top_n` table) and never the live `top_n` table.

### Interview Q&A

**Q1 — Clarifications before designing.**
Sketch answer: confirm whether aggregation must be **transactional for billing** (push toward exactly-once and reconciliation) or **directional only** (push toward at-least-once with sampling); confirm whether `top-N` is per-minute only or sliding; confirm filtering cardinality (10s vs. 10,000s of filter_ids); confirm retention (24h vs. 90 days); confirm SLA (sub-minute vs. a few minutes); confirm event schema variability (fixed vs. self-describing).

**Q2 — Capacity estimation.**
Sketch: 1B events/day, ~10K QPS average, 50K peak. Per ad, ~1.44K rows/day of minute aggregates; 90-day retention ≈ 8 TB. Top-N: 100 ads/minute × ~1K filters = ~100K rows/day ≈ 100 MB/day. Kafka: 50K events/s × 0.1 KB ≈ 5 MB/s ingress. Flink cluster: ~10–20 task managers at 4 cores each is a reasonable starting point (estimate; depends on state size).

**Q3 — Deep dive: event-time vs. processing-time.**
Sketch: processing-time is simple but inflates counts when late events arrive after a window has emitted; event-time with watermarks reflects user-visible reality. For RTB-style decisions on the *latest minute*, processing-time is acceptable but produces systematic bias during catch-up. Recommendation: **event-time + watermark** with bounded lateness, plus a periodic late-events repair job.

**Q4 — Hot `ad_id` problem.**
Sketch: detect via per-key rate metrics; split the hot key into N sub-keys at the source by adding a hash suffix; partial-aggregate per sub-key; merge in a downstream reduce by `(ad_id, minute)`; or use **local aggregation** in the SDK (e.g., batch 1,000 clicks into a single event when the device is offline).

**Q5 — "What if we 10×?"**
Sketch: Kafka scales by partitions; we 10× partitions and the Flink job. The aggregated DB becomes the bottleneck first: move from Cassandra to a columnar OLAP (Druid/Pinot/ClickHouse) with roll-up. Aggregation state in Flink exceeds JVM heap → spill to RocksDB state backend. Reconciliation job scales horizontally (Spark on the raw HDFS data).

**Q6 — "What if we go global?"**
Sketch: emit events in-region to the nearest Kafka cluster (eu-west, us-east, ap-southeast). Run Flink regionally to keep aggregation close to the source. Publish aggregates to a central OLAP store for cross-region queries via materialized views or a global aggregator service. Reconciliation is per-region plus a global roll-up. Watch for **time-zone alignment**: aggregate by **UTC minute**, not local time, to avoid skew.

**Q7 — Why not use a single OLAP store and skip the queue?**
Sketch: at 50K QPS writes with second-level freshness, an OLAP store either throttles ingest (Pinot/Druid can saturate on small rows) or bills by ingest (BigQuery). Kafka in front absorbs spikes and lets Flink do incremental pre-aggregation, dramatically reducing the OLAP store's effective write rate (10–100× reduction), which directly controls cost.

**Q8 — How do you prove "exactly-once"?**
Sketch: a probabilistic test — emit 10M events with intentional retries from a load test; assert `count(aggregate) == count(distinct event_id)`. For production, sample-level reconciliation as above. Document the failure mode if Kafka transactions are disabled (counting double on Flink restart) and the operator runbook to re-enable.

### Key Terms / Glossary

| Term | Precise definition | Common misconception |
|------|---------------------|----------------------|
| **Event time** | Timestamp carried in the event payload, set by the producer. | Not the same as the time the aggregator sees the event. |
| **Processing time** | Wall-clock time when the aggregator processes the event. | Aggregating by processing time silently double-counts late events. |
| **Watermark** | A per-partition signal `t` meaning "no event with timestamp ≤ t is expected later". | Watermarks are per-keyspace, not per-record; a single lagging source can stall all windows. |
| **Tumbling window** | Non-overlapping fixed-size window (e.g., `[10:00, 10:01)`). | Not a sliding window; each event belongs to exactly one window. |
| **Sliding window** | Overlapping fixed-size window (e.g., last 5 minutes, recomputed every second). | Cardinality of windows is `time/slide × 1`; cost grows fast at small slide. |
| **Exactly-once** | Each input event contributes exactly once to each output aggregate, even on retries. | Does not mean "no duplicates on the wire"; means **effective** exactly-once after dedup. |
| **Kappa architecture** | One streaming path handles both real-time and reprocessing via log replay. | Sometimes confused with Lambda; Kappa has one codebase, not two. |
| **Lambda architecture** | Two paths: batch (correct, slow) + streaming (fast, approximate); merge at query. | Costly to maintain; not the chapter's recommendation. |
| **Hot key** | A partition key receiving disproportionately more events than peers. | Mitigated by salting/splitting, not by adding brokers. |
| **Reconciliation** | A batch job that re-aggregates raw data and compares to streaming output. | Without it, exactly-once drift is invisible until billing dispute. |
| **Star schema** | Fact table (clicks) joined to dimension tables (filter_ids) at query time. | "Star" refers to the query topology, not a storage layout. |
| **Top-N** | The N highest-count keys in a window. | A naive top-N per minute × 1,000 filters × 1,440 minutes/day is small; per event is intractable. |