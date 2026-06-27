# SQS vs SNS vs EventBridge vs Kinesis

> Pick the wrong messaging primitive and you will either lose data, blow your budget, or rebuild the whole thing six months later.

**Type:** Learn
**Prerequisites:** Microservices & Service Decomposition, Async vs Sync Communication Patterns
**Time:** ~35 minutes

---

## The Problem

You have an order service that needs to trigger three downstream workflows when a customer places an order: decrement inventory, charge the payment card, and email a receipt. The naive approach is to call all three synchronously inside the order endpoint. That works until the inventory service is slow, the payment gateway is timing out, and a downstream outage takes your order service down with it.

The instinct is to "add a queue". But AWS alone gives you four distinct messaging primitives — SQS, SNS, EventBridge, and Kinesis — and they are not interchangeable. Choosing the wrong one means subtle reliability bugs: messages disappearing because no consumer was attached when SNS delivered them, ordering violations because you used a standard SQS queue where FIFO was needed, or a Kinesis stream that costs 10× more than SQS for a use case with 5 messages per minute.

Each service solves a different class of problem. SQS is for work queues. SNS is for fan-out notifications. EventBridge is for content-based routing between loosely coupled services. Kinesis is for ordered, replayable, high-throughput data streams. The architecture collapses quietly when those roles are swapped.

---

## The Concept

### Four Distinct Messaging Models

```
SQS — Work Queue (point-to-point)
─────────────────────────────────
Producer ──▶ [ Queue ] ──▶ Consumer A
                           (message deleted on ack)

SNS — Fan-out Pub/Sub (push)
─────────────────────────────
Publisher ──▶ [ Topic ] ──▶ SQS Queue A ──▶ Consumer A
                         ──▶ SQS Queue B ──▶ Consumer B
                         ──▶ Lambda C
                         ──▶ HTTP Endpoint D

EventBridge — Content-Based Event Bus (push)
─────────────────────────────────────────────
Source ──▶ [ Event Bus ] ──rule: {source:"order"}──▶ Lambda
                         ──rule: {detail.status:"failed"}──▶ SQS DLQ
                         ──rule: catch-all──▶ S3 Archive

Kinesis — Ordered Partitioned Stream (pull)
───────────────────────────────────────────
Producers ──▶ [ Stream ]
               Shard 0: [r1, r2, r3, ...] ──▶ Consumer A (all shards)
               Shard 1: [r4, r5, r6, ...] ──▶ Consumer B (all shards)
               Shard 2: [r7, r8, r9, ...] ──▶ Consumer C (Enhanced Fan-Out)
```

### Service-by-Service Breakdown

#### SQS (Simple Queue Service)

SQS is a durable work queue. One producer writes, one logical consumer reads. The critical mechanism is the **visibility timeout**: when a consumer `ReceiveMessage`, the message becomes invisible to all other consumers for a configurable window (default 30 s). The consumer must call `DeleteMessage` before the timeout expires, or the message reappears for redelivery. This is the foundation of at-least-once delivery.

**Two queue types:**

| | Standard | FIFO |
|---|---|---|
| Ordering | Best-effort | Strict (per message group) |
| Delivery | At-least-once | Exactly-once (deduplication window) |
| Throughput | Unlimited | 300 msg/s (3,000 with batching) |
| Use when | Order doesn't matter | Bank ledger, e-commerce checkout |

Dead-letter queues (DLQs) are a first-class feature: after N failed receive attempts, the message is moved to the DLQ automatically. Always configure one.

#### SNS (Simple Notification Service)

SNS is a pub/sub broker. A publisher sends to a **topic**; SNS pushes the message to every registered subscriber simultaneously. Subscribers can be SQS queues, Lambda functions, HTTP/HTTPS endpoints, email addresses, or SMS.

Critical behavior: **SNS has no storage**. If a subscriber is unreachable at delivery time and the retry policy is exhausted, the message is gone. The standard pattern is **SNS → SQS fan-out** to add durability: SNS does the fan-out, SQS buffers each leg independently.

**Subscription filter policies** are a powerful, underused feature. Each SQS or Lambda subscriber can attach a JSON filter that SNS evaluates against message attributes before delivering — you get cheap content routing without building a router service.

#### EventBridge

EventBridge is a serverless event bus optimised for **event-driven architectures** where the number of producers and consumers changes over time and where routing logic belongs in infrastructure, not application code.

