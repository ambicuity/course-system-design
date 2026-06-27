# Which Database Should I Use on AWS?

> Match your data model and access patterns to the right engine — not the other way around.

**Type:** Learn
**Prerequisites:** Relational vs. NoSQL databases, CAP theorem basics, AWS fundamentals
**Time:** ~25 minutes

---

## The Problem

You're architecting an e-commerce platform on AWS. Within a single application you need to store structured user accounts with ACID transactions, a product catalog with flexible schemas, shopping-cart session state that must survive restarts, click-stream analytics over billions of events, and a recommendation graph linking customers to products. If you reach for a single database — most commonly RDS PostgreSQL — you will hit the ceiling on one or more of these requirements within months: the analytics queries kill your OLTP latency, the graph traversals require 40-way JOINs, and the session store adds unnecessary read pressure to your primary database.

The deeper trap is that AWS exposes more than a dozen managed database services, each optimized for a different combination of data model, access pattern, and scale. Without a decision framework you either default to what you already know (usually relational), or you end up bikeshedding in architecture meetings for weeks. Both outcomes hurt your system.

This lesson gives you that framework: a repeatable way to map your requirements to the right AWS database, understand the trade-offs each service makes, and avoid the most common migrations-after-launch regrets.

---

## The Concept

### The Four Questions

Before comparing services, answer these four questions about your workload:

1. **What is the shape of your data?** — tabular rows, documents, key-value pairs, wide rows, graph edges, time-stamped measurements?
2. **What are your access patterns?** — random point reads/writes by primary key, complex multi-table JOINs, full-text search, range scans over time, graph traversals?
3. **What consistency and durability guarantees do you need?** — strong consistency, eventual consistency, ACID transactions, idempotent upserts?
4. **What is your scale profile?** — GB or PB? Hundreds or millions of requests per second? Read-heavy or write-heavy?

Your answers map almost directly to a database category, and then to a specific AWS service.

