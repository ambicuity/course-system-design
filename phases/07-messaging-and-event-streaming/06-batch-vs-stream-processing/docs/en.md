# Batch vs Stream Processing

> How you move data through a system is just as important as the data itself — choose wrong and you'll be a day late or a millisecond too slow.

**Type:** Learn
**Prerequisites:** Message Queues, Event-Driven Architecture, Kafka Fundamentals
**Time:** ~35 minutes

---

## The Problem

Imagine you run an e-commerce platform. Every order, click, and cart abandonment produces data. Your analytics team wants a daily revenue report — that's fine, it can wait until 2 AM. But your fraud detection system needs to flag a stolen card within 200 milliseconds of a purchase, before the package ships. Your recommendation engine should update the "customers also bought" panel before the user finishes scrolling. These three use cases need fundamentally different answers to the same question: *when do we process the data?*

Batch processing dominated the data world for decades because it was the only practical option — you collected records, loaded them into a file or database, then ran a job overnight. MapReduce, Hadoop, and SQL warehouses are built around this model. But as applications demanded immediate feedback, a second model emerged: stream processing, where each event is handled the moment it arrives, one record at a time.

The confusion arises because both models can answer questions about the same data. You could compute "average order value last 30 days" with a nightly batch job or a continuously updating streaming aggregate. The difference is not whether you *can* do it — it is what trade-offs you accept in latency, throughput, cost, fault tolerance, and operational complexity. Getting this choice wrong costs teams months of rework. Getting it right lets you build systems that feel alive.

---

## The Concept

### The Core Distinction

| Dimension | Batch Processing | Stream Processing |
|---|---|---|
| **When data is processed** | After it accumulates (minutes → days) | As it arrives (milliseconds → seconds) |
| **Data model** | Bounded dataset (finite, known size) | Unbounded dataset (infinite, ongoing) |
| **Latency** | High (scheduled intervals) | Low (near-real-time) |
| **Throughput** | Very high — optimized for bulk I/O | Moderate — optimized for latency |
| **Result freshness** | Stale by design | Current by design |
| **Fault tolerance** | Re-run the entire job | Replay from offset / checkpoint |
| **Complexity** | Lower — simpler mental model | Higher — windowing, state, ordering |
| **Cost profile** | Efficient per-record cost, bursty compute | Continuous compute, always-on cost |

### Batch Processing: How It Works

A batch job reads a finite set of data, applies transformations, and writes output. The lifecycle looks like this:

```
  [Data Source]
       │
       ▼
  [Ingest / Stage]      ← e.g., files land in S3 every hour
       │
       ▼
  [Batch Job Runs]      ← triggered by cron, Airflow, or event
       │  read all records since last run
       │  apply transformations (filter, join, aggregate)
       │
       ▼
  [Write Output]        ← data warehouse, report, updated table
       │
       ▼
  [Consumers read it]   ← dashboards, BI tools, downstream jobs
```

Key properties:
- **Idempotency matters.** Jobs should be safe to re-run. Write to a staging table first, then atomically swap.
- **Parallelism is embarrassingly easy.** Split the input by key range or partition, run workers in parallel, merge results.
- **Windowing is implicit.** The "window" is simply the time range of data ingested for this run.

### Stream Processing: How It Works

A stream processor subscribes to an unbounded log of events and applies operations continuously. State can be maintained across events:

```
  [Event Producers]
       │  order placed, click, sensor reading
       ▼
  [Message Broker]      ← Kafka topic, Kinesis stream
       │  partitioned, ordered within partition
       ▼
  [Stream Processor]
       │  reads events one-by-one (or micro-batch)
       │  maintains local state (counts, sums, joins)
       │  emits results downstream
       ▼
  [Sink / Output]       ← database, another topic, REST webhook
```

Key properties:
- **Windowing is explicit.** You must define *tumbling* (non-overlapping fixed-size), *sliding* (overlapping), or *session* (gap-based) windows. This is where most complexity lives.
- **Out-of-order events are the norm.** Network delays mean event timestamps and arrival times diverge. Processors use *watermarks* to decide when a window is "done enough" to emit.
- **State management is the hard part.** Counts, joins, and aggregates require durable, queryable state — usually a local RocksDB instance or in-memory store backed by a changelog topic.

### Windowing in Stream Processing

```
Tumbling Window (size = 5 min, no overlap):
│──── 00:00–00:05 ────│──── 00:05–00:10 ────│

Sliding Window (size = 5 min, slide = 2 min):
│── 00:00–00:05 ──│
        │── 00:02–00:05+00:02 ──│
                │── 00:04–00:09 ──│

Session Window (gap = 2 min):
│── activity ──│  [2 min gap]  │── activity ──│
     Session 1                     Session 2
```

Tumbling windows are simplest and cheapest — most aggregation use cases fit here. Sliding windows give smoother metrics (like a rolling 5-minute average) but require keeping more state. Session windows model user behavior where activity has natural pauses.

