# Design a Metrics Monitoring and Alerting System

A metrics monitoring and alerting system collects operational metrics from a large fleet (servers, services, containers), stores them as time series, lets engineers query and visualize them on dashboards, and fires alerts when conditions are violated. The canonical real-world references are **Prometheus + Grafana** and large-scale internal systems (Facebook Gorilla, Google Monarch). This is fundamentally a **time-series data** problem with a write-heavy, append-only ingest path.

---

## Step 1 — Understand the Problem and Establish Scope

### What kind of telemetry?

The "three pillars" of observability are **metrics, logs, and traces**. They have very different shapes:

- **Metrics**: numeric measurements over time (CPU %, request rate, error count, latency). Low cardinality per point, high volume, aggregatable. **This is our focus.**
- **Logs**: discrete, high-cardinality text/structured events. Different storage (search index).
- **Traces**: causal spans across services. Different storage again.

We explicitly scope to **metrics**, and acknowledge logs/traces as separate (related) systems.

### Functional requirements

1. **Collect metrics** from thousands of hosts/services.
2. **Store** them efficiently as time series for a configurable retention period.
3. **Query** metrics (e.g., "p99 latency of service X over the last hour, by region").
4. **Visualize** via dashboards.
5. **Alert** when rules are violated (e.g., error rate > 5% for 5 minutes) and **notify** via email/Slack/PagerDuty.

### Non-functional requirements

- **High write throughput / scalability**: ingest is enormous and continuous.
- **Low query latency** for dashboards (interactive) — but queries are far fewer than writes.
- **High availability** of ingest and alerting — losing monitoring during an incident is unacceptable.
- **Durability** to the level the use case needs; metrics can tolerate tiny loss more than, say, billing data, but alerting must be reliable.
- **Cost efficiency at scale**: compression and downsampling are essential, not optional.

### Back-of-the-envelope

Assume:
- **10 M time series** actively reported (e.g., 100k hosts × 100 metrics each, multiplied by label combinations).
- Scrape/report interval **10 s** → `10,000,000 / 10 = 1 M data points/sec` ingest.
- Each raw point ≈ 16 bytes (timestamp + float) before compression; specialized TSDB compression (delta-of-delta timestamps + XOR float encoding, à la Gorilla) gets this down to **~1–2 bytes/point**.
- Storage/day raw ≈ `1M/s × 86400 × 16B ≈ 1.4 TB/day`; compressed ≈ **~100–200 GB/day**. Retention of months means downsampling old data is mandatory.

**Key asymmetry**: writes dominate by orders of magnitude over reads. Design the ingest path for throughput; design the query path for flexibility and interactive latency.

---

## Step 2 — High-Level Design

### Data model: the time series

A **metric** is identified by a name + a set of **labels (key-value tags)**, and is a sequence of `(timestamp, value)` data points:

```
http_requests_total{service="checkout", method="POST", region="us-east", status="500"}
   -> (t0, v0), (t1, v1), (t2, v2), ...
```

- The **unique combination of metric name + label set = one time series**.
- **Cardinality** = number of distinct label combinations. High cardinality (e.g., putting `userId` in a label) explodes the number of series and is the #1 way to blow up a metrics system. Labels must be **bounded-cardinality** dimensions (region, status code, host), never unbounded ids.

### Components

```
 Targets ──(pull)──▶ ┌───────────┐                ┌──────────────┐
 (exporters)         │ Collector │──▶ (Kafka) ──▶ │  Ingestion/  │──▶ Time-Series DB
 Apps ──(push)─────▶ │  / Scraper│   (buffer)     │  Consumers   │     (+ downsampling)
                     └───────────┘                └──────────────┘            │
                                                                              ▼
        Alerting Engine ◀── Query Service ◀────────────────────────── Query/Read API
              │                    ▲
              ▼                    │
        Notification          Visualization (Grafana-style dashboards)
        (email/Slack/Pager)
```

1. **Collection** (pull or push) gathers raw data points.
2. **Optional message queue (Kafka)** buffers the firehose, decouples collection from storage, and absorbs bursts/backpressure.
3. **Ingestion consumers** write to the **time-series database (TSDB)**.
4. **Downsampling/rollup** jobs precompute lower-resolution aggregates for old data.
5. **Query service** serves reads (with a query language) to dashboards and the alerting engine.
6. **Visualization** (Grafana-style) renders dashboards.
7. **Alerting engine** evaluates rules on a schedule and dispatches **notifications**.

---

## Step 3 — Design Deep Dive

### 3.1 Collection: pull vs push

The most debated tradeoff in metrics systems.

| | **Pull** (server scrapes targets) | **Push** (targets send to server) |
|---|---|---|
| Examples | Prometheus | StatsD, Graphite, OpenTelemetry push, Monarch (partly) |
| Target discovery | Server uses **service discovery** to know what to scrape | Targets need to know the collector endpoint |
| Health signal | A scrape failure *is* a "target down" signal — free liveness check | Must infer down-ness from absence of data |
| Firewall/NAT | Server must reach targets (harder across network boundaries) | Targets initiate outbound (easier through NAT) |
| Short-lived jobs | Hard — job may die before scrape (need a **push gateway**) | Natural fit — job pushes before exiting |
| Load control | Server controls scrape rate; easy to throttle | Targets can overwhelm the collector; needs rate limiting |
| Ephemeral/serverless | Awkward | Better |