### AWS Database Landscape

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AWS Database Portfolio                          │
├───────────────┬───────────────────────────────────────────────────────  │
│  Category     │  AWS Service(s)                                         │
├───────────────┼─────────────────────────────────────────────────────────┤
│  Relational   │  Amazon RDS, Amazon Aurora                              │
│  Document     │  Amazon DocumentDB (MongoDB-compat)                     │
│  Key-Value    │  Amazon DynamoDB                                        │
│  Wide-Column  │  Amazon Keyspaces (Cassandra-compat)                    │
│  Graph        │  Amazon Neptune                                         │
│  Time-Series  │  Amazon Timestream                                      │
│  Search       │  Amazon OpenSearch Service                              │
│  In-Memory    │  Amazon ElastiCache (Redis / Memcached)                 │
│  Ledger       │  Amazon QLDB                                            │
│  Data Warehouse│ Amazon Redshift                                        │
└───────────────┴─────────────────────────────────────────────────────────┘
```

### Deep Dive: Each Category

#### Relational — RDS and Aurora

Both services run familiar SQL engines. The critical distinction is in the architecture:

- **Amazon RDS** is a managed lift of existing open-source and commercial engines (MySQL, PostgreSQL, MariaDB, Oracle, SQL Server). The primary instance writes to EBS volumes; read replicas stream the WAL. Failover is ~60–120 seconds.
- **Amazon Aurora** rewrites the storage layer. A single logical volume is spread across six storage nodes in three AZs. Writes only need four of six nodes to acknowledge (quorum). Failover is ~30 seconds. Aurora PostgreSQL-compatible and MySQL-compatible versions exist.

Use RDS when you already manage a specific engine version and need fine-grained control, or when licensing (Oracle, SQL Server) is a concern. Use Aurora when you need higher availability, faster failover, and up to 5× the write throughput of vanilla MySQL for roughly the same cost per compute hour.

**Aurora Serverless v2** adds per-ACU (Aurora Capacity Unit) automatic scaling, making it practical for workloads with large traffic spikes.

#### Key-Value / Document — DynamoDB

DynamoDB is the single most misunderstood AWS database. It is a fully managed, multi-region, multi-active key-value and document store. Every item is accessed by a **partition key** (mandatory) and an optional **sort key**. Secondary indexes (GSI/LSI) let you query on non-key attributes, but at a replication cost.

The key property: DynamoDB can sustain **millions of requests per second** with single-digit millisecond latency, indefinitely, at any table size, as long as your access patterns are designed at modeling time. If your queries change after launch you pay a steep schema-refactoring cost.

DynamoDB is wrong for ad-hoc SQL, complex JOINs, or workloads where you don't know your query patterns up front.

#### Document — DocumentDB

DocumentDB is AWS's managed MongoDB-compatible service. It stores JSON documents with flexible schemas and supports rich query expressions, nested document access, and secondary indexes by field value. Unlike DynamoDB, it allows you to query arbitrary fields without pre-defining indexes at design time — at the cost of lower write throughput ceilings and more complex capacity management.

Choose DocumentDB when you have a MongoDB-heavy team, a workload with variable document shapes, and you want managed operations without DynamoDB's strict key-design discipline.

#### Wide-Column — Keyspaces

Amazon Keyspaces (for Apache Cassandra) is a serverless Cassandra-compatible service. Wide-column stores excel at time-series-adjacent workloads where you write a lot and query by a well-known partition key plus a time range — user activity logs, IoT sensor readings by device, audit trails. If you have a Cassandra-native data model and want AWS to manage it, Keyspaces is the direct path.

#### In-Memory — ElastiCache

ElastiCache provides managed Redis or Memcached clusters. Both offer sub-millisecond latency, but differ significantly:

| Feature | Redis | Memcached |
|---|---|---|
| Persistence | RDB snapshots + AOF | None (pure RAM) |
| Data structures | Strings, Hashes, Lists, Sets, Sorted Sets, Streams | Strings only |
| Pub/Sub | Yes | No |
| Cluster mode | Yes (sharded) | Yes (sharded) |
| Multi-AZ failover | Yes | No |

**Use Redis** for session stores, leaderboards, rate limiters, pub/sub queues, and any cache where you need data structures beyond a simple string. **Use Memcached** for the simplest possible volatile object cache where you need maximum per-node memory density and are comfortable with data loss on restart.

#### Analytics — Redshift

Redshift is a columnar petabyte-scale data warehouse. It is OLAP, not OLTP. Queries that would be catastrophic on RDS (full-table aggregations, wide groupBys across hundreds of millions of rows) finish in seconds on Redshift because columnar compression and vectorized execution are designed for exactly that. Redshift Serverless removes capacity planning; provisioned clusters give you predictable cost at high utilization.

---

## Build It / In Depth

### Worked Example: Mapping an E-Commerce System

```
┌─────────────────────────────────────────────────────────────────────┐
│                         E-Commerce Platform                         │
│                                                                     │
│  [User Accounts]     →  RDS Aurora PostgreSQL                       │
│  [Product Catalog]   →  DocumentDB  (flexible attrs per category)   │
│  [Shopping Cart]     →  ElastiCache Redis  (TTL, fast R/W)          │
│  [Order History]     →  DynamoDB   (pk=userId, sk=orderId#timestamp)│
│  [Inventory Counts]  →  DynamoDB   (atomic counters via UpdateItem) │
│  [Session Tokens]    →  ElastiCache Redis  (string K/V + TTL)       │
│  [Search / Autocomplete] → OpenSearch Service                       │
│  [Recommendations]   →  Neptune  (user→product graph)               │
│  [Click-stream ETL]  →  Kinesis → Redshift  (analytics OLAP)       │
│  [IoT sensor data]   →  Timestream  (native time-series queries)    │
└─────────────────────────────────────────────────────────────────────┘
```

### Decision Procedure (Use This in Design Reviews)

```
START
  │
  ├─ Need ACID transactions across multiple tables?
  │     YES → RDS (Aurora PostgreSQL) ──────────────────────────────┐
  │     NO  ↓                                                        │
  │                                                                  │
  ├─ Access pattern: point reads/writes by known key at massive RPS? │
  │     YES → DynamoDB                                               │
  │     NO  ↓                                                        │
  │                                                                  │
  ├─ Data is JSON documents with ad-hoc query fields?                │
  │     YES → DocumentDB                                             │
  │     NO  ↓                                                        │
  │                                                                  │
  ├─ Need sub-millisecond latency cache or session store?            │
  │     YES → ElastiCache Redis                                      │
  │     NO  ↓                                                        │
  │                                                                  │
  ├─ Analytics / aggregations over large historical datasets?        │
  │     YES → Redshift                                               │
  │     NO  ↓                                                        │
  │                                                                  │
  ├─ Timestamp-ordered measurements (IoT, metrics, logs)?            │
  │     YES → Timestream                                             │
  │     NO  ↓                                                        │
  │                                                                  │
  ├─ Full-text search, facets, autocomplete?                         │
  │     YES → OpenSearch Service                                     │
  │     NO  ↓                                                        │
  │                                                                  │
  └─ Relationship traversal (friends-of-friends, fraud graph)?
        YES → Neptune
        NO  → Revisit your data model — something is off            │
                                                                     │
END ←──────────────────────────────────────────────────────────────────┘
```

### Quick Infrastructure Example: Aurora + DynamoDB + ElastiCache

```bash
# 1. Provision Aurora PostgreSQL (Serverless v2, pay-per-ACU)
aws rds create-db-cluster \
  --db-cluster-identifier prod-aurora \
  --engine aurora-postgresql \
  --engine-version 15.4 \
  --serverless-v2-scaling-configuration MinCapacity=0.5,MaxCapacity=16 \
  --master-username admin \
  --master-user-password "$DB_PASS" \
  --enable-cloudwatch-logs-exports postgresql

# 2. Create DynamoDB table for orders (on-demand billing)
aws dynamodb create-table \
  --table-name Orders \
  --attribute-definitions \
      AttributeName=userId,AttributeType=S \
      AttributeName=orderId,AttributeType=S \
  --key-schema \
      AttributeName=userId,KeyType=HASH \
      AttributeName=orderId,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST

# 3. Provision ElastiCache Redis cluster (Multi-AZ)
aws elasticache create-replication-group \
  --replication-group-id prod-redis \
  --replication-group-description "Session / cart cache" \
  --engine redis \
  --cache-node-type cache.r7g.large \
  --num-cache-clusters 2 \
  --automatic-failover-enabled
```

---

## Use It

### Reference Architecture by Workload Type

| Workload | Primary DB | Cache | Analytics |
|---|---|---|---|
| SaaS multi-tenant app | Aurora PostgreSQL | ElastiCache Redis | Redshift |
| Mobile / gaming backend | DynamoDB | ElastiCache Redis | (DynamoDB Streams → S3 → Athena) |
| Content management | DocumentDB | ElastiCache Redis | OpenSearch |
| IoT platform | Timestream + Keyspaces | — | Redshift |
| Social network | Neptune (graph) + DynamoDB | ElastiCache Redis | Redshift |
| Financial ledger | QLDB (immutable audit) | — | Redshift |
| Search-first product | OpenSearch | — | OpenSearch aggregations |

### When Polyglot Persistence Pays Off

Large systems almost always use multiple databases. The practice is called **polyglot persistence**. The cost is operational complexity: more connection strings, more failure domains, more backup policies, more schema migrations to coordinate. AWS managed services reduce that overhead significantly because provisioning, patching, backups, and Multi-AZ failover are handled for you. The remaining complexity is your application code managing transactions that span multiple stores — which is why event-driven architectures (DynamoDB Streams, Aurora zero-ETL to Redshift) are common bridges.

---

## Common Pitfalls

- **Treating DynamoDB as a relational database.** DynamoDB is not a general-purpose query engine. If you find yourself creating many GSIs to answer ad-hoc queries, your access patterns were not defined at design time. Switch to DocumentDB or RDS, or go back and define your query patterns before modeling.

- **Using RDS for session storage.** Session tokens are written and read on every authenticated request. Routing that traffic through RDS adds latency and consumes connection slots. ElastiCache Redis is the standard solution — it handles sessions in microseconds and evicts stale tokens with TTLs automatically.

- **Ignoring Aurora over RDS for production OLTP.** For most new greenfield applications on AWS, Aurora offers better availability (six-way storage replication, faster failover), comparable cost, and higher throughput than standard RDS. Defaulting to RDS without evaluating Aurora is a common oversight.

- **Running analytics queries on the OLTP database.** Long-running GROUP BY and aggregate queries on RDS or Aurora block or delay OLTP transactions. Even with a read replica, large scans compete with replication lag. Use Redshift or Athena for analytics and load data via Aurora zero-ETL integration or DMS.

- **Under-provisioning ElastiCache and treating it as optional.** Engineers often add ElastiCache as an afterthought after the database becomes a bottleneck. At that point the application is not cache-aware, leading to a painful refactor. Design cache-aside or write-through patterns from day one.

---

## Exercises

1. **Easy — Classification drill.** For each workload below, name the most appropriate AWS database and explain your reason in one sentence: (a) a leaderboard updated 10,000 times per second; (b) a product catalog where each category has a different set of attributes; (c) a fraud detection graph linking accounts, devices, and IP addresses.

2. **Medium — Schema migration cost.** You have a DynamoDB table with `pk=userId` and `sk=timestamp` storing user events. Your product manager asks for a new query: "give me all events of type `purchase` across all users in the last 7 days". Describe the options available — GSI, table scan, new table design, or alternative service — and compare their cost and latency trade-offs.

3. **Hard — Polyglot design.** Design the database layer for a ride-sharing platform that must handle: driver and rider profiles (relational), real-time location pings from 1 million active drivers (write-heavy, time-ordered), trip history queries by rider (point lookup), surge pricing recalculated every 30 seconds (cache), and end-of-day earnings reports by city (analytics). Assign an AWS service to each requirement, justify the choice, and describe the data flow between services.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Managed database | AWS handles everything | AWS handles provisioning, patching, backups, and Multi-AZ failover — you still own schema design, query optimization, and index tuning |
| DynamoDB on-demand | Scales infinitely with no limits | Scales elastically without capacity planning, but per-request pricing can exceed provisioned throughput cost at sustained high RPS — model both |
| Aurora vs RDS | Aurora is just RDS with a different name | Aurora replaces the storage engine with a purpose-built distributed volume; same SQL interface, very different durability and failover architecture under the hood |
| ElastiCache Redis | A simple cache | A full in-memory data structure server with persistence, pub/sub, Lua scripting, Streams, and atomic operations — far more than a dumb key-value cache |
| Polyglot persistence | Using many databases is always complex and bad | A common production pattern where each service or data domain uses the database best suited for its access patterns, with managed services reducing operational cost |
| GSI (Global Secondary Index) | A free query shortcut in DynamoDB | A separate partition of the table replicated asynchronously; reads from a GSI can be eventually consistent and consume additional write capacity units |
| Redshift | An analytics-tuned RDS | A columnar MPP (massively parallel processing) data warehouse — completely different execution engine, storage format, and optimization strategy from row-oriented OLTP databases |

---

## Further Reading

- [AWS Database Services Overview](https://aws.amazon.com/products/databases/) — official AWS landing page with use-case guides for each service
- [Amazon DynamoDB Developer Guide — Best Practices for Designing and Using Partition Keys](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-design.html) — the canonical resource for DynamoDB data modeling
- [Amazon Aurora User Guide — How Aurora Differs from MySQL and PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Overview.html) — explains the storage architecture and performance characteristics
- [The DynamoDB Book by Alex DeBrie](https://www.dynamodbbook.com/) — the definitive reference for access-pattern-first NoSQL modeling on DynamoDB
- [AWS re:Invent 2023: Which database should I use? (DAT209)](https://www.youtube.com/watch?v=hwnNbLXN4vA) — AWS solution architects walk through the decision framework with real customer architectures
