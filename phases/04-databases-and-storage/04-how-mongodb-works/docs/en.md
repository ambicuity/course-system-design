# How MongoDB Works?

> MongoDB trades the rigid rows-and-columns of SQL for flexible JSON-shaped documents, then scales them horizontally across shards without you rewriting your queries.

**Type:** Learn
**Prerequisites:** Relational vs. NoSQL Databases, CAP Theorem, Database Replication Basics
**Time:** ~25 minutes

---

## The Problem

You're building a product catalog for an e-commerce platform. Electronics have voltage ratings and warranty terms; apparel has sizes and colors; books have ISBNs and authors. In a relational database every new attribute forces an `ALTER TABLE`, a nullable column, or a join to a secondary attributes table. As the catalog grows to tens of millions of items, each query that fetches a product and its attributes becomes a multi-table join at scale — expensive and brittle when the schema keeps evolving.

You also face a traffic spike problem. A single primary server handles millions of daily active users browsing products. Vertical scaling (bigger box) has a ceiling and a single point of failure. Sharding in a relational system requires application-level logic to decide which host owns which rows, and foreign-key constraints break across shard boundaries.

MongoDB was designed for exactly this combination: a schema that changes per document, queries that don't cross document boundaries (eliminating joins as a hot path), and a distributed architecture where sharding and replication are first-class citizens built into the database engine — not bolted on afterward.

---

## The Concept

### Documents and Collections

MongoDB stores data as **BSON** (Binary JSON) documents — ordered sets of key-value pairs that support rich types: strings, numbers, arrays, nested sub-documents, dates, ObjectIds, and binary data. A document lives inside a **collection** (analogous to a table), and a collection lives inside a **database**.

```json
{
  "_id": ObjectId("64f1a2b3c4d5e6f7a8b9c0d1"),
  "sku": "PHONE-XR-128",
  "category": "electronics",
  "price": 799.99,
  "specs": {
    "battery_mah": 3110,
    "screen_inches": 6.1
  },
  "tags": ["apple", "5g", "unlocked"],
  "available_since": ISODate("2023-01-15")
}
```

There is no enforced schema across documents in a collection. Two documents can have completely different fields. Optional schema validation can be attached to a collection at the database level if you want guardrails without going full relational.

### The WiredTiger Storage Engine

Since MongoDB 3.2, the default storage engine is **WiredTiger**. It gives you:

- **Document-level concurrency control** — multiple writers can modify different documents in the same collection simultaneously without blocking each other (MVCC-style).
- **Compression** — Snappy by default for data, zlib optional. Indexes use prefix compression.
- **Checkpoints and journaling** — WiredTiger writes a checkpoint (a consistent snapshot to disk) every 60 seconds. Between checkpoints, a write-ahead journal (WAL) captures operations so no committed write is lost on crash.

### Replica Sets — Durability and HA

A **replica set** is a group of `mongod` processes that hold the same dataset. One node is the **primary** (handles all writes); the rest are **secondaries** that replicate from the primary using an **oplog** (operations log).

```
        Writes/Reads
   Client ──────────────► Primary
                             │
               oplog stream  │
               ┌─────────────┤
               ▼             ▼
          Secondary 1   Secondary 2
          (can serve     (can serve
           reads)         reads)
```

**Election flow:** If the primary becomes unreachable, the remaining nodes hold an election. A candidate must receive votes from a majority of the set. With a 3-node replica set, any two surviving nodes can elect a new primary. The process typically completes in 10–30 seconds.

**Write concern:** Controls how many replica acknowledgements MongoDB waits for before returning success to the client.

| Write Concern | Behaviour | Risk |
|--------------|-----------|------|
| `w:1` | Ack from primary only | Data loss if primary crashes before replication |
| `w:majority` | Ack from majority of nodes | Safe; default in MongoDB 5+ |
| `w:0` | Fire-and-forget | Maximum throughput, no durability guarantee |

**Read preference:** By default reads go to the primary. Setting `readPreference: secondary` can offload analytics queries to secondaries at the cost of reading slightly stale data.

### Sharding — Horizontal Scale-Out

When a single replica set can no longer handle the data volume or write throughput, you shard. Sharding distributes data across multiple replica sets called **shards**, each owning a subset of the collection.

