# Design a Distributed Message Queue

A distributed message queue decouples producers (services that emit messages) from consumers (services that process them). It buffers data, absorbs bursts, enables asynchronous processing, and lets independent services scale separately. This chapter designs a durable, high-throughput, partitioned, replicated queue/log — conceptually like **Apache Kafka** (and similar to Pulsar/Kinesis/RabbitMQ for some features).

---

## Step 1 — Understand the Problem and Establish Scope

### Two flavors of "message queue"

It's worth disambiguating up front, because the right design differs:

- **Traditional message queue** (RabbitMQ, ActiveMQ, SQS): messages are typically deleted once consumed; routing/priority/per-message ack are first-class; ordering is best-effort.
- **Distributed event log / streaming platform** (Kafka, Pulsar): messages are an **append-only, ordered, replayable log**, retained for a window even after consumption; consumers track their own offsets. This is what most modern "design a message queue" interviews want, and what we design here.

### Functional requirements

1. **Produce**: producers send messages to a named **topic**.
2. **Consume**: consumers read messages from a topic.
3. **Durability**: messages persist on disk and survive broker restarts/crashes.
4. **Retention**: messages are retained for a configurable period (or size), independent of whether they've been consumed.
5. **Ordering**: messages within a partition are delivered in the order they were produced.
6. **Scalability**: throughput scales horizontally by adding partitions/brokers.
7. **Consumer groups**: multiple consumers cooperate to consume a topic in parallel; messages are load-balanced across the group.
8. **Replay**: a consumer can rewind to an earlier offset and reprocess.

### Non-functional requirements

- **High throughput** (millions of messages/sec) **and/or low latency** — these can be tuned per workload.
- **Durability & availability**: no acknowledged message is lost; tolerate broker failures.
- **Horizontal scalability**.
- **At-least-once delivery** as the default guarantee, with paths toward exactly-once.

### Back-of-the-envelope

- Target: **1 M messages/sec**, average **1 KB** each → **~1 GB/s** write throughput.
- Retention: **7 days** → `1 GB/s × 86400 s × 7 ≈ 600 TB` raw, before replication. With **replication factor 3**, ~1.8 PB. → must shard across many brokers; sequential disk I/O and batching are essential.
- A single modern disk does sequential writes at hundreds of MB/s, so even one topic at 1 GB/s needs spreading across several partitions/brokers.

---

## Step 2 — High-Level Design

### Core concepts

```
Producers ──▶  ┌──────────── Topic: "orders" ────────────┐
               │  Partition 0:  [m0 m1 m2 m3 ... ] ──┐    │
               │  Partition 1:  [m0 m1 m2 ...     ] ──┤    │ ──▶ Consumer Group A (parallel consumers)
               │  Partition 2:  [m0 m1 ...        ] ──┘    │ ──▶ Consumer Group B (independent offsets)
               └──────────────────────────────────────────┘
               Partitions live on Brokers; each partition replicated to N brokers.
```

- **Topic**: a named logical stream of messages.
- **Partition**: a topic is split into partitions. **A partition is the unit of ordering, parallelism, and replication.** Each partition is an ordered, append-only log; each message gets a monotonically increasing **offset**.
- **Broker**: a server that hosts partitions (their leaders and/or replicas). A cluster has many brokers.
- **Producer**: chooses a partition (by key hash, round-robin, or explicit) and appends.
- **Consumer**: reads from partitions, tracking an **offset** (its position).
- **Consumer group**: a set of consumers that split a topic's partitions among themselves so each partition is consumed by exactly one member of the group. Different groups consume independently.
- **Offset**: per-consumer-group position in each partition; committed/stored so a restarted consumer resumes where it left off.
- **Coordination service**: metadata (topics, partitions, leaders, ISR, group membership) is managed by a coordination layer — historically **ZooKeeper**, now **KRaft** (Raft-based) in Kafka.

### Why partitions are the key abstraction

- **Parallelism**: more partitions → more consumers in a group can work concurrently. Max useful consumers per group = number of partitions.
- **Ordering**: order is only guaranteed *within* a partition. Cross-partition global order is not provided (it would serialize everything). To keep related messages ordered, **route them to the same partition** via a partition key (e.g., `userId`) — all of one user's events land in one partition, ordered.
- **Scaling unit**: partitions distribute load across brokers.

### API design

```
# Produce
produce(topic, key?, value, headers?) -> { partition, offset }     // ack per acks setting

# Consume (pull-based)
subscribe(topic, groupId)
poll(maxMessages, timeout) -> [ {partition, offset, key, value, timestamp} ]
commitOffset(topic, partition, offset)                              // mark progress
seek(topic, partition, offset)                                      // replay / skip

# Admin
createTopic(name, numPartitions, replicationFactor, retention)
```

### Storage model: the append-only commit log

Each partition is stored as an **append-only log file** on disk, broken into **segments** (e.g., 1 GB each). Key properties that make this fast:

- **Sequential writes**: appending is sequential disk I/O — far faster than random writes, and friendly to OS page cache.
- **Zero-copy reads**: serving consumers can use `sendfile` to copy from page cache straight to socket, skipping userspace.
- **Index per segment**: a sparse `offset → byte position` index enables fast seeks.
- **Immutable messages**: messages are never updated in place; this simplifies replication and caching.
- **Retention by time/size**: old segments are deleted (or compacted) once past the retention window — consumption does not delete messages.