### The Lambda and Kappa Architectures

Two architectural patterns emerged to reconcile batch accuracy with stream speed:

**Lambda Architecture** runs both a batch layer (for corrected, complete results) and a speed layer (for low-latency approximations), merging their outputs at query time. The problem: you maintain two codebases doing the same thing.

**Kappa Architecture** eliminates the batch layer entirely — everything goes through a replayable stream. When you need to recompute, replay from offset 0 in Kafka. This works because a fast-enough stream over historical data *is* batch processing. Most modern architectures prefer Kappa for its operational simplicity.

---

## Build It / In Depth

### Step 1 — Batch Job: Daily Revenue Report

A typical PySpark batch job reading from S3, aggregating, and writing to a warehouse:

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum as spark_sum, to_date

spark = SparkSession.builder.appName("DailyRevenue").getOrCreate()

# Read a bounded dataset: yesterday's orders
orders = spark.read.parquet("s3://data-lake/orders/date=2026-06-25/")

# Transform: filter completed orders, aggregate by merchant
revenue = (
    orders
    .filter(col("status") == "COMPLETED")
    .groupBy("merchant_id")
    .agg(spark_sum("amount_usd").alias("daily_revenue"))
)

# Write to warehouse (idempotent overwrite)
revenue.write.mode("overwrite").parquet("s3://warehouse/daily_revenue/date=2026-06-25/")
spark.stop()
```

This job runs once per day. It processes the entire day's orders in parallel across workers. If it fails halfway through, re-run it safely — the output partition is overwritten.

### Step 2 — Stream Job: Real-Time Fraud Scoring

A Flink-style streaming job (using Python's `kafka-python` for illustration):

```python
from confluent_kafka import Consumer, Producer
import json, time

consumer = Consumer({
    "bootstrap.servers": "kafka:9092",
    "group.id": "fraud-detector",
    "auto.offset.reset": "latest",
})
producer = Producer({"bootstrap.servers": "kafka:9092"})

consumer.subscribe(["transactions"])

# Maintain a 5-minute sliding window of card velocity
velocity: dict[str, list[float]] = {}

WINDOW_SECONDS = 300
THRESHOLD_COUNT = 10

while True:
    msg = consumer.poll(timeout=0.1)
    if msg is None:
        continue

    txn = json.loads(msg.value())
    card = txn["card_id"]
    now = time.time()

    # Evict events outside the window
    velocity[card] = [t for t in velocity.get(card, []) if now - t < WINDOW_SECONDS]
    velocity[card].append(now)

    if len(velocity[card]) > THRESHOLD_COUNT:
        alert = {"card_id": card, "reason": "velocity_breach", "count": len(velocity[card])}
        producer.produce("fraud-alerts", json.dumps(alert).encode())
        producer.flush()
```

This processor handles each event in microseconds. It maintains window state in memory (in production: backed by a changelog Kafka topic or RocksDB for fault tolerance). A breach alert reaches the fraud team within milliseconds of the triggering transaction.

### Step 3 — Decision Procedure

When you receive a new data processing requirement, ask these four questions in order:

```
1. What is the acceptable result latency?
   ├── Hours/days   → Batch
   └── Seconds      → Stream

2. Is the input dataset bounded (finite) or unbounded (continuous)?
   ├── Bounded      → Batch
   └── Unbounded    → Stream (or micro-batch if latency allows)

3. Does correctness require complete data (e.g., "top 100 of all time")?
   ├── Yes          → Batch (or Lambda with batch layer for corrections)
   └── No           → Stream (approximate / windowed is acceptable)

4. Can you afford always-on compute?
   ├── No           → Batch (burst compute, pay per job)
   └── Yes          → Stream