Key differentiators:
- **Event pattern matching**: Routes based on JSON content of the event (not just message attributes). Supports prefix, suffix, and numeric range matching.
- **Schema Registry**: Auto-discovers event schemas from AWS services and your custom buses; generates typed binding code.
- **Archive and Replay**: You can archive all events on a bus and replay them against new or changed rules — invaluable for debugging and backfilling new consumers.
- **Partner integrations**: Direct ingestion from Stripe, Datadog, Zendesk, and 130+ SaaS providers without writing glue code.
- **Default soft limit**: 10,000 events/second per bus (can be raised). Not suited for raw clickstream or telemetry firehose volumes.

EventBridge decouples producers from consumers at the schema level: producers emit canonical events; any future consumer adds a rule without touching the producer.

#### Kinesis Data Streams

Kinesis is an **ordered, replayable, partitioned log** — closer to Apache Kafka than to SQS. Data is grouped into **shards**; each shard provides 1 MB/s write and 2 MB/s read capacity. A **partition key** determines the shard, and records within a shard are strictly ordered by sequence number.

Because consumers track their own read position (sequence number), the same stream can be read by multiple independent consumer applications simultaneously without interfering. This is fundamentally different from SQS, where a consumed message is gone.

**Retention** is configurable from 24 hours (default) to 365 days (extended retention). Consumers can rewind and re-process the full stream from any point within the retention window.

**Enhanced Fan-Out** (EFO) gives each registered consumer a dedicated 2 MB/s read pipe per shard, with data pushed via HTTP/2. Without EFO, all standard consumers share the 2 MB/s limit per shard.

### Comparison Matrix

| Feature | SQS Standard | SQS FIFO | SNS | EventBridge | Kinesis |
|---|---|---|---|---|---|
| Primary pattern | Work queue | Ordered queue | Pub/Sub fan-out | Content-based routing | Ordered stream |
| Consumer model | Pull | Pull | Push | Push | Pull (or push w/ Lambda) |
| Ordering | Best-effort | Strict per group | None | None | Strict per shard |
| Delivery | At-least-once | Exactly-once | At-least-once | At-least-once | At-least-once |
| Retention / durability | Up to 14 days | Up to 14 days | None (push only) | None (unless Archive) | 24 h–365 days |
| Replay | No | No | No | Yes (Archive) | Yes (within window) |
| Max message size | 256 KB | 256 KB | 256 KB | 256 KB | 1 MB |
| Throughput ceiling | Unlimited | 3,000/s batched | Unlimited | ~10k/s per bus | 1 MB/s per shard |
| Fan-out | No | No | Yes | Yes (via rules) | Yes (multi-consumer) |
| Cost model | Per request | Per request | Per publish + delivery | Per event | Per shard-hour + PUT units |

---

## Build It / In Depth

### Decision Flowchart

```
Need to process a background job with exactly one worker?
  └─▶ SQS Standard (or FIFO if order matters)

Need to notify multiple downstream systems of the same event?
  └─▶ SNS → fan-out to multiple SQS queues

Need to route events to different consumers based on event content,
with loose coupling and potential for schema evolution?
  └─▶ EventBridge

Need ordered, replayable, high-throughput data (logs, clickstream,
IoT telemetry) consumed by multiple independent applications?
  └─▶ Kinesis Data Streams
```

### SQS — Image Processing Job Queue

```python
import boto3

sqs = boto3.client("sqs", region_name="us-east-1")
QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789/image-processing"

# Producer: enqueue a job
sqs.send_message(
    QueueUrl=QUEUE_URL,
    MessageBody='{"image_id": "img-999", "bucket": "uploads", "key": "user/42/avatar.jpg"}',
)

# Consumer: poll and process
while True:
    resp = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20,   # long polling — reduces empty responses
        VisibilityTimeout=60, # must finish processing within 60 s
    )
    for msg in resp.get("Messages", []):
        process(msg["Body"])
        sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
```

Always use **long polling** (`WaitTimeSeconds=20`). Short polling hammers the API and costs more. Set `VisibilityTimeout` to 1.5× your expected processing time.

### SNS → SQS Fan-out for Order Events