---

## Step 3 — Deep Dive

### 3.1 Replication and in-sync replicas (ISR)

To survive broker failure, each partition is replicated to **N brokers** (replication factor). One replica is the **leader**; the others are **followers**.

- **Leader handles all reads/writes** for the partition; followers pull from the leader to stay current.
- **In-Sync Replicas (ISR)**: the set of replicas (including the leader) that are fully caught up. A follower that falls behind is removed from the ISR until it catches up.
- **Commit semantics**: a message is considered **committed** once it's been written to all replicas in the ISR. Consumers only ever see committed messages (the **high-watermark**).
- **Producer `acks` setting** trades durability vs latency:

| `acks` | Behavior | Guarantee |
|---|---|---|
| `0` | Producer doesn't wait | Fire-and-forget; may lose messages |
| `1` | Leader has written | Lost if leader dies before followers replicate |
| `all` (`-1`) | All ISR have written | Strongest; no loss as long as one ISR survives |

- **`min.insync.replicas`**: with `acks=all`, also require at least M replicas in the ISR or the write fails — prevents accepting writes that aren't sufficiently replicated.
- **Leader election**: if a leader dies, the coordination layer elects a new leader **from the ISR** (so no committed data is lost). Electing a non-ISR replica (unclean election) would trade durability for availability — usually disabled.

### 3.2 Delivery semantics

This is the most-asked tradeoff. There are three levels:

- **At-most-once**: deliver, then process; if it fails, don't retry. No duplicates, but messages can be lost. (Commit offset *before* processing.)
- **At-least-once** (the practical default): process, then commit offset; if a consumer crashes after processing but before committing, the message is redelivered → **possible duplicates**, no loss. Achieved by committing offsets *after* successful processing and producers retrying on uncertain acks.
- **Exactly-once**: each message effects the system exactly once. Hard in a distributed system. Two production approaches:
  1. **Idempotent consumers**: make processing idempotent (dedupe on a message id / use upserts), so duplicates are harmless. This is the pragmatic answer for most systems.
  2. **Transactional / idempotent producers + atomic offset commit**: the broker dedupes producer retries (sequence numbers per producer), and consume-process-produce is wrapped in a transaction so output writes and offset commits are atomic. Kafka offers this within Kafka; end-to-end EOS to external systems still needs idempotency or 2PC-like coordination.

**Interview framing**: default to at-least-once + idempotent consumers; reach for transactional exactly-once only when duplicates are genuinely unacceptable, and note its throughput cost.

### 3.3 Push vs pull

How do consumers get messages?

| | Push (broker → consumer) | Pull (consumer → broker) |
|---|---|---|
| Flow control | Broker must track consumer rate; risk of overwhelming slow consumers | Consumer fetches at its own pace — natural backpressure |
| Batching | Harder | Consumer requests batches efficiently |
| Latency when idle | Low (broker pushes immediately) | Can poll-wait; **long-polling** removes busy-waiting |
| Catch-up / replay | Awkward | Trivial — consumer just requests older offsets |

**Kafka uses pull (with long-polling).** Pull gives consumers control over rate and batching, makes replay natural, and avoids the broker having to model each consumer's capacity. The downside — latency when the queue is empty — is solved with **long-poll** (the fetch blocks server-side until data arrives or a timeout).

### 3.4 Consumer groups and rebalancing

- Within a group, **each partition is assigned to exactly one consumer**. Add consumers to scale out (up to the partition count); idle consumers beyond that count sit unused.
- A **group coordinator** (a broker) tracks membership via heartbeats. When a consumer joins/leaves/dies, a **rebalance** reassigns partitions across the surviving members.
- **Rebalance cost**: a stop-the-world rebalance pauses consumption; modern designs use **cooperative/incremental rebalancing** and **static membership** to minimize disruption.
- **Offset storage**: committed offsets are stored durably (in Kafka, in an internal `__consumer_offsets` topic) so a restarted/reassigned consumer resumes correctly.

### 3.5 Message ordering in practice

- Guaranteed **only within a partition**. To preserve order for an entity, pick a **partition key** (`userId`, `orderId`) so all its messages hash to the same partition.
- With at-least-once + producer retries, a naive retry can reorder messages within a partition. **Idempotent producers** (per-producer sequence numbers) let the broker maintain order and dedupe even across retries (Kafka caps in-flight requests / uses sequence numbers to preserve order).
- **Hot partitions**: a skewed key (one whale user) overloads one partition. Mitigate with a better key, composite keys, or splitting that key's traffic when strict ordering isn't required.

### 3.6 Retention, compaction, and replay

- **Time/size retention**: keep messages for, e.g., 7 days; delete old segments regardless of consumption. This is what makes **replay** and **multiple independent consumer groups** possible — the data is still there.
- **Log compaction** (alternative retention): keep only the **latest value per key**, discarding older updates. Turns the log into a changelog / materialized latest-state stream (great for CDC, config topics, and rebuilding state).
- **Replay**: because messages aren't deleted on consume, a consumer can `seek` to an old offset (or a timestamp) and reprocess — invaluable for backfills, new consumers, and recovering from bad deploys.

### 3.7 Coordination and metadata

