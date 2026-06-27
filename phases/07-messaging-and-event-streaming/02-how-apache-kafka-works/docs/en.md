# How Apache Kafka Works?

> Kafka is a distributed commit log that makes durable, ordered, replayable event streams the primitive — not the afterthought.

**Type:** Learn
**Prerequisites:** Introduction to Messaging Systems, Pub/Sub vs. Message Queues
**Time:** ~25 minutes

---

## The Problem

Imagine you run a ride-sharing platform. At peak hours, millions of GPS pings, payment events, driver-status changes, and search queries arrive every second. You have a dozen downstream consumers: the real-time map, the surge-pricing engine, the fraud detector, the analytics warehouse, and more. If you wire them point-to-point, every producer must know every consumer. Adding a new service means updating producers. A slow consumer blocks faster ones. A restart loses in-flight messages. The system becomes a tangled mesh.

Traditional message queues (RabbitMQ, ActiveMQ) partially solve this but carry a different problem: once a broker delivers a message and the consumer acknowledges it, the message is gone. If the analytics team wants to re-process the last 30 days of GPS events to retrain an ML model, they have nothing to replay. Queues model work items; you need a shared, durable log.

Kafka solves both: it decouples producers from consumers completely, retains messages for a configurable window (hours, days, or forever), and lets any number of independent consumer groups read the same stream at their own pace, from any point in time — without slowing each other down.

---

## The Concept

### Core Abstractions

| Abstraction | What it is |
|---|---|
| **Event / Record** | An immutable key-value pair plus metadata (timestamp, headers). The atom of Kafka. |
| **Topic** | A named, ordered, append-only log. Producers write to topics; consumers read from them. |
| **Partition** | A topic is split into N partitions. Each partition is an independent ordered log stored on one broker. |
| **Offset** | A 64-bit integer that uniquely identifies a record's position within a partition. Monotonically increasing, never reused. |
| **Broker** | A single Kafka server that stores partitions and serves clients. A cluster has 3–12+ brokers. |
| **Producer** | Application that appends records to a topic. |
| **Consumer Group** | A named set of consumers that collaboratively consume a topic. Each partition is owned by exactly one consumer in the group at any time. |
| **Replication** | Each partition has one leader and (replication factor − 1) followers. Followers copy from the leader. |

### The Append-Only Log

Kafka's central insight is treating the broker as a *commit log*, not a mailbox.

```
Partition 0 of topic "rides"
┌────────────────────────────────────────────────────────┐
│ offset 0 │ offset 1 │ offset 2 │ offset 3 │ offset 4  │
│ {"id":1} │ {"id":2} │ {"id":3} │ {"id":4} │ {"id":5}  │
└────────────────────────────────────────────────────────┘
                                              ▲ LEO (Log End Offset)
```

Records are never modified or deleted on demand. The log grows to the right. Retention is time-based or size-based (`log.retention.hours`, `log.retention.bytes`).

### How Partitions Enable Parallelism

A topic with one partition can only be read by one consumer in a group at a time. Split it into P partitions and you get up to P parallel readers — throughput scales linearly.

```
Topic "rides" (3 partitions, Consumer Group "surge-pricing")

 Producer A ──► Partition 0 ──► Consumer 1
 Producer B ──► Partition 1 ──► Consumer 2
 Producer C ──► Partition 2 ──► Consumer 3
```

If you add a fourth consumer to the group, it sits idle — there are only 3 partitions to own. More consumers than partitions means wasted resources.

### Partition Assignment and Ordering

Producers choose the partition by:
1. **Explicit key hashing** — `hash(key) % numPartitions`. All events with the same key (e.g., the same `driver_id`) land in the same partition, preserving per-key order.
2. **Round-robin** — used when no key is set; maximizes throughput but loses ordering across keys.
3. **Custom partitioner** — plug in your own logic.

**Global ordering across all partitions is not guaranteed.** If you need strict global order, use a single partition — but that caps your throughput to one consumer.

### Replication: Durability Under Failure