**Pull** (Prometheus model) is clean for dynamic infrastructure with service discovery and gives a built-in up/down signal. **Push** suits short-lived jobs, serverless, and cross-network-boundary cases. Large systems often support **both**, with a **push gateway** to bridge short-lived jobs into a pull-based core.

**Scaling collection**: a single collector can't scrape millions of series. **Shard collectors** by target (e.g., by service or by hash of target), and/or run a hierarchy of collectors that **federate** up to a global view.

### 3.2 Why a Kafka buffer in the middle

Placing a durable queue (Kafka) between collection and the TSDB:

- **Absorbs bursts** so a spike in metrics doesn't drop data or crash the TSDB.
- **Decouples** producers (collectors) from consumers (TSDB writers) — each scales independently.
- **Backpressure & replay**: if the TSDB is slow or being upgraded, data buffers in Kafka and consumers catch up; you can replay on failure.
- **Fan-out**: multiple consumers (TSDB writer, real-time alerting, anomaly detection) read the same stream.

Trade-off: it adds operational complexity and a dependency. Simpler/smaller deployments (vanilla Prometheus) skip it and scrape straight into local storage; very large pipelines (Kafka → consumers → TSDB) add it for resilience and scale. Mention both and pick based on scale.

### 3.3 Time-series database

Why not a general-purpose RDBMS? Metrics workloads are: append-mostly, time-ordered, write-heavy, with range-scan-by-time queries and aggregation. Purpose-built **TSDBs** exploit this:

- **Append-only, time-partitioned storage**: data written in time order; old chunks are immutable and easy to expire.
- **Specialized compression**: **delta-of-delta** encoding for timestamps (regular intervals compress to almost nothing) and **XOR** encoding for floats (consecutive values are similar) — the Gorilla techniques. ~1–2 bytes/point.
- **Recent-data in memory**: hot, recent data lives in memory / an in-memory chunk (Gorilla kept ~26h in RAM) for fast writes and queries; older chunks flush to disk/object storage.
- **Inverted index on labels**: to resolve `{service="checkout", region="us-east"}` to the matching series quickly.
- Examples: Prometheus TSDB, InfluxDB, TimescaleDB, M3DB, VictoriaMetrics, Cortex/Thanos (horizontally scalable Prometheus), Monarch.

**Scaling the TSDB**:
- **Shard by series** (hash of metric+labels) and/or **by time** so writes distribute across nodes.
- **Replicate** shards for availability.
- **Tiered storage**: recent high-resolution data on fast local storage; older downsampled data on cheap object storage (S3) — as Thanos/Cortex/M3 do.

### 3.4 Downsampling and rollups

You cannot keep 10-second resolution for a year — the volume is enormous and nobody queries year-old data at 10 s granularity. **Downsampling** precomputes coarser aggregates as data ages:

| Age | Resolution | Example |
|---|---|---|
| 0–7 days | raw (10 s) | full fidelity for recent debugging |
| 7–30 days | 1 min rollups | dashboards over a month |
| 30 days–1 year+ | 1 hour rollups | long-term trends, capacity planning |

- Rollups store aggregates (min/max/avg/sum/count, and quantile sketches) per window so queries over long ranges stay cheap and fast.
- Old raw data is then expired per the retention policy.
- This is a **batch/streaming job** that reads recent data and writes lower-resolution series.

**Note on percentiles**: you cannot average pre-aggregated percentiles. Latency quantiles need **histograms** (bucketed counts) recorded at ingest, so quantiles can be computed/merged correctly across time and instances (e.g., Prometheus histogram + `histogram_quantile`).

### 3.5 Query service and query language

- A **query service** sits in front of the TSDB, exposing a query language (PromQL-style) for selecting series by labels, applying functions (rate, increase, avg, percentile), aggregating across dimensions, and over time windows.
- **It serves two clients**: interactive dashboards and the alerting engine (alert rules are just queries with a threshold).
- **Optimizations**: a **caching layer** for repeated dashboard queries, query result pre-aggregation, fan-out/scatter-gather across shards then merge, and pushing aggregation down to storage nodes.
- Reads are far fewer than writes, but dashboards issue **many concurrent panel queries**; cache and limit expensive unbounded queries.

### 3.6 Visualization

- A dashboard layer (Grafana-style) renders panels: time-series line charts, heatmaps, gauges, tables.
- Each panel is one or more queries against the query service on an auto-refresh interval.
- Don't build this from scratch in an interview — Grafana is the de facto standard; the system exposes a query API it talks to.

### 3.7 Alerting

The alerting pipeline:

1. **Rule definition**: declarative rules, e.g. `avg(rate(http_errors[5m])) / avg(rate(http_requests[5m])) > 0.05 for 5m`. Rules include a condition, a duration ("for"), severity, and routing labels.
2. **Rule evaluation**: an **alert manager / evaluator** runs each rule on a schedule (e.g., every 15–60 s) by querying the metrics store. Evaluation is itself sharded across many rules.
3. **State machine**: a rule moves `inactive → pending` (condition true but not yet for the required duration) `→ firing`. The **"for" duration prevents flapping** on transient spikes.
4. **Deduplication & grouping**: collapse many related alerts (e.g., 500 hosts of one service) into one notification; group by labels.
5. **Silencing & inhibition**: mute alerts during maintenance; suppress downstream alerts when a root-cause alert is firing (a cluster-down alert inhibits the per-node alerts).
6. **Routing & notification**: route by severity/team to channels — **email, Slack, PagerDuty, webhooks** — with escalation policies.
7. **Reliability**: the alerting path must stay up even when things are on fire. Run the alert manager **highly available / replicated** (e.g., Prometheus Alertmanager gossip-clustered) so a single node failure doesn't silence alerts, and **deduplicate** across the redundant evaluators.