- The cluster needs consensus on: which broker leads each partition, ISR membership, topic configs, and consumer-group assignments. A **consensus layer** (ZooKeeper historically; **KRaft**, a Raft-based controller quorum, in modern Kafka) owns this.
- Producers/consumers fetch **metadata** (partition → leader broker mapping) and talk directly to the leader broker, refreshing metadata on leadership changes.

---

## Step 4 — Wrap Up

### How the pieces deliver the requirements

- **High throughput**: append-only sequential disk writes, batching, compression, zero-copy reads, and partition-level parallelism.
- **Durability**: persist to disk + replicate to ISR; `acks=all` + `min.insync.replicas` guarantees no committed-message loss.
- **Scalability**: add partitions and brokers; consumer groups scale read throughput up to partition count.
- **Ordering**: per-partition ordering + partition keys for entity-level order.
- **Delivery guarantees**: at-least-once by default, exactly-once via idempotency/transactions.
- **Replay & multi-consumer**: retention keeps messages after consumption; offsets are per-group.

### Bottlenecks and mitigations

| Bottleneck | Mitigation |
|---|---|
| Single partition throughput ceiling | More partitions; spread across brokers |
| Hot partition (key skew) | Better partition key; composite/sharded keys |
| Rebalance storms | Cooperative/incremental rebalancing, static membership |
| Slow consumer lags | Scale out group, increase partitions, monitor consumer lag |
| Broker failure | Replication + ISR leader election |
| Coordination layer as SPOF | Raft quorum (KRaft) / replicated ZooKeeper ensemble |

### Talking points to close

- **Partitions are the central design lever** — they couple ordering, parallelism, and replication. Choosing partition count and keys well is most of the design.
- **Durability vs latency is a dial** (`acks`, `min.insync.replicas`) — name it explicitly.
- **Pull + long-poll + retained log** is what distinguishes a streaming log from a classic broker, and is what enables replay and multiple consumer groups.
- **Exactly-once is expensive**; prefer idempotent consumers unless duplicates are truly unacceptable.

---

## Deep Dive: Back-of-the-Envelope Math

Working in powers of 2 and realistic numbers from production-style loads.

### Workload assumptions

| Constant | Value | Notes |
|---|---|---|
| Target throughput | 1 M messages/sec | steady-state; bursts 2–3 M |
| Average message size | 1 KB | payload + headers + metadata |
| Replication factor | 3 | RF=3 for durability |
| Retention | 7 days | standard; some topics 30+ days |
| Partitions per topic | 100–1,000 | depends on parallelism need |
| Brokers per cluster | 50–200 | large production |
| Brokers per partition | 1 leader + 2 followers (RF=3) | |
| Disk per broker (NVMe) | 10 TB usable | with 30% headroom for compaction |
| Network per broker | 10 Gbps | inter-broker replication + client |
| Page cache per broker | 64–256 GB | RAM |

### Throughput

- Steady-state write bandwidth (before replication): `1 M/s × 1 KB = 1 GB/s` raw
- With RF=3: each write is replicated to 2 followers → aggregate write bandwidth on the cluster is `1 GB/s × 3 = 3 GB/s`. Spread across, say, 50 brokers → `60 MB/s` per broker. Comfortable.
- Read bandwidth: consumers re-read from disk on cache miss; hot partitions in the page cache; total sustained read often equals or exceeds write at high consumer concurrency.

### Storage

- 7-day retention raw: `1 GB/s × 86,400 s × 7 = 604,800 GB ≈ 605 TB`
- With RF=3: `~1.8 PB`
- Per broker: `1.8 PB / 50 brokers = 36 TB` raw. With compression (~3× ratio typical for JSON/log payloads) → `~12 TB` per broker. Fits in 10 TB usable if retention is reduced or more brokers are added.

### Latency

- Append (in-sync ack from all replicas): typical 5–10 ms p50, 20–50 ms p99. Bottleneck is the slowest follower.
- End-to-end produce → consume (1 broker hop, 1 consumer group, no fan-out): 10–100 ms p50.
- Fan-out across many consumer groups: 10–50 ms p50; scales with consumer group count.

### Producer scaling

- A single producer can sustain 10k–100k msg/s with batching (linger.ms, batch.size tuned).
- For 1 M msg/s, you need ~10–100 producer processes.
- Producer batching (32 KB batches, 5 ms linger) is essential to reach the throughput.

### Consumer scaling

- Max useful consumers in a group = number of partitions. 100 partitions = 100 consumers in the group.
- A single consumer can process 5k–20k msg/s depending on the work; for 1 M msg/s in aggregate you need 50–200 consumer processes distributed across 100 partitions.

### Network

- Inter-broker replication at 3 GB/s aggregate requires a non-blocking 10 Gbps fabric.
- Cross-AZ replication (synchronous RF=3 across 3 AZs) pays an extra 1–5 ms latency per ack.

---

## Deep Dive: ASCII Architecture Diagrams

### Diagram 1 — Produce path (sequence)

