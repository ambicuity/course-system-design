# Apache Kafka vs. RabbitMQ

> Kafka is a distributed log built for streaming; RabbitMQ is a message broker built for routing — using the wrong one doubles your complexity.

**Type:** Learn
**Prerequisites:** Message Queues Fundamentals, Pub/Sub Pattern, Event-Driven Architecture
**Time:** ~25 minutes

---

## The Problem

Your checkout service just crashed mid-payment. Orders were in-flight. You want to replay every event that happened in the last two hours to reconstruct state and find the bug. Your team reaches for RabbitMQ — and discovers the messages are already gone. Consumers acknowledged them, they were deleted. There is nothing left to replay.

Meanwhile, another team builds an email notification system using Kafka. Each email-send is a message. Once the worker consumes and sends the email, the task is done. But Kafka kept that message for seven days. Now you have millions of stale "send email" records consuming disk space, and your consumer group offsets are drifting because a new consumer accidentally replayed three days of duplicate sends.

Both failures share the same root cause: the tool was matched to the wrong workload. Kafka and RabbitMQ are not interchangeable queue implementations. They are built on different mental models — a distributed commit log versus a routed message broker — and the mismatch shows up immediately in production.

---

## The Concept

### Mental Model Difference

| Dimension | Apache Kafka | RabbitMQ |
|---|---|---|
| Core abstraction | Distributed append-only log | Message broker with routing |
| Message lifetime | Time/size-based retention (days/weeks) | Deleted after consumer acknowledges |
| Consumer model | Pull (consumer controls offset) | Push (broker delivers to consumer) |
| Delivery guarantee | At-least-once by default; exactly-once available | At-least-once with acks; publisher confirms |
| Ordering | Strict within a partition | Per-queue FIFO; no global ordering |
| Throughput | Millions of messages/sec | Tens of thousands/sec per queue |
| Replay | Yes — rewind offset to any point | No — consumed messages are gone |
| Routing | Partition key (hash-based) | Exchanges: direct, topic, fanout, headers |
| Primary use case | Event streaming, analytics pipelines | Task queues, RPC, workflow routing |

### How Kafka Works Under the Hood