```bash
# Create topic
TOPIC_ARN=$(aws sns create-topic --name order-events --query TopicArn --output text)

# Create two SQS queues for two downstream consumers
INVENTORY_URL=$(aws sqs create-queue --queue-name inventory-queue --query QueueUrl --output text)
PAYMENT_URL=$(aws sqs create-queue   --queue-name payment-queue   --query QueueUrl --output text)

# Subscribe each queue to the topic
aws sns subscribe \
  --topic-arn "$TOPIC_ARN" \
  --protocol sqs \
  --notification-endpoint "arn:aws:sqs:us-east-1:123456789:inventory-queue"

aws sns subscribe \
  --topic-arn "$TOPIC_ARN" \
  --protocol sqs \
  --notification-endpoint "arn:aws:sqs:us-east-1:123456789:payment-queue"

# Publish — both queues receive the message atomically
aws sns publish \
  --topic-arn "$TOPIC_ARN" \
  --message '{"order_id":"ord-7", "total":49.99, "user_id":"u-123"}' \
  --message-attributes '{"event_type":{"DataType":"String","StringValue":"order.created"}}'
```

### EventBridge — Route on Event Content

```json
// Event schema your order service emits
{
  "source": "com.myapp.orders",
  "detail-type": "OrderPlaced",
  "detail": {
    "order_id": "ord-7",
    "status": "placed",
    "total": 49.99
  }
}
```

```bash
# Rule: route failed payments to an SQS DLQ, everything else to Lambda
aws events put-rule \
  --name "route-payment-failures" \
  --event-bus-name "myapp-bus" \
  --event-pattern '{"source":["com.myapp.payments"],"detail":{"status":["failed"]}}'

aws events put-targets \
  --rule "route-payment-failures" \
  --event-bus-name "myapp-bus" \
  --targets '[{"Id":"dlq","Arn":"arn:aws:sqs:us-east-1:123:payment-failures-dlq"}]'
```

### Kinesis — High-Throughput Clickstream

```python
import boto3, json, time

kinesis = boto3.client("kinesis", region_name="us-east-1")
STREAM = "user-clickstream"

# Producer: put records with a partition key that determines the shard
def track_click(user_id, event):
    kinesis.put_record(
        StreamName=STREAM,
        Data=json.dumps({"user_id": user_id, "event": event, "ts": time.time()}),
        PartitionKey=str(user_id),  # same user always hits same shard — preserves order per user
    )

# Consumer: iterate shards and read from each
def consume_shard(shard_id, iterator_type="LATEST"):
    it = kinesis.get_shard_iterator(
        StreamName=STREAM, ShardId=shard_id, ShardIteratorType=iterator_type
    )["ShardIterator"]
    while it:
        resp = kinesis.get_records(ShardIterator=it, Limit=100)
        for record in resp["Records"]:
            process(json.loads(record["Data"]))
        it = resp["NextShardIterator"]
        time.sleep(1)  # Kinesis GetRecords limited to 5 calls/s per shard
```

In production, use the **Kinesis Client Library (KCL)** or trigger a Lambda directly from the stream — both handle shard enumeration, checkpointing, and shard splits automatically.

---

## Use It

### Real-World Mapping

| Scenario | Service | Why |
|---|---|---|
| E-commerce image resizing queue | SQS Standard | Single worker per job; durability; retry via visibility timeout |
| FIFO bank transaction ledger | SQS FIFO | Strict ordering per account; exactly-once processing |
| New-user signup → email + Slack + analytics | SNS → 3× SQS | Fan-out to independent consumers; each gets durable copy |
| Multi-tenant SaaS event routing | EventBridge | Content-based rules; producers don't know about consumers |
| CI/CD pipeline triggers on GitHub push | EventBridge + partner integration | GitHub SaaS event → CodePipeline without polling |
| Real-time user clickstream analytics | Kinesis | Ordered per user; multiple consumers (analytics + ML); replayable |
| IoT sensor telemetry at 50k events/s | Kinesis | High throughput; partitioned by device ID |
| Audit log that must be replayed | Kinesis (or EventBridge Archive) | Retention window; multi-consumer read |

### Common Architecture Pattern: Fan-out with Durability

The most common production pattern combines SNS and SQS:

```
Order Service
     │
     ▼
[SNS Topic: order-events]
     ├──▶ [SQS: inventory-queue]  ──▶ Inventory Lambda
     ├──▶ [SQS: payment-queue]    ──▶ Payment Lambda
     └──▶ [SQS: analytics-queue]  ──▶ Analytics Lambda
```

SNS delivers to all three queues atomically. Each SQS queue buffers independently — if the analytics Lambda is slow, the payment Lambda is unaffected. DLQs on each SQS queue catch individual failures. This is the pattern to reach for when you need durable fan-out.