**Why evaluate alerts as queries**: reusing the query engine means rules are expressive and consistent with dashboards. Some systems also do **streaming/real-time alerting** off the Kafka stream for the lowest-latency, simplest threshold alerts, bypassing the round-trip to the TSDB.

---

## Step 4 — Wrap Up

### How requirements map to the design

- **Scale of writes** → pull/push collectors (sharded) + Kafka buffer + horizontally sharded TSDB with aggressive compression.
- **Retention without runaway cost** → downsampling/rollups + tiered storage + retention policies.
- **Interactive queries** → query service with caching, scatter-gather, and a metrics query language.
- **Alerting reliability** → HA alert manager, dedup/grouping, silencing/inhibition, "for" durations to avoid flapping.

### Bottlenecks and mitigations

| Bottleneck | Mitigation |
|---|---|
| Ingest firehose | Kafka buffer, sharded collectors/consumers |
| **Cardinality explosion** | Forbid unbounded labels (no user ids); enforce label budgets; reject/limit high-cardinality series |
| TSDB write/query load | Shard by series + time, replicate, tiered storage |
| Storage cost over time | Downsampling + compression + retention tiers |
| Hot dashboards | Query cache, pre-aggregation, query limits |
| Alert flapping / storms | "for" durations, grouping, dedup, inhibition |
| Monitoring availability during incidents | HA alert manager, independent failure domains, push-gateway resilience |

### Closing talking points

- A metrics system is a **time-series storage problem** dominated by **write throughput**; everything keys off the `(metric + labels) → (timestamp, value)` model.
- **Cardinality discipline** is the make-or-break operational concern — call it out explicitly.
- **Pull vs push** is the signature tradeoff; real systems often support both with a push gateway.
- **Specialized compression + downsampling + tiered storage** are what make multi-month retention affordable.
- **Alerting must be more reliable than the things it monitors** — HA, dedup, and anti-flap controls are first-class, not afterthoughts.
- This mirrors **Prometheus (pull, TSDB, PromQL, Alertmanager) + Grafana (visualization)**, scaled out with Kafka/Thanos/Cortex/M3-style components for very large fleets.

---

## Deep Dive: Back-of-the-Envelope Math

Working in powers of 2 and realistic constants for a large-fleet operation.

### Constants and assumptions

| Constant | Value | Notes |
|---|---|---|
| Hosts | 100,000 | 10^5 |
| Containers per host | 5 | 5 × 10^5 services |
| Metrics per service | 100 | 5 × 10^7 base metrics |
| Cardinality multiplier (labels) | 200 | bounded combinations of region/zone/status/etc. |
| **Active time series** | **~10 M** (10^7) | realistic for a moderate-sized fleet |
| Scrape interval | 10 s | |
| Ingest rate | 1 M samples/sec | `10^7 / 10` |
| Sample size (raw) | 16 B | 8 B timestamp + 4 B float + 4 B metadata |
| Compression ratio | 8–16× | Gorilla-style delta-of-delta + XOR |
| Days of raw retention | 7 | |
| Days of 1-min rollup | 30 | |
| Days of 1-hour rollup | 365 | |

### Storage

- Raw (uncompressed): `1 M/s × 16 B × 86,400 s = 1.4 TB/day`
- Compressed: `1.4 TB / 8 = ~175 GB/day` (Gorilla-class compression)
- 7 days raw: `1.2 TB`
- 30 days of 1-min rollup: 30 days × 24 h × 60 min × 16 B/point × 1 sample/min × 10^7 series / 8 ≈ ~50 TB — but most series are much sparser at 1-min resolution; realistic is closer to 5–10 TB.
- 365 days of 1-hour rollup: ~50 GB.
- **Total 1-year retention: ~10–20 TB compressed** for a 10 M active series fleet. At AWS S3 prices, this is **~$200–400/month** in storage. The dominant cost is compute, not storage.

### Ingest

- A single Prometheus instance handles ~1 M active series comfortably on modest hardware.
- For 10 M series, run 10+ Prometheus shards behind a Thanos/Cortex/M3 coordinator.
- Each shard does ~100k samples/sec ingest, well within one modern disk's sequential write capacity.

### Queries

- Dashboard panel refresh: 10 s × 50 panels × 100 concurrent users = ~500 queries/sec peak from the dashboards alone.
- Alert evaluation: 1,000 rules × 1/30s = ~33 queries/sec.
- Total: ~1 k QPS. Order of magnitude smaller than ingest — this is the asymmetry.

### Network

- Ingest: 1 M/s × 16 B = 16 MB/s raw, 2 MB/s compressed. Trivial.
- Cross-AZ replication: another 2 MB/s. Trivial.
- Query fan-out: bounded by dashboard concurrency.

### Alerting latency budget

- Scrape: 10 s
- TSDB write: 1 s
- TSDB visibility: 1 s
- Alert evaluation cycle: 30 s (configurable)
- Notification: 5 s
- **End-to-end alert latency: ~50 s** (10 s scrape + 30 s eval + 5 s notify). Configurable down to ~5 s with streaming alerts, at the cost of complexity.

---

## Deep Dive: ASCII Architecture Diagrams

### Diagram 1 — Pull-based Prometheus-style collection (sequence)