A Kafka **topic** is divided into **partitions**. Each partition is an ordered, immutable log stored on disk. Producers append records to the end of a partition. Consumers maintain a cursor called an **offset** — a simple integer indicating the next record to read. The broker never tracks "who consumed what"; the consumer owns that state (or delegates it to Kafka's internal `__consumer_offsets` topic).

```
Topic: orders  (3 partitions)

Partition 0:  [msg0][msg1][msg4][msg7] ← Producer appends here
Partition 1:  [msg2][msg5][msg8]
Partition 2:  [msg3][msg6][msg9]

Consumer Group A (inventory service):
  P0 offset=4, P1 offset=3, P2 offset=3  ← reads all events

Consumer Group B (analytics service):
  P0 offset=4, P1 offset=3, P2 offset=3  ← reads same events independently
```

Both consumer groups read the same messages at their own pace. Neither one affects the other. A new analytics pipeline added today can set its offset to `earliest` and process every event ever written — up to the retention window.

Within a partition, ordering is guaranteed. Across partitions, it is not. You control which partition a message lands on via a partition key (e.g., `order_id`). All events for the same order land in the same partition, giving you per-order ordering.

### How RabbitMQ Works Under the Hood

RabbitMQ is built around the **AMQP** model. Producers publish to an **exchange**, not directly to a queue. The exchange applies a routing rule and forwards the message to one or more bound **queues**. Consumers subscribe to queues; the broker pushes messages to them.

```
Producer
   │
   ▼
 Exchange (topic: "orders")
   ├── binding: "order.created" ──→ Queue: new-orders-queue ──→ Consumer: fulfillment
   ├── binding: "order.*"       ──→ Queue: audit-log-queue  ──→ Consumer: auditor
   └── binding: "#"             ──→ Queue: analytics-queue  ──→ Consumer: analytics
```

Exchange types:
- **Direct** — exact routing key match
- **Topic** — wildcard pattern (`order.*`, `#`)
- **Fanout** — broadcast to all bound queues, ignores routing key
- **Headers** — route on message header attributes instead of key

Once a consumer sends an `ack`, the message is removed from the queue. If the consumer crashes before acking, the broker re-delivers to another consumer. This makes RabbitMQ excellent for work queues where each task must be executed exactly once, but it means there is no replay.

### The Log vs. Queue Dichotomy

```
QUEUE model (RabbitMQ):
  Message enters → sits in queue → delivered to one consumer → deleted on ack
  Think: post office mailbox. Letter is gone once collected.

LOG model (Kafka):
  Message enters → appended to partition → any consumer reads at any offset → deleted only on retention expiry
  Think: newspaper archive. Anyone can read today's or last month's issue.
```

This dichotomy drives every architectural decision:

- **Need fan-out to independent services?** Kafka is natural — each consumer group reads independently. In RabbitMQ you need a separate queue per consumer, which is workable but adds topology management.
- **Need smart routing based on content?** RabbitMQ excels — exchange bindings handle it declaratively. In Kafka you'd filter in the consumer or use Kafka Streams for topic-to-topic routing.
- **Need event sourcing or audit logs?** Kafka's retention makes it a built-in event store. RabbitMQ requires an external store.
- **Need guaranteed task completion with one worker?** RabbitMQ's competing consumers on a single queue is the simplest model. Kafka requires consumer group coordination.

---

## Build It / In Depth

### Kafka: Publishing and Consuming with Python

```bash
# Start Kafka locally (Docker Compose)
docker run -d --name kafka \
  -p 9092:9092 \
  -e KAFKA_ENABLE_KRAFT=yes \
  -e KAFKA_CFG_NODE_ID=1 \
  -e KAFKA_CFG_PROCESS_ROLES=broker,controller \
  -e KAFKA_CFG_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093 \
  -e KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
  -e KAFKA_CFG_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 \
  -e KAFKA_CFG_CONTROLLER_LISTENER_NAMES=CONTROLLER \
  bitnami/kafka:3.7
```

```python
# producer.py
from kafka import KafkaProducer
import json

producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    key_serializer=lambda k: k.encode("utf-8"),
)

# Partition key = order_id ensures same order always lands in same partition
producer.send("orders", key="order-42", value={"event": "created", "order_id": 42})
producer.flush()
```

```python
# consumer.py — consumer group "fulfillment"
from kafka import KafkaConsumer
import json

consumer = KafkaConsumer(
    "orders",
    bootstrap_servers="localhost:9092",
    group_id="fulfillment",          # group tracks offsets independently
    auto_offset_reset="earliest",    # start from beginning if no committed offset
    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    enable_auto_commit=False,        # manual commit for at-least-once safety
)

for msg in consumer:
    process(msg.value)
    consumer.commit()                # advance offset only after processing
```

A second consumer group (`analytics`) pointing at the same topic reads the same events independently — no changes needed to the producer or the first group.

### RabbitMQ: Topic Exchange with Python (pika)

```bash
docker run -d --name rabbitmq \
  -p 5672:5672 -p 15672:15672 \
  rabbitmq:3-management
```

```python
# publisher.py
import pika, json

conn = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
ch = conn.channel()

ch.exchange_declare(exchange="orders", exchange_type="topic", durable=True)

ch.basic_publish(
    exchange="orders",
    routing_key="order.created",
    body=json.dumps({"order_id": 42}),
    properties=pika.BasicProperties(delivery_mode=2),  # persistent
)
conn.close()
```

```python
# worker.py — fulfillment service
import pika, json

conn = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
ch = conn.channel()

ch.exchange_declare(exchange="orders", exchange_type="topic", durable=True)
ch.queue_declare(queue="fulfillment", durable=True)
ch.queue_bind(queue="fulfillment", exchange="orders", routing_key="order.created")

def on_message(ch, method, properties, body):
    data = json.loads(body)
    process(data)
    ch.basic_ack(delivery_tag=method.delivery_tag)  # delete only after success

ch.basic_consume(queue="fulfillment", on_message_callback=on_message)
ch.start_consuming()
```

A second service binds its own queue to `order.*` and receives the same events — but only if it is declared and bound before the messages arrive. Messages published before the binding existed are missed.

### Decision Procedure

```
Does the system need replay / audit trail?
  YES → Kafka

Does the system need routing logic (content-based, wildcard)?
  YES → RabbitMQ

Is throughput > 100k msg/sec?
  YES → Kafka

Are consumers short-lived workers (jobs, emails, webhooks)?
  YES → RabbitMQ

Do multiple independent services need the same event?
  YES → Kafka (consumer groups are zero-coupling)

Do you need per-message TTL, dead-letter queues, or priority?
  YES → RabbitMQ
```

---

## Use It

### Where Kafka Dominates

| Company / System | Use Case |
|---|---|
| LinkedIn (origin) | Activity feeds, metrics pipeline |
| Confluent Platform | Fully managed Kafka + Schema Registry + Kafka Connect |
| Apache Flink + Kafka | Real-time stream processing at scale |
| Debezium (CDC) | Change Data Capture — DB changes as Kafka events |
| AWS MSK | Managed Kafka on AWS |
| Event sourcing systems | Kafka as the durable event store |

Kafka pairs naturally with **Kafka Streams** or **Apache Flink** for stateful transformations, aggregations, and joins directly on the log — no separate data store required for intermediate state.

### Where RabbitMQ Dominates

| Company / System | Use Case |
|---|---|
| Celery (Python) | Default broker for distributed task queues |
| Laravel Queue | PHP background job processing |
| Mass Transit (.NET) | Enterprise message bus over RabbitMQ |
| Microservice RPC | Request/reply pattern via reply-to queues |
| CloudAMQP | Managed RabbitMQ hosting |

RabbitMQ's **dead-letter exchanges (DLX)** and **message TTL** are mature primitives for retry logic and delayed processing that Kafka requires application-level workarounds to replicate.

### Cloud Alternatives

- **AWS SQS + SNS** — managed queue + fan-out; closer to RabbitMQ semantics
- **AWS Kinesis** — managed Kafka-like stream; lower operational overhead
- **Google Pub/Sub** — managed pub/sub with replay; hybrid positioning
- **Azure Service Bus** — enterprise broker; RabbitMQ semantics
- **Azure Event Hubs** — Kafka-compatible API; stream-first

---

## Common Pitfalls

- **Treating Kafka as a simple queue.** If you have one consumer group and delete the topic after consumption, you are using a distributed log as an expensive queue. Use RabbitMQ, SQS, or a database-backed queue instead.

- **Expecting RabbitMQ messages to survive for replay.** Messages are deleted on acknowledgment. New consumers never see old messages. If you need an audit trail or event sourcing, you need a log, not a broker.

- **Ignoring Kafka partition count after creation.** Changing partition count redistributes which partition key maps where, breaking per-key ordering guarantees. Set partition count correctly up front based on target parallelism.

- **Consumer group offset drift in Kafka.** If a consumer group stops consuming and Kafka's `log.retention.ms` elapses, the earliest available offset advances past the committed offset, causing `OffsetOutOfRangeException`. Monitor consumer lag and alert on groups that fall too far behind.

- **RabbitMQ queue length unbounded under backpressure.** If consumers are slower than producers, queues grow indefinitely. Set `x-max-length` limits, use lazy queues for large backlogs, and implement publisher confirms to detect overflow early.

- **Conflating Kafka topics with RabbitMQ queues.** A Kafka topic is a shared log that all consumer groups read. A RabbitMQ queue is private to its consumers. Designing your Kafka topics like queues (one topic per consumer) loses the fan-out advantage entirely.

---

## Exercises

1. **Easy** — Draw a data flow diagram for an e-commerce order service. Label which events (order created, payment captured, shipment dispatched) you would put on a Kafka topic and which task (send confirmation email) you would put on a RabbitMQ queue. Justify each choice in one sentence.

2. **Medium** — A new analytics team joins mid-project and needs to read all `order.created` events from the last 30 days. Describe exactly what configuration changes are needed in (a) a Kafka system and (b) a RabbitMQ system. Which is simpler and why?

3. **Hard** — Design a hybrid architecture for a ride-sharing platform: (a) Kafka for location updates (10k drivers, 1k updates/sec each), (b) RabbitMQ for driver-to-rider match notifications. Specify partition strategy, consumer group design, exchange type, routing key scheme, and how you handle a driver going offline mid-ride. Identify the failure modes at the boundary between the two systems.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Partition | A shard you scale by adding | An ordered, append-only log segment; the unit of parallelism and ordering |
| Consumer Group | Multiple consumers sharing a subscription | A set of consumers where each partition is assigned to exactly one member; offsets are tracked per group |
| Offset | A message ID | An integer position in a partition log; the consumer owns it, not the broker |
| Exchange | A router in RabbitMQ | A broker component that applies a routing rule and dispatches to zero or more queues; does not store messages |
| Ack | Confirmation the message was received | Signal to the broker that processing succeeded and the message may be deleted from the queue |
| Retention | How long Kafka keeps messages | Time- or size-based policy on a topic; independent of whether anyone consumed the message |
| Lag | How behind a consumer is | The difference between the latest offset in a partition and the consumer's committed offset; the primary health metric for Kafka consumers |

---

## Further Reading

- [Kafka Documentation — Core Concepts](https://kafka.apache.org/documentation/) — Official reference for topics, partitions, consumer groups, and configuration.
- [RabbitMQ Tutorials](https://www.rabbitmq.com/getstarted.html) — Six progressive tutorials covering queues, exchanges, routing, and RPC patterns.
- [Confluent: Kafka vs. Traditional Messaging](https://developer.confluent.io/courses/apache-kafka/intro/) — Confluent's free course covering Kafka internals and comparison with traditional brokers.
- [Martin Kleppmann — *Designing Data-Intensive Applications*, Chapter 11](https://dataintensive.net/) — The definitive treatment of stream processing, log-based messaging, and how they compare to databases.
- [CloudAMQP: RabbitMQ vs Kafka](https://www.cloudamqp.com/blog/when-to-use-rabbitmq-or-apache-kafka.html) — Practical comparison with real benchmark numbers and use-case guidance.