Every partition has a **leader** (handles all reads and writes) and zero or more **followers** (replicate the leader's log). The set of followers that are fully caught up is called the **In-Sync Replica set (ISR)**.

```
Partition 0 (replication factor = 3)

 Broker 1 [LEADER]  ──► Broker 2 [FOLLOWER, in ISR]
                    ──► Broker 3 [FOLLOWER, in ISR]
```

When a producer sends a message with `acks=all`, the leader waits for **all ISR members** to confirm before acknowledging. This guarantees no data loss even if the leader crashes immediately after ack.

`min.insync.replicas` (typically 2) sets the minimum ISR size that must acknowledge a write. If ISR shrinks below this threshold, writes are rejected rather than risking data loss.

### Cluster Coordination: ZooKeeper → KRaft

Historically, Kafka used Apache ZooKeeper to track broker membership, leader election, and topic metadata. Since Kafka 3.3, **KRaft mode** (Kafka Raft) replaces ZooKeeper: a small quorum of Kafka controllers stores cluster metadata directly in an internal Raft log. As of Kafka 4.0, ZooKeeper mode is fully removed.

### Consumer Offset Management

Consumers track their own progress. The current position is stored in a special internal Kafka topic: `__consumer_offsets`. This means:

- A consumer crash and restart resumes from the last committed offset, not the beginning.
- Multiple independent consumer groups each maintain their own offset — they don't interfere.
- You can reset a group's offset backward to replay history (`--reset-offsets --to-earliest`).

```
Consumer Group "analytics" reads Partition 0:

 [0][1][2][3][4][5][6][7]
        ▲               ▲
  committed             LEO
  offset=2        (next record to write)
```

The gap between committed offset and LEO is the **consumer lag**. High lag = consumer is falling behind.

---

## Build It / In Depth

### Step 1: Start a Single-Node Cluster (KRaft mode)

```bash
# Download Kafka 3.7+
tar -xzf kafka_2.13-3.7.0.tgz
cd kafka_2.13-3.7.0

# Generate a cluster UUID and format the log directory
KAFKA_CLUSTER_ID=$(bin/kafka-storage.sh random-uuid)
bin/kafka-storage.sh format -t $KAFKA_CLUSTER_ID -c config/kraft/server.properties

# Start the broker (it is also the controller in single-node mode)
bin/kafka-server-start.sh config/kraft/server.properties
```

### Step 2: Create a Topic with Partitions and Replication

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic rides \
  --partitions 3 \
  --replication-factor 1   # use 3 on a real multi-broker cluster

# Verify
bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic rides
```

Output shows partition leaders, replicas, and ISR:
```
Topic: rides  PartitionCount: 3  ReplicationFactor: 1
  Partition: 0  Leader: 1  Replicas: 1  Isr: 1
  Partition: 1  Leader: 1  Replicas: 1  Isr: 1
  Partition: 2  Leader: 1  Replicas: 1  Isr: 1
```

### Step 3: Produce Messages with the Python Client

```python
from kafka import KafkaProducer
import json

producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    key_serializer=str.encode,
    value_serializer=lambda v: json.dumps(v).encode(),
    acks="all",                  # wait for all ISR replicas
    retries=5,
    enable_idempotence=True,     # exactly-once at-producer level
)

# Key = driver_id ensures all events for driver-42 go to the same partition
producer.send("rides", key="driver-42", value={"lat": 37.7, "lng": -122.4, "status": "en_route"})
producer.flush()
```

### Step 4: Consume with a Consumer Group

```python
from kafka import KafkaConsumer
import json

consumer = KafkaConsumer(
    "rides",
    bootstrap_servers="localhost:9092",
    group_id="surge-pricing",
    key_deserializer=bytes.decode,
    value_deserializer=lambda m: json.loads(m.decode()),
    auto_offset_reset="earliest",   # read from beginning if no committed offset
    enable_auto_commit=False,        # manual commit for at-least-once control
)

for msg in consumer:
    process(msg.value)
    consumer.commit()                # commit after successful processing
```

### Step 5: Check Consumer Lag

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group surge-pricing \
  --describe
```

```
GROUP          TOPIC  PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
surge-pricing  rides  0          1402            1410            8
surge-pricing  rides  1          893             893             0
surge-pricing  rides  2          2101            2110            9
```

A LAG of 0 means the consumer is fully caught up on that partition.

---

## Use It

### Where Kafka Appears in Production

| Use Case | How Kafka is Used |
|---|---|
| **Change Data Capture (CDC)** | Debezium reads the DB write-ahead log and publishes row changes to Kafka topics. Downstream services react without polling the DB. |
| **Stream Processing** | Kafka Streams or Apache Flink reads from Kafka, applies windowed aggregations, and writes results back to Kafka. |
| **Event Sourcing** | Kafka is the system of record. Services rebuild state by replaying the topic from offset 0. |
| **Log Aggregation** | Fluentd / Logstash ship application logs to Kafka; Elasticsearch or S3 consumes them. |
| **Metrics Pipeline** | Prometheus remote-write or OpenTelemetry exporters push metrics to Kafka; a downstream aggregator computes rollups. |
| **ML Feature Pipelines** | Feature engineering jobs consume raw events, compute features, and publish to a feature store. |

### Kafka vs. Alternatives