```
  Producer      Producer     Broker (Leader)     Broker (Follower 1)   Broker (Follower 2)   Consumer (Group A)
      │            │              │                       │                     │                     │
      │ produce()  │              │                       │                     │                     │
      │───────────▶│              │                       │                     │                     │
      │            │ 1) lookup partition leader (metadata)                     │                     │
      │            │ 2) serialize, batch (linger=5ms, batch=32KB)              │                     │
      │            │              │                       │                     │                     │
      │            │ send batch   │                       │                     │                     │
      │            │─────────────▶│                       │                     │                     │
      │            │              │ 3) write to leader log (append-only)        │                     │
      │            │              │ 4) replicate (high-watermark + 1)            │                     │
      │            │              │──────────────────────▶│                     │                     │
      │            │              │────────────────────────────────────────────▶│                     │
      │            │              │ 5) follower acks (after fsync)              │                     │
      │            │              │◀──────────────────────│                     │                     │
      │            │              │◀───────────────────────────────────────────│                     │
      │            │              │ 6) leader updates high-watermark            │                     │
      │            │              │ 7) ack to producer (acks=all)               │                     │
      │            │◀─────────────│                       │                     │                     │
      │ partition, │              │                       │                     │                     │
      │ offset     │              │                       │                     │                     │
      │◀───────────│              │                       │                     │                     │
      │            │              │                       │                     │                     │
      │            │              │                       │                     │  poll (long)         │
      │            │              │                       │                     │◀────────────────────│
      │            │              │ 8) serve from log     │                     │                     │
      │            │              │ (zero-copy if hot)    │                     │                     │
      │            │              │──────────────────────────────────────────────────── batched messages ▶│
      │            │              │                       │                     │                     │
      │            │              │                       │                     │ 9) consumer commits offset
      │            │              │                       │                     │   (after process)     │
      │            │              │                       │                     │                     │
```

### Diagram 2 — Broker layout (per-topic partition placement)

```
  Cluster of 6 brokers (RF=3, 3 partitions for topic "orders"):

  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
  │ Broker 0         │   │ Broker 1         │   │ Broker 2         │
  │ orders-0 (L)     │   │ orders-0 (F)     │   │ orders-0 (F)     │
  │ orders-1 (F)     │   │ orders-1 (L)     │   │ orders-1 (F)     │
  │ orders-2 (F)     │   │ orders-2 (F)     │   │ orders-2 (L)     │
  └──────────────────┘   └──────────────────┘   └──────────────────┘
  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
  │ Broker 3         │   │ Broker 4         │   │ Broker 5         │
  │ orders-0 (—)     │   │ orders-0 (—)     │   │ orders-0 (—)     │
  │ orders-1 (—)     │   │ orders-1 (—)     │   │ orders-1 (—)     │
  │ orders-2 (—)     │   │ orders-2 (—)     │   │ orders-2 (—)     │
  └──────────────────┘   └──────────────────┘   └──────────────────┘

  L = leader; F = follower (ISR); — = not on this broker

  Failure: if Broker 0 dies, orders-0's leader election picks a new leader
  from {Broker 1, Broker 2} (its ISR).  orders-1 and orders-2 are unaffected.
  Replication spread ensures no single broker is a SPOF for any partition.
```

### Diagram 3 — Consumer group rebalance

```
  BEFORE (3 consumers, 6 partitions, group "billing"):
    C0: [P0, P1]
    C1: [P2, P3]
    C2: [P4, P5]

  ──▶ C1 dies (heartbeat timeout)

  REBALANCE in progress (stop-the-world):
    - coordinator detects missing consumer (session.timeout.ms)
    - triggers rebalance; all consumers must rejoin

  AFTER (2 consumers, 6 partitions):
    C0: [P0, P1, P2]
    C2: [P3, P4, P5]
    (C1's partitions redistributed; idle partitions: 0)

  ──▶ with COOPERATIVE rebalancing (incremental):
    - only C1's partitions are revoked
    - other consumers keep processing throughout
    - fewer stop-the-world pauses
```

### Diagram 4 — Idempotent producer + transactional consumer (EOS sketch)

```
  Producer (idempotent)        Broker        Consumer (transactional)
        │                          │                  │
        │ produce(seq=1)           │                  │
        │─────────────────────────▶│                  │
        │  duplicate? (seq in       │                  │
        │   producer epoch)        │                  │
        │  → dedupe, no append     │                  │
        │                          │                  │
        │ produce(seq=2)           │                  │
        │─────────────────────────▶│                  │
        │                          │                  │
        │                          │ poll()           │
        │                          │─────────────────▶│
        │                          │                  │ process
        │                          │                  │ write to outbox
        │                          │                  │ sendOffsetsToTransaction
        │                          │                  │ commitTransaction
        │                          │◀─────────────────│
        │                          │ atomic:          │
        │                          │   offsets +      │
        │                          │   outbox writes  │
        │                          │                  │
        │                          │ result: exactly-once
        │                          │ from Kafka → outbox
        │                          │ (downstream still
        │                          │  needs its own
        │                          │  dedupe or 2PC)
```

---

## Deep Dive: Trade-off Tables

### 1. Log-based vs broker-based (queue) architectures

| Property | **Log-based (Kafka, Pulsar)** | Broker-based (RabbitMQ, ActiveMQ) |
|---|---|---|
| Persistence | always; retained after consume | optional; deleted on ack |
| Ordering | per-partition strong | best-effort |
| Replay | trivial (seek) | not native |
| Per-message ack overhead | amortized (batched) | per-message |
| Smart routing (topic exchange, headers) | weak (key-based partitioning) | strong |
| Per-message priority | no | yes |
| Throughput per node | 100k–1M msg/s | 10k–50k msg/s |
| Operational complexity | medium | medium |
| Best for | event streams, CDC, analytics | RPC-style task distribution, low-latency work queues |

### 2. Replication: sync vs async, leader-based vs quorum