```
  Prometheus    Service Discovery   Target App    TSDB (local)    Alertmanager    Notification
      │                │                 │              │                │                │
      │ discover       │                 │              │                │                │
      │────────────────▶                │              │                │                │
      │                │ list of targets │              │                │                │
      │                │────────────────▶              │                │                │
      │                │                 │              │                │                │
      │ GET /metrics   │                 │              │                │                │
      │──────────────────────────────────▶              │                │                │
      │                │                 │              │                │                │
      │ metric samples │                 │              │                │                │
      │◀──────────────────────────────────              │                │                │
      │                │                 │              │                │                │
      │ append to head block, periodically flush to disk                │                │
      │─────────────────────────────────────────────▶  │                │                │
      │                │                 │              │                │                │
      │  (alerting tick)                │              │                │                │
      │ eval rule                       │              │                │                │
      │─────────────────────────────────────────────▶  │                │                │
      │                │                 │              │                │                │
      │                │                 │              │ rule fired     │                │
      │                │                 │              │────────────────▶                │
      │                │                 │              │                │ notify         │
      │                │                 │              │                │───────────────▶│
```

### Diagram 2 — Large-scale pipeline (Kafka-buffered)

```
  Targets           Collectors         Kafka           Ingest Workers        TSDB Shards
     │                  │                │                    │                    │
     │ /metrics         │                │                    │                    │
     │─────────────────▶│                │                    │                    │
     │                  │ produce        │                    │                    │
     │                  │ (batched, 32KB)│                    │                    │
     │                  │───────────────▶│                    │                    │
     │                  │                │ consume batch      │                    │
     │                  │                │ (shard by series)  │                    │
     │                  │                │───────────────────▶│                    │
     │                  │                │                    │                    │
     │                  │                │                    │ append (Gorilla    │
     │                  │                │                    │  compression)      │
     │                  │                │                    │───────────────────▶│
     │                  │                │                    │                    │
     │                  │                │  (parallel: real-time alerting, anomaly detection)
     │                  │                │                    │                    │
     │                  │                │ consume (filter)   │                    │
     │                  │                │───────────────────▶│ rule engine         │
     │                  │                │                    │   (in-process)     │
     │                  │                │                    │                    │
     │                  │                │                    │ notify             │
     │                  │                │                    │──────▶             │
     │                  │                │                    │                    │
     │                  │                │                    │  (downsample after N hours)
     │                  │                │                    │                    │
     │                  │                │                    │ 1-min rollup       │
     │                  │                │                    │───────────────────▶│
     │                  │                │                    │ 1-hour rollup      │
     │                  │                │                    │───────────────────▶│ S3
```

### Diagram 3 — Alert state machine

```
              ┌────────────────┐
              │   INACTIVE     │  (no condition met)
              └────────┬───────┘
                       │  condition true
                       ▼
              ┌────────────────┐
              │    PENDING     │  (condition true, but "for" duration not yet elapsed)
              └────────┬───────┘
                       │  "for" duration elapsed
                       ▼
              ┌────────────────┐
              │    FIRING      │  (alert sent to Alertmanager; pages / notifies)
              └────────┬───────┘
                       │  condition no longer true
                       ▼
              ┌────────────────┐
              │   RESOLVED     │  (notification: "alert cleared")
              └────────────────┘

  Example: error rate > 5% for 5 minutes
    t=0:    error rate spikes to 7%        → PENDING
    t=5m:   still 7%                      → FIRING (page on-call)
    t=12m:  error rate drops to 2%        → RESOLVED
```

The "for" duration is the **anti-flap** mechanism: without it, a 30-second spike pages the on-call. With `for: 5m`, only sustained conditions page.

### Diagram 4 — Sharded TSDB with query fan-out

```
  Query (PromQL):    rate(http_requests_total[5m]) by (service)

  Query Service (router)
        │
        │  hash({__name__="http_requests_total", region=*}) →
        │  identifies relevant shards
        │
        ├──▶ Shard A (region: us-east)  ──▶ partial result
        ├──▶ Shard B (region: us-west)  ──▶ partial result
        ├──▶ Shard C (region: eu)       ──▶ partial result
        └──▶ Shard D (region: apac)     ──▶ partial result
                       │
                       ▼
                Query Service (merge)
                       │
                       ▼
                   final result
```

A scatter-gather query service hides sharding from the user. The cost model: each shard does a partial scan; the merge is in-memory; total latency is `max(shard_latency) + merge_time + network_RTT`. For a 4-shard cluster, this is ~2–4× the single-shard latency, often acceptable.

---

## Deep Dive: Trade-off Tables

### 1. Collection: pull vs push

| Property | **Pull (Prometheus)** | Push (StatsD / OTel push) |
|---|---|---|
| Target discovery | service discovery (K8s, Consul, file_sd) | targets need to know endpoint |
| Liveness check | free (failed scrape = down) | inferred (no data = ?) |
| NAT/firewall | harder | easier |
| Short-lived jobs | awkward (push gateway) | natural |
| Load control | server (centralized) | client (need rate limits) |
| Multi-tenant | one Prometheus per tenant | one collector per cluster |
| Best for | long-running services, K8s | serverless, mobile, batch jobs |

### 2. TSDB storage: local-only vs remote-write vs tiered

| Property | **Local-only (vanilla Prometheus)** | Remote-write (Cortex, Thanos) | Tiered (M3, Cortex v2) |
|---|---|---|---|
| Durability | single-node (1 replica) | replicated in object store | replicated, tiered |
| Cross-cluster query | no | yes (Querier) | yes |
| Long retention | bounded by local disk | unbounded (S3) | unbounded |
| Operational complexity | low | medium | medium-high |
| Query latency (recent) | very low | medium (network hop) | low |
| Query latency (old) | low | medium (S3 scan) | medium |