| | Kafka | RabbitMQ | AWS Kinesis | Pulsar |
|---|---|---|---|---|
| Retention | Days–forever | Until ack'd | 1–365 days | Days–forever |
| Replay | Yes | No | Yes (limited) | Yes |
| Ordering | Per-partition | Per-queue | Per-shard | Per-partition |
| Throughput | Very high | Moderate | High | Very high |
| Complexity | High (ops burden) | Low | Managed | High |
| Best for | High-volume streaming | Task queues, RPC | AWS-native streaming | Multi-tenancy |

Choose Kafka when you need durable, replayable, high-throughput event streams and can absorb the operational complexity (or use Confluent Cloud / MSK to offload it).

---

## Common Pitfalls

- **Too few partitions at creation.** Partitions are the unit of parallelism. You cannot reduce partition count after creation without recreating the topic. Start with at least 3× your expected peak consumer count, and add headroom.

- **`acks=0` or `acks=1` on critical data.** `acks=1` only waits for the leader to write; if the leader crashes before followers replicate, data is lost. Use `acks=all` + `min.insync.replicas=2` for durability that survives a broker failure.

- **Auto-commit hiding message loss.** The default `enable.auto.commit=True` commits the offset on a timer, *not* after your processing logic succeeds. If your consumer crashes between the auto-commit and finishing processing, messages are silently skipped. Disable auto-commit and commit manually after successful processing.

- **Rebalance storms from slow consumers.** Kafka's consumer group coordinator removes a consumer if it misses a heartbeat within `session.timeout.ms`. A slow processing loop causes heartbeat misses, triggering constant rebalances that halt the whole group. Use `max.poll.interval.ms` to bound processing time per poll, and separate your processing thread from the polling loop if needed.

- **Treating Kafka as a database.** Kafka is optimized for sequential reads from the tail. Random access by key or filtering by field is expensive (you'd scan all records). For point lookups, write results to a real store (Redis, PostgreSQL) from a stream processor — don't query Kafka directly.

---

## Exercises

1. **Easy** — Create a topic called `temperatures` with 2 partitions. Produce 10 messages with keys `sensor-A` and `sensor-B` alternating. Use `kafka-console-consumer.sh` to confirm that all `sensor-A` messages land in the same partition (check with `--property print.partition=true`).

2. **Medium** — Write a Python consumer group with two consumers reading the `temperatures` topic. Kill one consumer mid-run and observe which partitions are reassigned to the surviving consumer. Then add the consumer back and confirm the group rebalances again. Record the offsets before and after to verify no messages are replayed or skipped.

3. **Hard** — Design a CDC pipeline: use Debezium to capture `INSERT`/`UPDATE` events from a PostgreSQL table into a Kafka topic. Write a Kafka Streams (or Flink) job that counts the number of updates per primary-key value in a 1-minute tumbling window and outputs the result to a second topic. Deploy on a 3-broker cluster with replication factor 3 and `min.insync.replicas=2`, then deliberately kill one broker mid-stream to verify zero data loss and uninterrupted processing.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Topic** | Like a database table | An append-only, distributed, ordered log — immutable records, no deletes |
| **Partition** | Just a shard of the topic | The actual unit of ordering, parallelism, and storage; leader elections happen at partition level |
| **Offset** | A message ID you can look up | A monotonically increasing integer position within one partition; meaningless across partitions |
| **Consumer Group** | A pool of workers sharing a queue | Independent groups each get a *full copy* of the stream; within one group, partitions are divided |
| **Replication Factor** | Backup copies | The total number of replicas including the leader; RF=3 means 1 leader + 2 followers |
| **ISR** | All replicas | Only the replicas that are *caught up* to the leader; writes with `acks=all` must be confirmed by all ISR members |
| **Lag** | Backlog waiting to be sent | Difference between LEO and committed consumer offset — measures how far behind a consumer is |

---

## Further Reading

- [Apache Kafka Documentation — Core Concepts](https://kafka.apache.org/documentation/#gettingStarted) — the official reference for all broker configs, APIs, and design rationale.
- [Kafka: The Definitive Guide (O'Reilly, 2nd ed.)](https://www.oreilly.com/library/view/kafka-the-definitive/9781492043072/) — the canonical deep-dive book; chapters 3–6 cover internals exhaustively.
- [Confluent Developer: Kafka Fundamentals](https://developer.confluent.io/learn-kafka/) — free self-paced courses with interactive exercises from the Kafka creators.
- [Jay Kreps — "The Log: What every software engineer should know about real-time data's unifying abstraction"](https://engineering.linkedin.com/distributed-systems/log-what-every-software-engineer-should-know-about-real-time-datas-unifying) — the seminal essay that explains *why* an append-only log is such a powerful primitive.
- [Kafka Improvement Proposals (KIPs) index](https://cwiki.apache.org/confluence/display/KAFKA/Kafka+Improvement+Proposals) — read KIP-500 (KRaft) and KIP-679 (idempotent producer by default) to understand the trajectory of the platform.