| Scheme | Durability | Latency | Use case |
|---|---|---|---|
| Leader + sync followers (ISR) | high (acks=all) | RTT to slowest follower | Kafka default |
| Leader + async followers | low (data loss on leader death) | low | rare, log-only |
| **Quorum (R=3, W=3, ack after 2)** | high (any 2 of 3) | one RTT | Dynamo-style |
| Chain replication | high | sequential RTTs | PNUTS-style |
| Hinted handoff | medium | low during partition | mobile-first |

### 3. Storage backend: local disk vs object store (S3) vs tiered

| Backend | Latency | Cost | Durability | Throughput per broker |
|---|---|---|---|---|
| NVMe local | sub-ms | medium | medium (replicated) | 1–5 GB/s |
| SATA SSD | 1–5 ms | low | medium | 200–500 MB/s |
| S3 / object store | 10–50 ms | very low | very high (11 9s) | effectively unlimited |
| **Tiered (hot SSD + cold S3)** | hot: ms; cold: 10s of ms | **lowest** | high | broker becomes compute, not storage |

Tiered (Pulsar BookKeeper + S3, or Kafka with tiered storage) is the modern pattern; brokers become stateless compute over a durable log on S3.

### 4. Coordination: ZooKeeper vs KRaft vs etcd

| Property | ZooKeeper | **KRaft (Kafka)** | etcd |
|---|---|---|---|
| Consensus algorithm | ZAB (Paxos-like) | Raft | Raft |
| Operational complexity | high (separate ensemble) | low (in-broker) | medium |
| Latency for metadata | high (ZAB round-trip) | low (Raft over brokers) | low |
| Scalability limit | tens of thousands of znodes | millions of topics/partitions | thousands of keys |
| Adoption in MQ | Kafka (legacy), old Pulsar | **Kafka 2.8+ default** | control-plane only |

### 5. Delivery semantics tradeoffs

| | At-most-once | **At-least-once** | Exactly-once |
|---|---|---|---|
| Loss possible | yes | no | no |
| Duplicates possible | no | yes | no |
| Throughput cost | 1× (baseline) | 1× | 2–5× (transaction overhead) |
| Producer complexity | low | low | medium |
| Consumer complexity | low | medium (idempotency) | high (transactions) |
| Use case | metrics, ephemeral | **default** | financial, inventory |

---

## Deep Dive: Real-World Case Studies

### Apache Kafka (and the LinkedIn origin)

Kafka was created at LinkedIn in 2010–2011 to handle activity tracking and operational metrics at a scale that traditional log aggregation (and Scribe) couldn't keep up with. The original paper (Kreps et al., 2011, "Kafka: a Distributed Messaging System for Log Processing") introduced the "distributed commit log" abstraction that has since become the default.

- **Architecture**: partitioned, replicated, append-only log; pull consumers; long-poll; per-consumer-group offsets.
- **Throughput milestones**: LinkedIn's public numbers through the 2010s grew from "10s of thousands msg/s" to "trillions of messages per day" by 2019. The architectural reasons are exactly the chapter above: sequential disk writes, zero-copy, batching.
- **Coordination evolution**: ZooKeeper-based control plane (2011–2022) → KRaft (Raft-based, no ZK) from Kafka 2.8 onward. KRaft removes a major operational pain point and allows single-cluster scaling to millions of partitions.

### Apache Pulsar

Pulsar, originally from Yahoo, takes the log abstraction a step further by separating **compute** (brokers) from **storage** (BookKeeper, a distributed write-ahead log). This is the "tiered" pattern from above.

- **BookKeeper** is the persistent log; brokers are stateless and can be replaced/restarted without data movement. Adding capacity is "add a broker," not "rebalance petabytes."
- **Geo-replication** is built in (multi-cluster by default, with policy-based replication).
- **Functions / connectors**: Pulsar Functions is a lightweight compute model for stream processing without a separate Flink/Spark cluster.
- **Trade-off vs Kafka**: Pulsar is more architecturally elegant for elastic scale-out, but the ecosystem (connectors, clients, monitoring) is smaller than Kafka's.

### RabbitMQ

RabbitMQ is the canonical broker-based queue. It is a battle-tested implementation of the AMQP model.

- **Architecture**: per-queue leader with replication via mirrored queues (or quorum queues in modern versions). Per-message ack, exchange-based routing.
- **Strengths**: rich routing (topic, headers, fanout, direct exchanges), per-message priority, dead-lettering, RPC-style patterns.
- **Weaknesses**: lower throughput than log-based systems; replay not native; harder to scale horizontally because state is per-queue, not per-partition.
- **Adoption**: classical task queues, RPC over queues, app integration in enterprises; not the default for event streaming or CDC.

### AWS SQS / SNS

The AWS managed alternative. SQS is a broker-based queue; SNS is a fan-out pub/sub.

- **SQS**: at-least-once, FIFO variant for ordering, dead-letter queues, visibility timeout for ack, **completely managed** with no operational burden.
- **SNS**: pub/sub with multiple delivery targets (SQS, Lambda, HTTP).
- **Trade-off vs self-hosted**: lower ceiling on per-queue throughput, but zero ops. Standard queue gives unlimited throughput with on-demand auto-scaling; FIFO is throttled to 300 msg/s per queue (or 3,000 with batching).
- **Adoption**: glue between AWS services, low-friction task queues; not the first choice for high-throughput event streaming (Kinesis or MSK fill that role).