### 3. Alerting: pull-from-TSDB vs stream-from-Kafka

| Property | **Query-based (Prometheus)** | Stream-based (Kafka consumer) |
|---|---|---|
| Latency | 30–60 s (eval interval) | sub-second |
| Expressiveness | full PromQL | limited (simple thresholds) |
| Reuses query layer | yes | no |
| Failure mode | TSDB lag → stale alerts | Kafka lag → stale alerts |
| Best for | most rules | page-on-spike, anomaly, fraud |

### 4. Storage backend: Gorilla compression vs columnar vs append-only LSM

| | Gorilla (Prometheus) | Columnar (InfluxDB IOx) | LSM (VictoriaMetrics) |
|---|---|---|---|
| Compression | ~1.3 B/point | ~2 B/point (parquet) | ~1 B/point |
| Merge cost | chunk-based | parquet re-write | merge-heavy |
| Read pattern | scan chunks | columnar scan | seek + scan |
| Best for | time-range scans | analytical queries | mixed read/write |

### 5. Notification: pull (webhook) vs push (PagerDuty API) vs email

| Channel | Reliability | Latency | Best for |
|---|---|---|---|
| PagerDuty API | high (managed, ack) | seconds | on-call paging |
| Slack | medium (depends on Slack uptime) | seconds | team awareness |
| Email | medium | minutes | non-urgent, audit |
| Webhook | depends on receiver | seconds | custom integrations |
| SMS (via PagerDuty) | high | seconds | critical, last-resort |

---

## Deep Dive: Real-World Case Studies

### Facebook Gorilla (TSDB)

The Gorilla paper (Pelkonen et al., 2015, "Gorilla: A Fast, Scalable, In-Memory Time Series Database") is the canonical reference for the compression techniques used in modern TSDBs.

- **In-memory design**: Gorilla keeps the last ~26 hours of data in RAM (a single 1U server with 144 GB held ~1.6 M unique series at 10 s resolution). Older data flushes to a columnar on-disk format.
- **Compression**: delta-of-delta for timestamps (regular intervals encode to a single bit "same as before" or a small offset) and XOR for floats (consecutive values share many bits, so XOR is mostly zeros). Empirical result: ~1.37 bytes per data point — a 12× improvement over uncompressed.
- **Lessons for our design**: in-memory + flush is the right pattern for "recent data is hot, old data is cold." Compression is not optional; the techniques are well-known and cheap to implement.

### Google Borgmon / Monarch

Borgmon and Monarch are Google's internal monitoring systems, the predecessors of what became public as Monarch (publicly described in 2020). They are the largest-scale examples of the patterns in this chapter.

- **Borgmon** (pre-2015): the "pull from every Borg job" model. A distributed set of collectors scrapes every binary's `/varz` endpoint. Rule evaluation ran as a streaming pipeline (each rule was a small program) so alerts fired in seconds, not minutes.
- **Monarch** (current): global, multi-tenant, sharded TSDB. Uses a custom query language (MQL), tiered storage with recent data in memory and older data in Bigtable/Colossus, and federated alert evaluation.
- **Architectural lessons**:
  - **Treat monitoring as a first-class distributed system**, not a side project. Sharding, replication, and HA are as important as for the user-facing services it monitors.
  - **Push and pull coexist** — push for short-lived jobs (MapReduce), pull for long-running services.
  - **Alerts are not a query result**, they're a derived stream; evaluation can be done in the dataflow pipeline itself, with sub-second end-to-end latency.

### Prometheus

Prometheus (2012–, CNCF graduated 2018) is the open-source canonical implementation of this design.

- **Pull model** with service discovery; multiple scrape strategies (file, K8s, Consul, DNS, EC2, etc.).
- **Gorilla-style TSDB** with on-disk block storage; long-term via Thanos/Cortex/M3.
- **PromQL** — the de facto standard query language for metrics.
- **Alertmanager** — the de facto standard alert routing engine; gossip-clustered for HA.
- **Ecosystem**: hundreds of exporters for everything from MySQL to HAProxy to Kubernetes itself; client libraries in every language; Grafana as the de facto dashboard.

### Grafana

Grafana is the de facto visualization layer, sitting in front of Prometheus, InfluxDB, Elasticsearch, CloudWatch, and many more. It is a query-renderer, not a storage system.

- **Lessons for our design**: don't build your own dashboard layer. Grafana's data-source plugin model means your query API can be adopted without a custom UI.

### InfluxDB

InfluxDB is a competing TSDB with a SQL-like query language (InfluxQL, now Flux). Its 2.0 release introduced **IOx**, a columnar Rust-based storage engine with Parquet on object storage.

- **Architectural lessons**: columnar storage is competitive with Gorilla on compression and is much better for analytical queries (min/max/avg over long ranges). It is also more expensive to merge. The trade-off is "scan speed vs. write amplification."

### TimescaleDB

TimescaleDB is a PostgreSQL extension that turns Postgres into a TSDB via **hypertables** (auto-partitioned by time) and **continuous aggregates** (the equivalent of downsampling).

- **Architectural lessons**: you can build a perfectly fine TSDB on a relational engine with the right partitioning and compression. The advantage is **SQL** — joins against other relational data, ad-hoc analytics, transactional updates. The disadvantage is **operational complexity** at very high write rates.