```

---

## Use It

### Real Systems and Where They Land

| Technology | Model | Typical Use Case |
|---|---|---|
| Apache Spark (batch mode) | Batch | ETL pipelines, ML feature engineering, large-scale SQL |
| Apache Hadoop / MapReduce | Batch | Petabyte-scale historical processing |
| dbt (on a warehouse) | Batch | SQL transformations, data modeling |
| Apache Flink | Stream (+ batch) | Real-time analytics, CEP, stateful event processing |
| Apache Kafka Streams | Stream | Lightweight stream processing colocated with Kafka |
| Apache Spark Structured Streaming | Micro-batch / Stream | Unified API when team already uses Spark |
| AWS Kinesis Data Analytics | Stream | Managed Flink on AWS |
| Google Dataflow | Stream + Batch | Apache Beam runner, unified model |
| Apache Airflow | Batch orchestration | Scheduling and dependency management for batch jobs |
| Materialize / ksqlDB | Stream | Streaming SQL for operational analytics |

### Micro-Batch: The Middle Ground

Spark Structured Streaming and older Spark Streaming use *micro-batching*: events are buffered for a short interval (100ms–5s) and then processed as a mini-batch. This simplifies state management and achieves latencies in the low seconds — acceptable for most "near real-time" use cases without the operational complexity of true event-at-a-time processing.

Use micro-batch when:
- Latency requirements are in the 1–30 second range
- Your team already knows Spark
- You want one codebase for both historical backfills and ongoing processing

Use true stream processing (Flink, Kafka Streams) when:
- Sub-second latency is required
- You need complex event processing (CEP) or pattern detection across events
- You need fine-grained per-event state management

---

## Common Pitfalls

- **Assuming batch is always cheaper.** Batch jobs spin up large clusters for a short burst. If your data volume is small but frequency is high (hourly mini-batches), streaming with a lightweight processor is often cheaper and simpler. Profile cost per record, not just compute hours.

- **Ignoring late data in streams.** Events arrive out of order — a mobile app event from a user with a spotty connection may arrive 10 minutes after it was generated. Without watermarks and a grace period, your streaming aggregates silently drop late events and produce wrong results. Always configure watermark lag based on your observed p99 event delay.

- **Building a Lambda architecture you don't need.** Teams add a batch layer "for correctness" before proving the stream layer is actually wrong. Start with Kappa. Add a batch layer only when you have a measured, material accuracy gap and a business requirement that justifies the operational cost.

- **Treating stream checkpoints as a backup strategy.** Checkpoints let a stream processor recover where it left off after a crash. They are not a substitute for testing your consumer group offsets, your changelog topic retention, or your sink idempotency. A checkpoint without a tested recovery procedure is false confidence.

- **Running batch jobs that overlap their schedule.** A nightly job that takes 25 hours will overlap the next run. Build your pipeline with explicit completion gates (Airflow sensors, step-function states) and monitor job duration against its schedule. Alert before it drifts past the threshold, not after it breaks.

---

## Exercises

1. **Easy — Latency Classification:** For each use case below, decide whether batch or stream processing is appropriate and explain why: (a) generating a monthly invoice PDF for every customer, (b) detecting when a server's CPU exceeds 90% for 3 consecutive minutes, (c) computing the all-time top 1000 most-played songs on a music platform.

2. **Medium — Window Design:** You are building a stream processor that tracks the number of failed login attempts per user. A user should be locked out if they fail 5 times within any rolling 10-minute window. Sketch the data flow: what event fields do you need, which window type do you choose, how do you handle late events, and where does the lockout action get emitted?

3. **Hard — Kappa Recompute:** Your team runs a Kappa architecture with Kafka retaining 30 days of raw events. A bug in your stream processor produced incorrect user lifetime-value (LTV) figures for the past 14 days. Design a full recovery procedure: how do you replay, avoid double-writing to your sink, coordinate consumer groups, and validate the recomputed results against the corrupted ones — without taking the production system offline.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Batch processing** | Just running a cron job on a CSV | A paradigm where a bounded, finite dataset is read, transformed, and written as a single logical unit of work — regardless of trigger mechanism |
| **Stream processing** | Reading from Kafka | Continuously applying operations to an unbounded sequence of events, maintaining state across records, with explicit handling of time and order |
| **Watermark** | A timestamp on an event | A processor-side signal declaring "I don't expect to see any events earlier than time T" — used to close windows and emit results without waiting forever |
| **Tumbling window** | Any time-based grouping | A non-overlapping, fixed-size time interval; each event belongs to exactly one window |
| **Micro-batch** | Real stream processing | Buffering events for a short interval (ms–seconds) then processing them as a mini-batch; a pragmatic middle ground with higher latency than true streaming |
| **Lambda architecture** | A best-practice pattern | A design that runs batch and speed layers in parallel and merges their outputs — accepted as a trade-off, not an ideal |
| **Checkpoint** | A full data backup | A snapshot of a stream processor's in-flight state (offsets + operator state) that allows recovery from the last consistent point after a failure |

---

## Further Reading

- [Apache Flink — Stateful Stream Processing Concepts](https://nightlies.apache.org/flink/flink-docs-stable/docs/concepts/stateful-stream-processing/) — authoritative reference on state, time, and watermarks
- [Martin Kleppmann, *Designing Data-Intensive Applications*, Chapter 11: Stream Processing](https://dataintensive.net/) — the most thorough treatment of stream vs. batch trade-offs available in book form
- [Apache Beam Programming Guide](https://beam.apache.org/documentation/programming-guide/) — unified model that expresses both batch and stream pipelines, useful for understanding the underlying abstractions
- [Databricks Blog — Structured Streaming Design](https://www.databricks.com/blog/2016/07/28/structured-streaming-in-apache-spark.html) — explains the micro-batch execution model and its trade-offs versus continuous processing
- [Jay Kreps — "Questioning the Lambda Architecture"](https://www.oreilly.com/radar/questioning-the-lambda-architecture/) — the essay that introduced the Kappa architecture and the argument for a single replayable stream