### AWS Kinesis

Kinesis is the AWS-flavored streaming log. It is closer to Kafka in spirit, with shards as the partition unit.

- **Shards**: each shard is ~1 MB/s write, ~2 MB/s read. Shard splitting/merging is the scaling lever.
- **Retention**: 1–365 days; consumers use shards (KCL) or Lambda.
- **Adoption**: AWS-native event streaming, clickstreams, IoT. Less popular outside AWS for cross-cloud workloads.

### NATS

NATS is a lightweight, high-performance pub/sub system with a JetStream upgrade for persistence.

- **Core NATS**: at-most-once, fire-and-forget, sub-millisecond latency, ideal for ephemeral signaling and service discovery (NATS is the default in many service meshes).
- **JetStream**: adds persistence, replay, at-least-once / exactly-once, key-value store, object store. Bridges the gap to Kafka-like capabilities at lower operational cost.
- **Adoption**: cloud-native infrastructure, edge/IoT, low-latency RPC.

### ZeroMQ

ZeroMQ is not a broker — it is a **socket library** that gives you messaging primitives. It is the right answer when you need sub-millisecond latency and are willing to handle the operational glue yourself.

- **Patterns**: request-reply, pub/sub, pipeline, pair.
- **Trade-off**: extreme performance, no broker means no replay, no buffering across process restarts. Use for in-cluster or in-process messaging where the producer and consumer are roughly co-located.

### Uber's Ringpop (and the application-level shim)

Ringpop is a Gossip-based membership and failure-detection layer that Uber used to build application-level sharding. It is not a message queue per se, but the pattern is relevant: when you need a queue-like primitive that is also a **swim-lane-aware sharding system**, you may build it on top of a Gossip layer (SWIM protocol). Mentioning Ringpop is the right move when the interviewer asks "what if Kafka is too heavy for this use case?"

### Confluent's tiered storage (Kafka Tiered Storage)

Confluent's modern Kafka added tiered storage (S3 / GCS / Azure Blob) as a first-class feature: recent segments on local disk for hot performance, older segments in object storage for cheap retention. The broker becomes a coordinator for a log that physically lives mostly in S3.

---

## Deep Dive: Common Pitfalls & Failure Modes

### 1. Partition count chosen too small

**Symptom:** a topic created with 3 partitions becomes the throughput bottleneck. Adding more consumers doesn't help (they go idle); individual partitions are hot.