### OpenTelemetry

OpenTelemetry is the modern standard for instrumenting applications and emitting telemetry. It is not a TSDB but a **client + collector + protocol** (OTLP).

- **Push or pull** — OTel SDK can be configured either way; most production setups use the **OTel Collector** as a central pull-and-forward tier.
- **Three pillars** — metrics, logs, traces in one protocol. The metrics path produces Prometheus-compatible data when configured to.
- **Lessons for our design**: OTel is the right answer to "what should my application use to emit metrics?" Don't define a custom protocol; use OTLP.

### Datadog

Datadog is the commercial SaaS that does all of the above (metrics, logs, traces, APM, alerting) with strong defaults and a managed service.

- **Architectural lessons**: the "ingest-everything" model is feasible at scale if you (a) charge by host/ingest (which limits per-customer cardinality), (b) use aggressive aggregation and sampling on the agent, and (c) build tiered storage. Datadog's per-second pricing reflects the real cost of high-cardinality metrics.

### Honeycomb

Honeycomb is a higher-cardinality observability system (think "wide events" with arbitrary fields, not just `(metric, labels)`).

- **Architectural lessons**: traditional metrics systems (Gorilla-style) compress away high-cardinality data. For "what request caused this latency spike?" you need an event store, not a TSDB. Honeycomb's model is "store every event with arbitrary fields; query by any field." The cost is 10–100× more storage; the benefit is debuggability.

### Lightstep

Lightstep (acquired by ServiceNow) is a tracing-first observability system that uses **satellite sampling** and **adaptive sampling** to bound ingest cost.

- **Lessons for our design**: sampling is the right answer when ingest cost dominates. For metrics, sampling is rare (you want every data point); for traces, it is standard. The same architectural reasoning applies: **don't store what you can't afford**.

---

## Deep Dive: Common Pitfalls & Failure Modes

### 1. Cardinality explosion

**Symptom:** the TSDB suddenly has 100× more series. Memory pressure; ingest slows to a crawl; queries time out; everything is on fire.

**Root cause:** a developer adds a `userId` or `requestId` label, or a new status code, or some other unbounded dimension. The number of series goes from 10 M to 10 B.

**Fix:**
- Enforce a **label whitelist** at the collector: only specific label keys are allowed; unknown labels are dropped or rejected.
- Set a **series-per-metric budget** (e.g., max 10 k series per metric name) and reject writes that exceed it.
- Monitor `tsdb_head_series` (Prometheus) or equivalent; alert on >N series.
- Educate: a "metrics labels" doc that lists the allowed dimensions and explicitly forbids unbounded ids.

### 2. Alert fatigue / flapping

**Symptom:** pages fire constantly for transient conditions. The on-call team ignores pages. The real incident gets missed.

**Root cause:** rules without a `for` duration fire on every spike. Or the threshold is wrong. Or the alert is for a condition that doesn't actually require action.

**Fix:**
- Every alert must have a `for` duration (typically 5–15 min for warning, 1–2 min for page).
- Group by cluster, region, or service so 500 hosts produce one alert, not 500.
- Use **inhibitions**: a cluster-down alert inhibits per-host alerts. A database-down alert inhibits per-query alerts.
- Maintain an alert SLO: if a page is acknowledged and silenced within 5 min, count it as "noisy" and review.

### 3. Monitoring itself goes down during an incident

**Symptom:** the system is failing but Grafana shows the last data from 30 minutes ago. The alerting engine is also down; no pages are sent.

**Root cause:** the TSDB is in the same failure domain as the services it monitors (e.g., they all share a K8s cluster with a node failure, or all depend on the same database). The monitoring pipeline is treated as a side project, not as critical infrastructure.

**Fix:**
- Run monitoring in a **separate failure domain** (different region, different cloud account) from what it monitors.
- HA the alertmanager (gossip-clustered, with dedup across replicas).
- Have a **fallback notification path**: SMS via PagerDuty that is independent of the main monitoring stack.
- **Out-of-band health check** — a tiny service that does a "is monitoring working?" check, distinct from the main monitoring.

### 4. The 10-second scrape interval doesn't match 30-second alert eval

**Symptom:** alerts fire on stale data. The "5-minute error rate" alert fires, but the data was 4 minutes old when evaluated.

**Root cause:** the alert evaluation interval is too aggressive for the data's freshness. The 5-minute window contains fewer than 30 points (10 s scrape × 30 = 30 points), so the rate calculation is sparse.

**Fix:**
- Match `evaluation_interval` to `scrape_interval` (or use the same time base).
- Set `for` duration to at least 2× the evaluation interval to allow for jitter.
- Use `rate()` with care: it requires at least 2 points in the window; if the scrape is missing, the rate is wrong.

### 5. Stale dashboards

**Symptom:** a dashboard shows 2 weeks of data, but the chart only renders the last 24 hours. Old data is "lost."

**Root cause:** the dashboard queries 5-minute resolution data over 2 weeks, but the TSDB only has 5-minute resolution for the last 7 days. Older data is 1-hour rollup. The query needs to be rewritten to use the right resolution.

**Fix:**
- Train users on the "downsample tiers": what's available at what age.
- Use the query service's automatic downsample selection (some implementations do this for you).
- Build dashboards that degrade gracefully: "no data" rather than "wrong data" when the requested range exceeds retention.

### 6. Hot shard (one TSDB instance overwhelmed)

**Symptom:** all queries against a particular TSDB shard are slow. Other shards are idle. The router isn't distributing load evenly.

