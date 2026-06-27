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

## Step 3 — Deep Dive

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