**Root cause:** partition count is the upper bound on consumer parallelism and on per-topic throughput (a single partition tops out at the broker's per-partition write rate, typically 50–100 MB/s).

**Fix:** start with more partitions than you think you need; partition count can only grow (and re-partitioning is expensive — all consumers must rebalance). Typical guidance: each partition ≤ 10 MB/s average, so for 1 GB/s aggregate, ≥ 100 partitions. Plan for 2–3× headroom.

### 2. Hot partition from a skewed key

**Symptom:** a topic's throughput is far below capacity, but a single partition's lag is enormous. The skewed-key entity (a power user, a single tenant in multi-tenant) is overloading one partition.

**Root cause:** the partition key is high-cardinality with skewed distribution, and the hash function sends most of the keyspace to one partition (or the keyspace is dominated by a single hot key).

**Fix:**
- If order isn't required, drop the partition key (round-robin) or use a coarser key (`tenantId` instead of `userId`).
- Use a composite key: hash by `hash(userId) % K`, so K "buckets" of order.
- For the hot key specifically, **shard the entity's traffic** by adding a sub-key (`userId#shard0`, `userId#shard1`, ...).
- Monitor per-partition lag and produce rate; alert on lopsided distributions.

### 3. Unclean leader election causing data loss

**Symptom:** a broker is unreachable for 10 minutes (say, a network partition). The ISR shrinks to 1. When the partition heals, the out-of-sync replica is elected leader, **and messages it didn't have are silently dropped**. The system reports "no message loss" (none of the committed messages were lost) but **uncommitted messages between the leader and the rejoin are gone**.

**Root cause:** unclean leader election is enabled (`unclean.leader.election.enable=true`), trading consistency for availability.

**Fix:** keep `unclean.leader.election.enable=false` in production. The cluster will refuse to elect an out-of-sync leader and the partition will be unavailable until the original leader returns or the ISR is exhausted; prefer unavailability over data loss. Use `min.isr` instead — refuse writes when ISR is too small, but keep reads on ISR.

### 4. Rebalance storm

**Symptom:** a consumer group is in a constant cycle of rebalance. Throughput collapses; no progress is made; logs are full of "REBALANCE_IN_PROGRESS."

**Root cause:**
- `session.timeout.ms` too low for the GC / network jitter of the consumers.
- `max.poll.interval.ms` too low for the consumer's processing time.
- A "chatty" consumer that doesn't process fast enough between polls.

**Fix:**
- Raise `session.timeout.ms` and `max.poll.interval.ms` to realistic values (e.g., 30 s / 5 min).
- Use **static membership** (`group.instance.id`) so the same consumer rejoins the same assignment after a restart instead of triggering a full rebalance.
- Use **cooperative-sticky** assignor so rebalances are incremental, not stop-the-world.

### 5. Producer retries without idempotence causing duplicates

**Symptom:** the producer sees an `Unknown` ack (network blip), retries, and the broker appends the message twice. Downstream consumers see duplicates.

**Root cause:** the producer is not idempotent (`enable.idempotence=false`).

**Fix:** set `enable.idempotence=true` and `acks=all` (Kafka enforces this combo). The producer assigns each message a producer ID + sequence number; the broker dedupes within the producer's session. For cross-session dedupe, transactional producers (`transactional.id`) provide stronger guarantees.

### 6. Offset committed before processing (silent message loss)

**Symptom:** a consumer crashes after committing its offset but before processing the message. On restart, the message is never processed.

**Root cause:** the consumer is configured for at-most-once (commit, then process).

**Fix:** invert the order — process, then commit. Accept the duplicate-on-crash trade-off and add idempotency downstream. Most modern Kafka clients default to this; the bug usually shows up when someone manually tunes `enable.auto.commit=true` for performance without realizing the implication.

### 7. Disk full from misconfigured retention

**Symptom:** brokers fill their disks overnight; producers start failing with `RecordTooLargeException` or worse, becoming unavailable.

**Root cause:** `retention.ms` is set very high, or `retention.bytes` is unset, on a topic with a higher-than-expected ingest rate. A burst in traffic, or a new topic, fills the disk before the retention job runs.

**Fix:**
- Always set both `retention.ms` and `retention.bytes` on every topic; the smaller of the two wins.
- Run a disk-usage monitor and alert at 70% capacity.
- Use **tiered storage** for high-retention topics: old segments to S3, not local disk.

### 8. Long-poll starvation under high consumer concurrency

**Symptom:** a partition has 100 consumers in a group (over-provisioned); long-poll requests pile up; the broker's fetch-handler thread pool is exhausted; latency spikes.

**Root cause:** Kafka allows more consumers than partitions in a group; idle consumers still send heartbeats and may issue long-poll requests.

**Fix:**
- Always size the consumer group to ≤ partition count.
- Set `max.poll.records` and a sane `max.poll.interval.ms` so idle consumers don't busy-loop.
- Use **Kafka Quotas** (produce / fetch byte rate) per client to bound resource use.

### 9. Schema evolution breaking consumers

**Symptom:** a producer ships a new field; old consumers crash because they expect a different schema.

**Root cause:** no schema registry; no compatibility check.

**Fix:** integrate a **schema registry** (Confluent Schema Registry, Apicurio). Enforce a compatibility policy (`BACKWARD`, `FORWARD`, `FULL`). Add a CI check that runs every new schema through a compatibility test against the current head.

### 10. "At-least-once is enough" turning into a billing incident

**Symptom:** a payment processor consumes a "charge customer" event, charges the customer, and the consumer crashes before committing. The event is redelivered; the customer is charged twice.

**Fix:** this is the canonical reason to use exactly-once semantics — but only at the cost of throughput and complexity. Real-world fix: a **deduplication key** (e.g., a `chargeId` derived from the message id) at the downstream system. The consumer becomes idempotent. This is cheaper than full EOS and is the right default.

---

## Deep Dive: Interview Q&A

### Q1. "Why partitions? Why not just have a single log?"

**Answer sketch.** A single log serializes everything — one writer at a time, no parallelism, one failure domain. Partitions let you **scale throughput horizontally**: N partitions can sustain N× the write rate, and N consumer processes can read in parallel. The trade-off is that ordering is per-partition, not global; the right way to think about it is "I get ordering for free within a partition, and I choose the partitioning key to put related events on the same partition."

### Q2. "Why pull, not push?"

**Answer sketch.** Push (broker-to-consumer) requires the broker to model each consumer's capacity and back off; it's hard to do well, and the broker becomes the bottleneck. Pull puts the consumer in control: it fetches at its own pace, batches efficiently, and can catch up by reading a large range. The downside — latency when idle — is solved with long-poll: the fetch request blocks server-side until data arrives or a timeout. Net: pull is simpler, more efficient, and naturally replayable (consumer just requests older offsets).

### Q3. "How do you scale to 10x? 100x?"

**Answer sketch (10x).** 10 M msg/s. The math: 10 GB/s raw, 30 GB/s aggregate replication, ~6 PB retention over 7 days. Add brokers (linear, with rebalance), add partitions (carefully — only grow), add a tiered-storage layer so old segments move to S3. Producer batching becomes essential (64 KB batches, 20 ms linger). Consumer group parallelism scales with partition count.

**Answer sketch (100x).** 100 M msg/s — a system like LinkedIn's "trillions of messages per day" scale. Multi-region active-active, geo-replication between clusters, **per-region tiered storage** so each region's data is mostly local. Producer-side **batching + compression at the source** (LZ4 / Zstandard). Consider **Kafka-on-Kafka** (the "Kafka of Kafka"): use one cluster to coordinate metadata and route between many regional clusters, each with its own tiered storage.

### Q4. "What if we go global? Multi-region?"

**Answer sketch.** Two patterns:
- **Active-passive (stretch cluster)**: one cluster spans regions with synchronous replication. Simple, but pays the WAN RTT on every ack. Suitable for low-latency LANs between, say, US-East and US-West.
- **Active-active (mirror maker)**: each region has its own cluster; a separate process (MirrorMaker 2, or a custom replicator) tails one cluster and produces to another. Asynchronous; eventual consistency. Suitable for global products where each region's users are mostly local.
- Pick active-active for write locality; pick active-passive for low RTT clusters and operational simplicity.

### Q5. "Exactly-once — is it real?"

**Answer sketch.** It is real **within Kafka** (idempotent producer + transactional consumer) and it is real **between Kafka and a system that supports idempotent writes** (idempotent producer + transactional outbox + idempotent consumer on the other side). It is **not free**: transactional commits are 2–5× slower than plain produce/consume, and end-to-end EOS to an external system without idempotent writes still requires deduplication. Default to at-least-once + idempotent consumers; reach for transactions only when the cost of duplicates is genuinely catastrophic (financial transactions, inventory decrement).

### Q6. "How do you handle poison-pill messages?"

**Answer sketch.** A poison-pill is a message that consistently crashes the consumer (bad payload, unexpected schema). Three layers: (1) **schema validation at the consumer** — drop and log before processing; (2) **retry with backoff** for transient failures; (3) **dead-letter topic** after N failures, so a poison-pill is parked for human review instead of looping. Monitor the dead-letter topic volume; non-zero dead-letters is a signal that a producer shipped bad data.

### Q7. "How do you backfill a new consumer without re-reading the whole log?"

**Answer sketch.** Two patterns: (1) **snapshot-and-tail** — the new consumer reads the compacted log (the latest state per key), then starts tailing; (2) **time-bounded seek** — `seek(timestamp = T - 24h)` to read only the last day, then tail. Compaction is the more powerful primitive; it is also the right answer for rebuilding state after a bad deploy.

### Q8. "How do you test this?"

**Answer sketch.** Four layers: (a) **correctness fixtures** — known-produce-then-consume round trips; idempotence under retry; transactional atomicity. (b) **chaos** — kill a broker, kill a controller, partition a rack, verify ISR shrinks and leaders re-elect. (c) **load tests** — sustain 1 M msg/s for 24 hours and watch for disk leaks, lag growth, rebalance storms. (d) **soak** — measure consumer lag p99 over weeks; catch slow degradations (e.g., a memory leak in the consumer that only shows up after 7 days).

---

## Glossary

| Term | Definition | Common misconception |
|---|---|---|
| **Partition** | The unit of ordering, parallelism, and replication in a topic. | "Partitions are a storage detail." They are the central design lever; most trade-offs derive from them. |
| **Offset** | A monotonically increasing per-partition position; consumers track it. | "Offset is global." No — offset is per-partition, per-consumer-group. |
| **ISR (In-Sync Replica)** | The set of replicas fully caught up to the leader; only ISR can be elected leader. | "Replicas always equal ISR." No — a lagging replica is removed. |
| **High-watermark** | The last committed offset; consumers cannot read beyond it. | "Consumers see all messages." They see only committed messages. |
| **acks** | Producer-side durability knob: 0, 1, or all. | "acks=all is always right." It is correct, but adds RTT; for ephemeral metrics, acks=1 is fine. |
| **min.insync.replicas** | The minimum ISR size required for a write to be accepted (with acks=all). | "Default is fine." Default is 1, which is no better than acks=1; production should set 2. |
| **Consumer group** | A set of consumers that load-balance a topic's partitions. | "Consumer groups are for ordering." They are for parallelism; ordering is per-partition. |
| **Rebalance** | The reassignment of partitions across consumers in a group when membership changes. | "Rebalance is free." Stop-the-world rebalances pause consumption; use cooperative-sticky. |
| **Idempotent producer** | A producer that assigns sequence numbers so the broker dedupes retries. | "Idempotence is just a flag." It is a per-producer-ID state; the broker stores recent sequence numbers. |
| **Transactional producer** | A producer that batches produces and offset commits atomically. | "Transactions give EOS everywhere." They give EOS within Kafka; downstream systems still need their own handling. |
| **Log compaction** | Retention mode that keeps only the latest value per key, like a changelog. | "Compaction deletes all old data." It deletes intermediate values; the latest value per key survives. |
| **Retention** | The time/size window a topic's data is kept on disk. | "Retention = how long consumers can read." Retention is a storage property; consumer offsets are independent. |
| **Pull / long-poll** | The consumer-driven fetch model with server-side blocking on empty. | "Pull is high-latency." With long-poll, the only added latency is the small linger window. |
| **ZooKeeper / KRaft** | The coordination layer that stores cluster metadata. | "ZooKeeper is part of Kafka." Modern Kafka (KRaft mode) does not need ZooKeeper. |
| **Dead-letter queue** | A sink for messages that fail processing N times. | "DLQ is the same as the main topic." It is a separate topic with separate retention and monitoring. |
| **Schema registry** | A service that stores and validates schemas; enforces compatibility. | "Schema is in the message." The bytes don't carry the schema; the registry is the source of truth. |
| **Zero-copy** | `sendfile(2)`: kernel-level copy from page cache to socket, no userspace. | "Zero-copy is a Kafka feature." It's an OS feature that Kafka exploits. |
| **Page cache** | The OS's file cache in unused RAM. | "Page cache is the broker's memory." It is the OS's; broker-managed "memory" is a different layer. |
| **Producer epoch** | The producer's identity token, changed on each `transactional.id` reset. | "Epoch is per-message." It is per producer session, used to fence zombies. |
| **Zombie producer** | A producer that was fenced but kept running due to a network partition. | "Zombies don't matter." Without epoch fencing, they can corrupt the log. |