**Root cause:** the shard key (usually a hash of the metric+labels) produces a skewed distribution, or a few "hot" series (a busy metric) concentrate on one shard.

**Fix:**
- Use **consistent hashing** with virtual nodes (vnodes) to spread load more evenly.
- For known hot series, **replicate** them across multiple shards.
- Profile: which series are most-read? Are they also write-hot? Consider splitting.

### 7. Schema drift between services

**Symptom:** a service emits `http_requests_count` while another emits `http_requests_total`. Aggregations miss one.

**Root cause:** no enforced metric naming standard; teams invent names ad hoc.

**Fix:**
- A **metric naming guide** (Prometheus best practices is a good starting point) reviewed and enforced.
- CI check: every new metric is registered in a catalog; PR review catches naming drift.
- Use OpenTelemetry semantic conventions where possible (they define standard names for common operations).

### 8. Histogram vs summary: which to use

**Symptom:** you want p99 latency; you use a `summary` (client-side quantile). The aggregation across instances is wrong because quantiles can't be averaged.

**Fix:** use a **histogram** (server-side bucket counts). The client emits counts per bucket; the TSDB stores the buckets; the query service computes the quantile across instances via `histogram_quantile()`. Histograms are aggregatable; summaries are not.

### 9. Retention policy silently expiring data

**Symptom:** "Why is the 6-month-old data gone?" — the user assumed infinite retention.

**Fix:** make retention explicit in the documentation and on dashboards (e.g., a "data available through" footer). For long-term archival, ship to S3 / data lake.

### 10. "We added a custom dashboard, now everything is slow"

**Symptom:** a dashboard with 50 panels each running a `rate()` over a 30-day range. The query service fans out 50 scatter-gather queries × 30 days of data.

**Fix:**
- **Caching** at the query service: cache the result of a query for, say, 30 s, so concurrent dashboard loads share the work.
- **Pre-aggregation** for known slow queries: materialize `rate(http_requests_total[5m])` into a derived series and dashboard against that.
- **Query timeouts and limits**: enforce a max evaluation time per query; cap the number of series returned.
- **Range limits**: don't allow 30-day queries against raw 10 s data; the query planner rewrites to 1-hour rollup.

---

## Deep Dive: Interview Q&A

### Q1. "Why not just use Postgres for this?"

**Answer sketch.** Metrics workloads are append-only, time-ordered, write-heavy, and queried by time range with aggregation. Postgres is a general-purpose RDBMS optimized for transactional workloads; it can do metrics, but at 1 M samples/sec it would saturate a row-store and the storage would be 10–50× larger without specialized compression (delta-of-delta, XOR). A TSDB exploits the regularity of the data — fixed-interval timestamps, slowly-changing float values — to compress 12–16× over a generic row store. A purpose-built TSDB also has time-aware query planners and retention policies built in. That said, TimescaleDB is a fair counter-example: a Postgres extension that adds TSDB-like partitioning and continuous aggregates; the right answer for a moderate scale.

### Q2. "Why pull, not push?"

**Answer sketch.** Pull gives the server control over scrape rate, free liveness checks (a failed scrape = a target down), and natural service discovery integration. Push is better for short-lived jobs (a serverless function can't wait to be scraped) and for cross-network-boundary cases. In practice, large systems use **both** — pull for long-running services, push for batch jobs, with a push gateway that bridges push-style jobs into a pull-based core.

### Q3. "How do you scale to 10x the fleet?"

**Answer sketch.** Shard the TSDB by series hash, replicate each shard 3×, add a query router that scatter-gathers. Move from local-disk storage to tiered storage (recent on local SSD, older on S3). Add a Kafka buffer between the collectors and the ingest workers so the TSDB can fail/restart without dropping data. Run more collectors, sharded by target. The alerting engine runs in HA, gossip-clustered, with deduplication. Cardinality discipline becomes critical — the first thing to break at 10x is usually the cardinality budget.

### Q4. "How do you handle high cardinality?"

**Answer sketch.** Don't allow it at the source. Enforce a label whitelist, set per-metric series budgets, and reject writes that exceed them. For legitimate high-cardinality data, use a different system (events, traces, logs — not metrics). For metrics, design label sets carefully: bounded cardinal dimensions (region, status code, host, container) and no unbounded ids.

### Q5. "How do you alert reliably? What if the alertmanager is down?"

**Answer sketch.** Run the alertmanager in HA — multiple instances, gossip-clustered, deduplication across replicas so the same alert isn't sent twice. Make sure the alerting path is in a different failure domain from the things it monitors (separate region, separate cloud account). Have an out-of-band escalation path (SMS via a separate provider) for when the primary notification channel is down. Test the failure mode: kill the alertmanager, ensure the redundant one picks up; kill both, ensure the fallback path (PagerDuty's own deduplication) takes over.

### Q6. "What's the difference between logs, metrics, and traces? When do you use which?"

**Answer sketch.**
- **Metrics**: numeric time series, low-cardinality, aggregatable. For "is the system healthy?" — CPU, latency, error rate, throughput.
- **Logs**: discrete events, high-cardinality, often text. For "what happened in this request?" — used for debugging, audit.
- **Traces**: causal spans across services. For "where did the time go in this request?" — distributed tracing.
- They are complementary, not interchangeable. A typical debugging flow: alert from a metric (error rate spike) → query the metric for the affected service/region → search logs for the failing requests → look at the trace for one of those requests.

### Q7. "What if I need 'real-time' alerts (sub-second)?"

