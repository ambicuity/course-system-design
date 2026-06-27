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