```
                        ┌─────────────┐
   Application  ──────► │   mongos    │  (Query Router — stateless)
                        └──────┬──────┘
                               │ looks up routing table
                        ┌──────▼──────┐
                        │Config Servers│  (3-node replica set, stores
                        │  (CSRS)     │   chunk metadata & shard map)
                        └─────────────┘
                               │
             ┌─────────────────┼──────────────────┐
             ▼                 ▼                  ▼
        Shard 1           Shard 2             Shard 3
    (replica set)     (replica set)       (replica set)
    range A–F         range G–N           range O–Z
```

**Shard key:** You pick a field (or compound field) as the shard key. MongoDB partitions the key space into **chunks** and assigns chunks to shards. The `mongos` reads the shard key from a query and routes it to exactly the right shard. Without the shard key, `mongos` must fan the query out to all shards (**scatter-gather**) and merge results — far more expensive.

**Chunk balancing:** A background **balancer** process moves chunks between shards when one shard accumulates more than others, keeping distribution even.

**Shard key strategies:**

| Strategy | Good for | Watch out for |
|----------|----------|---------------|
| Hashed shard key | Even write distribution | Range queries hit all shards |
| Range shard key | Range queries efficient | Hot spots if key is monotonic (e.g., timestamps) |
| Zone sharding | Geo compliance, data locality | Complex to set up |

### Indexes

MongoDB indexes are B-tree structures (except geospatial and text). Every collection gets a default index on `_id`. You add compound indexes, multikey indexes (on array fields), TTL indexes (auto-expire documents), and partial indexes (index a filtered subset).

```
Query: db.products.find({ category: "electronics", price: { $lt: 500 } })

Without index: collection scan — O(n)
With compound index { category: 1, price: 1 }: index scan — O(log n)
```

The **`explain()`** command shows the query plan. Always check `"stage": "IXSCAN"` not `"COLLSCAN"` for latency-sensitive queries.

---

## Build It / In Depth

### Step 1 — Connecting and Basic CRUD

```python
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["shop"]
products = db["products"]

# Insert
result = products.insert_one({
    "sku": "BOOK-DDIA",
    "category": "books",
    "price": 49.99,
    "tags": ["distributed-systems", "databases"]
})
print(result.inserted_id)  # ObjectId(...)

# Read
doc = products.find_one({"sku": "BOOK-DDIA"})

# Update (immutable pattern — use $set, not replace)
products.update_one({"sku": "BOOK-DDIA"}, {"$set": {"price": 44.99}})

# Delete
products.delete_one({"sku": "BOOK-DDIA"})
```

### Step 2 — Adding an Index for a Hot Query

```javascript
// mongosh
db.products.createIndex({ category: 1, price: 1 })

// Verify the plan
db.products.find({ category: "books", price: { $lt: 50 } }).explain("executionStats")
// Look for: winningPlan.stage === "IXSCAN"
```

### Step 3 — Write Concern for Durability

```python
from pymongo import WriteConcern

safe_products = db.get_collection(
    "products",
    write_concern=WriteConcern(w="majority", j=True)
)
safe_products.insert_one({"sku": "CRITICAL-ITEM", "price": 9999})
# MongoDB waits until a majority of replica-set nodes acknowledge the write
# AND the write is flushed to the journal on each.
```

### Step 4 — Querying a Sharded Cluster

```bash
# Connect to mongos (not a direct shard)
mongosh "mongodb://mongos-host:27017/shop"

# Targeted query — includes shard key (userId)
db.orders.find({ userId: "usr_42", status: "shipped" })

# Scatter-gather — no shard key, hits every shard
db.orders.find({ status: "shipped" })  # avoid on large collections
```

### Worked Example: Write Path on a Replica Set

1. Client sends `insertOne` to the **primary**.
2. Primary writes to its **WiredTiger journal** (WAL) — durable even if it crashes mid-way.
3. Primary applies the write to its in-memory data structures and appends an entry to the **oplog**.
4. Secondaries pull new oplog entries and replay them on their own datasets.
5. If `w: majority`, the primary waits until `(n/2)+1` nodes have confirmed the oplog entry before acking the client.

---

## Use It

MongoDB is the go-to choice when:

| Scenario | Why MongoDB fits |
|----------|-----------------|
| Variable-schema entity storage (catalogs, user profiles) | Document model accommodates evolving fields per record |
| Hierarchical or nested data | Sub-documents avoid expensive joins |
| High write throughput with eventual consistency acceptable | Sharding + `w:1` or async replication |
| Geo-spatial queries | Native `$geoNear`, `2dsphere` indexes |
| Time-series (since MongoDB 5.0) | Native time-series collections with automatic bucketing |
| Real-time analytics on operational data | Secondary reads + aggregation pipeline |