**Answer sketch.** Move from query-based evaluation to **stream-based evaluation**. A Kafka consumer reads the metric stream and runs the rule against each event; an alert fires in <1 s of the underlying condition. The trade-off: rule expressiveness is limited (you can't do PromQL across a 5-minute window in a stream consumer) and the path is more complex. Use stream-based alerting sparingly — for security and fraud (where every second matters) — and keep query-based alerting as the default for most rules.

### Q8. "How do you test this?"

**Answer sketch.** Three layers: (a) **schema tests** — CI checks metric names, label keys, and unit conventions; reject drift. (b) **load tests** — synthetic 1 M samples/sec for 24 hours, watch for ingest lag, memory growth, query latency creep. (c) **drill tests** — simulate a target failure, verify the alert fires within the SLO; simulate an alertmanager failure, verify redundancy. (d) **chaos** — kill the TSDB primary, verify failover; partition a network region, verify alerts either fire or are explicitly silenced with a reason.

---

## Glossary

| Term | Definition | Common misconception |
|---|---|---|
| **Time series** | A sequence of `(timestamp, value)` data points indexed by a unique label set. | "Time series is a database table." It is a logical concept; the storage engine can be anything. |
| **Label** | A key-value tag that distinguishes series of the same metric name. | "Labels are free." Each unique label set is a separate series; cardinality is the cost. |
| **Cardinality** | The number of unique label combinations for a metric. | "Cardinality is bounded." It is whatever the labels allow; you must enforce it. |
| **Series / time series** | The unique (metric name + label set) identifying one stream. | "A metric is a series." A metric is the *name*; each label set is a series. |
| **Scrape** | A single pull of `/metrics` (or equivalent) from a target. | "Scrape is the same as sample." A scrape returns many samples. |
| **Histogram** | A set of bucket counters recorded per series; quantiles are computed at query time. | "Histograms give you percentiles directly." They give bucket counts; `histogram_quantile` is the function. |
| **Summary** | A pre-computed quantile, sent by the client. | "Summaries are aggregatable." They are not — quantiles can't be averaged. |
| **Gorilla compression** | Delta-of-delta (timestamps) + XOR (floats) — Facebook's 2015 TSDB. | "Gorilla is a specific database." It is a compression technique used by many TSDBs. |
| **Delta-of-delta** | Encoding a timestamp as the difference of the difference from a prior timestamp. | "Regular intervals compress to zero." They compress to a single "same" bit. |
| **XOR encoding** | Storing `value XOR previous_value`; consecutive similar values produce mostly-zero bytes. | "XOR is lossy." It is exact and reversible. |
| **Downsampling / rollup** | Pre-computing lower-resolution aggregates for older data. | "Downsampling is the same as averaging." It is windowed; per-window min/max/avg/count are all valid rollups. |
| **PromQL** | Prometheus's query language. | "PromQL is the standard." It is the most common but not the only one (InfluxQL, Flux, MQL exist). |
| **Alert state machine** | inactive → pending → firing; "for" duration between pending and firing. | "Pending = fired." Pending is a soft state; firing is when notifications go out. |
| **Inhibition** | An alert rule that suppresses another alert when both are active. | "Inhibition is just silence." Inhibition is rule-based and automatic; silence is manual. |
| **Silencing** | A manual rule that mutes alerts for a time window (e.g., during maintenance). | "Silencing is permanent." It is time-bounded. |
| **Dedup (in alerting)** | Merging multiple identical alerts into one notification. | "Dedup is the same as grouping." Dedup collapses identical alerts; grouping merges related-but-different ones. |
| **Pull / scrape vs push** | Server-driven fetch vs client-driven send. | "Push is always faster." Push is faster to set up; pull is easier to operate at scale. |
| **Push gateway** | A relay that accepts push metrics and serves them via pull to a pull-based system. | "Push gateway is just a buffer." It is a compatibility layer for short-lived jobs. |
| **Service discovery** | Mechanism for finding targets (K8s API, Consul, file_sd). | "SD is a separate system." It is integrated into the collector. |
| **Scatter-gather** | Query pattern where the router fans the query to multiple shards and merges results. | "Scatter-gather is free." It costs `max(shard_latency) + merge_time + RTT`. |
| **Tiered storage** | Hot data on local SSD, cold data on S3. | "Tiered storage is just archival." Hot path stays fast; cold path stays cheap. |
| **Federation** | A higher-tier collector that scrapes lower-tier collectors to produce a global view. | "Federation is the only way to scale Prometheus." It is one way; remote-write and Thanos are others. |
| **OpenTelemetry (OTel)** | Vendor-neutral SDK + protocol for emitting metrics, logs, traces. | "OTel is a TSDB." It is a client and protocol; storage is a separate choice. |
| **SLO (Service Level Objective)** | The reliability target the alerting system protects (e.g., 99.9% of requests < 200 ms). | "SLOs are the same as SLAs." SLOs are internal targets; SLAs are customer-facing contracts. |
| **Burn rate** | How fast an SLO's error budget is being consumed. | "Burn rate is the same as error rate." Burn rate is normalized to the SLO; 100× the budget in 1 hour is a burn rate of 100. |
| **Multi-window burn rate** | A common alerting pattern: alert when burn rate is high over a short window AND sustained over a long window. | "Single-window alerts are fine." They flap; multi-window is anti-flap by design. |
| **Recording rule** | A pre-computed query result stored as a new series, for fast dashboard access. | "Recording rules are just caches." They are first-class series, with retention and labels. |