---

## Common Pitfalls

- **Treating SNS as a durable bus.** SNS has no storage. If your Lambda subscriber is throttled or erroring and retries exhaust, messages disappish. Always front SNS with an SQS subscription for anything that matters. Configure a DLQ on the SNS subscription itself for HTTP/Lambda subscribers.

- **Ignoring the SQS visibility timeout.** If processing takes 45 seconds and the visibility timeout is 30 seconds, a second consumer picks up the same message before the first finishes. Result: duplicate processing, race conditions, and confused state. Set visibility timeout = 1.5× your P99 processing time and extend it programmatically for long jobs.

- **Underprovisioning Kinesis shards and hitting write throttles.** A single shard handles 1 MB/s or 1,000 records/s — whichever is hit first. At burst load, `ProvisionedThroughputExceededException` gets thrown and records are dropped unless your producer retries with backoff. Monitor `WriteProvisionedThroughputExceeded` and auto-scale (on-demand mode removes this concern).

- **Using EventBridge for high-throughput telemetry.** The default limit is 10,000 events/s per bus (soft limit). A clickstream with 100k events/s will require either Kinesis or requesting a significant limit increase. EventBridge is optimised for lower-volume, content-rich routing — not raw data pipelines.

- **No dead-letter queue configured anywhere.** A message that cannot be processed will be retried until its retention expires and then silently discarded. Always configure DLQs on SQS queues, Kinesis consumer Lambda functions, and SNS subscriptions. Alert on DLQ depth. A non-zero DLQ depth is an incident.

---

## Exercises

1. **Easy** — Draw the fan-out pattern for an e-commerce checkout: one SNS topic, three SQS subscribers (fulfillment, billing, email). Label each component, explain why SNS is used instead of calling three services directly, and identify where you would put DLQs.

2. **Medium** — You are building a real-time leaderboard for a mobile game. 50,000 score events per second arrive from mobile clients. The leaderboard must reflect scores within 2 seconds. Design the ingestion layer: which service handles ingest, how many shards do you provision, how does the leaderboard consumer read from the stream, and what happens when you need to add a second consumer (fraud detection) without slowing down the leaderboard?

3. **Hard** — Your team is migrating a monolith to microservices. The monolith fires 15 types of domain events (order.placed, inventory.updated, payment.failed, etc.) to 8 downstream services, where routing rules change quarterly. Compare an architecture using SNS topics per event type vs. a single EventBridge custom bus. Address: operational overhead of adding a new consumer, cost at 1M events/day, replay capability, schema management, and what happens when a routing rule needs to change.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Visibility timeout** | A message lock | A temporary invisibility window — the message still exists; if not deleted in time, it reappears for another consumer |
| **SNS delivery** | Guaranteed delivery like a queue | Best-effort push; messages are not stored; a subscriber that is down during delivery may not receive the message at all |
| **Kinesis shard** | A queue partition | An ordered, append-only log segment with fixed read/write capacity; multiple consumers can independently track their own position within it |
| **Fan-out** | SNS doing the work alone | Typically SNS + SQS: SNS delivers simultaneously; SQS queues buffer each consumer's copy independently for durability |
| **Exactly-once delivery** | The messaging system guarantees no duplicates | SQS FIFO guarantees this within a 5-minute deduplication window using a client-provided deduplication ID; network failures at consumer ack still require idempotent consumers |
| **EventBridge rule** | A filter on a message header | Full content-based routing on the JSON event body — you can match nested fields, numeric ranges, prefix/suffix, and logical AND/OR |
| **DLQ (Dead-Letter Queue)** | A place where bad messages go | An SQS queue that receives messages after N failed processing attempts — the source of truth for messages your system could not handle; must be monitored |

---

## Further Reading

- [AWS SQS Developer Guide — Visibility Timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [AWS SNS Developer Guide — Message Filtering](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering.html)
- [Amazon EventBridge User Guide — Event Patterns](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-patterns.html)
- [Amazon Kinesis Data Streams Developer Guide — Developing Consumers](https://docs.aws.amazon.com/streams/latest/dev/developing-consumers-with-kcl.html)
- [AWS Architecture Blog — "Decoupling Serverless Workloads with Amazon EventBridge"](https://aws.amazon.com/blogs/compute/decoupling-serverless-workloads-with-amazon-eventbridge/)