**When to prefer something else:**
- Multi-document ACID transactions across many collections → PostgreSQL (MongoDB does support multi-document transactions since 4.0, but the overhead is higher and it's not the primary design target).
- Pure key-value lookups at extreme throughput → Redis or DynamoDB.
- Immutable append-only event logs → Kafka + Parquet or a dedicated time-series DB.

**Managed options:** MongoDB Atlas (AWS/GCP/Azure), AWS DocumentDB (MongoDB-compatible API, different internals).

---

## Common Pitfalls

- **Choosing a bad shard key.** Using a monotonically increasing field like a timestamp or `ObjectId` as the shard key sends all new writes to a single shard (the "hot shard"), killing write scalability. Use a hashed key or a high-cardinality composite key that distributes writes evenly.

- **Embedding unbounded arrays.** MongoDB documents have a 16 MB size limit. Embedding an array of comments on a blog post document looks natural until a viral post accumulates 100,000 comments and every read fetches the full array. Reference the comments in a separate collection instead.

- **Missing indexes on query predicates.** MongoDB will do a full collection scan if no index covers a query field. On a 50 M-document collection, this means reading every document. Always run `explain()` on production query shapes before deploying.

- **Ignoring write concern in critical paths.** Defaulting to `w:1` for financial or inventory writes means a primary crash between write and replication causes data loss. Use `w: majority` for anything you cannot afford to lose.

- **Using `$where` or JavaScript in queries.** `$where` evaluates a JS function per document on the server — no index can be used, and it blocks the JS engine. Replace with native MongoDB operators (`$expr`, comparison operators, etc.).

---

## Exercises

1. **Easy:** Start a local MongoDB instance and insert 10 product documents with varying fields (some with a `specs` sub-document, some without). Run `find()` queries filtering by a nested field (e.g., `"specs.battery_mah": { $gt: 3000 }`). Then add an index on that field and use `explain()` to confirm the query changed from `COLLSCAN` to `IXSCAN`.

2. **Medium:** Set up a 3-node replica set locally using Docker Compose. Simulate a primary failure by stopping the primary container. Observe the election logs on the secondaries, note which node becomes the new primary, and verify that a write issued after failover succeeds. Measure the election time.

3. **Hard:** Design a sharding strategy for a social-media "posts" collection expected to reach 1 billion documents and 50,000 writes/second. Pick and justify a shard key (considering write distribution, common query patterns like `userId + createdAt` range scans, and avoiding hot spots). Sketch a `mongos` + CSRS + shard topology, and calculate how many shards you need if each shard replica set can sustain ~5,000 writes/second.

---

## Key Terms

| Term | What people think | What it actually means |
|------|------------------|----------------------|
| **BSON** | Just binary JSON | A superset of JSON with additional types (ObjectId, Date, binary, Decimal128) serialized in a binary format for efficient traversal and size |
| **Replica Set** | A backup copy of the database | An always-on cluster of `mongod` processes where one primary accepts writes and the rest replicate continuously; automatic failover is built in |
| **Shard Key** | Any field used to split data | The field (or compound fields) whose value MongoDB hashes or ranges over to decide which shard owns a document; a wrong choice permanently limits scalability |
| **mongos** | A database server | A stateless query router; it holds no data, just reads the chunk map from config servers and forwards operations to the correct shards |
| **oplog** | A transaction log | A capped collection on each `mongod` that records every write operation as an idempotent statement; secondaries tail it to stay in sync |
| **Write Concern** | How many copies are written | A durability knob: how many nodes must acknowledge a write before the client gets a success response |
| **WiredTiger** | MongoDB's file format | The pluggable storage engine (default since 3.2) providing MVCC concurrency, compression, and a write-ahead journal |

---

## Further Reading

- [MongoDB Architecture Guide (official)](https://www.mongodb.com/mongodb-architecture) — deep dive into replica sets, sharding, storage engine internals.
- [MongoDB Manual: Sharding](https://www.mongodb.com/docs/manual/sharding/) — authoritative reference on shard key selection, zone sharding, and balancer behavior.
- [MongoDB Manual: Replication](https://www.mongodb.com/docs/manual/replication/) — oplog mechanics, read preferences, and election protocol details.
- [Designing Data-Intensive Applications — Martin Kleppmann, Ch. 2 & 6](https://dataintensive.net/) — places MongoDB's document model and partitioning strategies in the broader landscape of distributed data systems.
- [MongoDB University Free Courses](https://learn.mongodb.com/) — hands-on labs for schema design, performance tuning, and cluster operations.
