# How to Learn Databases?

> Databases are not a single skill — they are a layered discipline; learn them in the right order and each layer unlocks the next.

**Type:** Learn
**Prerequisites:** None
**Time:** ~25 minutes

---

## The Problem

You are designing a system for millions of users. Someone asks: "Should we use Postgres or Cassandra?" You know both names but you cannot articulate *why* one fits better than the other. You guess — and six months later the team is migrating because write amplification on the relational schema is killing latency at scale.

The deeper problem is that "databases" is not one topic. It is six overlapping disciplines: data modeling, query languages, index internals, transaction semantics, replication, and operational tooling. Most engineers learn one corner well (SQL SELECT statements) and stay vague on the rest. When a system design interview or a real production incident forces precision, the gaps show up immediately.

This lesson lays out a structured learning map — the same six layers that experienced engineers use implicitly — and explains what each layer buys you and in what order to tackle it. By the end you will know not just *what* to learn, but *why each layer matters* and what breaks if you skip it.

---

## The Concept

### The Six-Layer Learning Stack

Database knowledge compounds layer by layer. Skipping a layer does not save time; it creates confusion at the next layer.

```
┌────────────────────────────────────────────────────────────┐
│  Layer 6 — Tools & Ecosystem                               │
│  (SQL DBs, NoSQL DBs, GUIs, ORMs, Cloud services)         │
├────────────────────────────────────────────────────────────┤
│  Layer 5 — Security, Backups & Scaling                     │
│  (Roles, Encryption, Replication, Failover, H/V scaling)   │
├────────────────────────────────────────────────────────────┤
│  Layer 4 — Indexing & Optimization                         │
│  (B-Tree, Hash, Bitmap, Query plans, Sharding, Pooling)    │
├────────────────────────────────────────────────────────────┤
│  Layer 3 — Querying & Language                             │
│  (SQL basics, Advanced SQL, NoSQL querying)                │
├────────────────────────────────────────────────────────────┤
│  Layer 2 — Data Models & Types                             │
│  (Relational, Document, Key-Value, Graph, Time-Series)     │
├────────────────────────────────────────────────────────────┤
│  Layer 1 — Fundamentals                                    │
│  (ACID, BASE, OLTP vs OLAP, Transactions, Isolation)       │
└────────────────────────────────────────────────────────────┘
```

### Layer 1 — Fundamentals

This is the vocabulary layer. Two frameworks define almost all database behavior:

**ACID** (Atomicity, Consistency, Isolation, Durability) — the contract of relational databases. A bank transfer that debits one account and credits another must either complete entirely or not at all. Without atomicity, you get half-executed transactions and corrupt balances.

**BASE** (Basically Available, Soft state, Eventually consistent) — the contract most distributed NoSQL systems make. Instead of locking rows across nodes (expensive over a network), they allow temporary divergence and converge later. Suitable for shopping carts; unsuitable for financial ledgers.

**OLTP vs OLAP** is equally foundational:

| Dimension        | OLTP                          | OLAP                          |
|------------------|-------------------------------|-------------------------------|
| Query shape      | Point reads + small writes    | Full table scans, aggregations|
| Latency target   | < 10 ms                       | Seconds to minutes acceptable |
| Row count/query  | 1–100                         | Millions to billions          |
| Storage layout   | Row-oriented                  | Column-oriented               |
| Example          | Postgres, MySQL               | BigQuery, Redshift, ClickHouse|

Mixing these up costs real money: running BI reports directly against your production OLTP database is the most common performance disaster in early-stage companies.

**Isolation levels** (Read Uncommitted → Read Committed → Repeatable Read → Serializable) control what a transaction can see from concurrent transactions. Lower isolation = more throughput, more anomalies. Most databases default to Read Committed. Postgres defaults to Read Committed; MySQL's InnoDB defaults to Repeatable Read.

### Layer 2 — Data Models

The data model is the single most consequential design decision. Getting it wrong is expensive to reverse.

| Model         | Structure               | Best for                              | Examples                  |
|---------------|-------------------------|---------------------------------------|---------------------------|
| Relational    | Tables, rows, joins     | Structured data, complex queries      | Postgres, MySQL, SQLite   |
| Document      | JSON/BSON trees         | Hierarchical, schema-flexible data    | MongoDB, Firestore        |
| Key-Value     | Hash map                | Session caches, feature flags         | Redis, DynamoDB (simple)  |
| Wide-Column   | Rows + dynamic columns  | Time-series, append-heavy workloads   | Cassandra, HBase          |
| Graph         | Nodes + edges           | Social networks, recommendation graphs| Neo4j, Amazon Neptune     |
| Time-Series   | Timestamped metrics     | Monitoring, IoT, financial ticks      | InfluxDB, TimescaleDB     |

### Layer 3 — Querying

SQL is the lingua franca of data. The progression:

1. **Core DML**: SELECT, INSERT, UPDATE, DELETE with WHERE, JOIN, GROUP BY, ORDER BY, LIMIT.
2. **Advanced SQL**: Window functions (`ROW_NUMBER`, `RANK`, `LAG`/`LEAD`), CTEs (`WITH` clauses), Views, Stored procedures, Triggers.
3. **NoSQL querying**: Aggregation pipelines (MongoDB), Key-Value lookups, scan/filter operations in DynamoDB.

Window functions and CTEs are where most engineers plateau. They unlock patterns like rolling averages, cohort analysis, and recursive hierarchies that would otherwise require application-side post-processing.

### Layer 4 — Indexing & Optimization

Indexes are the performance layer. The two index types you must internalize:

**B-Tree index** — the default in Postgres, MySQL, and nearly every relational database. Balanced tree structure. Supports equality, range queries, and `ORDER BY`. O(log n) lookup. Works for most use cases.

**Hash index** — O(1) equality lookup, but cannot handle range queries or ordering. Useful for exact-match primary keys.

**Bitmap index** — column with low cardinality (e.g., `gender`, `status`). Stores a bit per row. Extremely efficient for AND/OR combinations in analytical queries.

Beyond index type, the query execution plan (`EXPLAIN ANALYZE` in Postgres) tells you whether the planner chose a sequential scan or an index scan, the estimated vs actual rows, and where time is spent. Learning to read a query plan is the most leveraged skill in database optimization.

**Sharding** partitions data horizontally across database nodes (by user ID range, hash, or geography). It multiplies write throughput but complicates cross-shard joins and transactions. Do not shard prematurely.

### Layer 5 — Security, Backups & Scaling

**Security**: Principle of least privilege — application users should not have `SUPERUSER`. Encrypt data at rest (AES-256) and in transit (TLS). Parameterized queries to prevent SQL injection.

**High availability** is built on two primitives:
- **Replication**: Primary continuously streams WAL (Write-Ahead Log) to standbys. Read replicas offload read traffic; hot standbys enable fast failover.
- **Failover**: Automatic promotion of a standby when the primary fails. Tools: Patroni (Postgres), Orchestrator (MySQL), managed cloud RDS multi-AZ.

**Scaling paths**:
```
Vertical scaling:  bigger machine → works until you hit the ceiling
                   Pros: no application changes  Cons: single point of failure, expensive

Read scaling:      add read replicas → offload reads, writes still single node
                   Pros: simple  Cons: replication lag

Write scaling:     sharding → distribute writes across nodes
                   Pros: horizontal  Cons: complex joins, distributed transactions
```

### Layer 6 — Tools & Ecosystem

Knowing which tool to reach for and when:

| Category         | Tools                                              |
|------------------|----------------------------------------------------|
| SQL databases    | Postgres (general), MySQL (web apps), SQLite (embedded) |
| NoSQL document   | MongoDB, Firestore (Firebase)                      |
| Key-Value / Cache| Redis, Memcached                                   |
| Wide-Column      | Cassandra, HBase                                   |
| Cloud managed    | AWS RDS, Aurora, DynamoDB; GCP Cloud SQL, BigQuery; Azure Cosmos DB |
| ORMs             | SQLAlchemy (Python), Prisma (TypeScript), Hibernate (Java) |
| GUI tools        | DBeaver, TablePlus, pgAdmin                        |
| Query optimization| `EXPLAIN ANALYZE`, `pg_stat_statements`, slow query logs |

---

## Build It / In Depth

### A Worked Learning Path: From Zero to Production-Ready

**Week 1 — Fundamentals + Data Models**

Start by running Postgres locally and experimenting with transactions:

```sql
-- Demonstrate atomicity: both or neither
BEGIN;
  UPDATE accounts SET balance = balance - 100 WHERE id = 1;
  UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;
-- Roll back if anything fails:
-- ROLLBACK;
```

Then try breaking isolation intentionally:

```sql
-- Session A
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM accounts WHERE id = 1;   -- reads 500

-- Session B (concurrently)
UPDATE accounts SET balance = 600 WHERE id = 1;
COMMIT;

-- Back in Session A
SELECT balance FROM accounts WHERE id = 1;   -- now reads 600 (non-repeatable read)
COMMIT;
```

This exercise makes isolation levels concrete faster than any diagram.

**Week 2 — SQL Querying**

Progress from basic to window functions:

```sql
-- Basic: total orders per user
SELECT user_id, COUNT(*) AS order_count
FROM orders
GROUP BY user_id
ORDER BY order_count DESC;

-- Advanced: rank users by revenue within each country (window function)
SELECT
  user_id,
  country,
  revenue,
  RANK() OVER (PARTITION BY country ORDER BY revenue DESC) AS country_rank
FROM user_revenue;

-- CTE: find users who placed an order in month 1 and again in month 2
WITH month1_users AS (
  SELECT DISTINCT user_id FROM orders
  WHERE DATE_TRUNC('month', created_at) = '2024-01-01'
),
month2_users AS (
  SELECT DISTINCT user_id FROM orders
  WHERE DATE_TRUNC('month', created_at) = '2024-02-01'
)
SELECT m1.user_id FROM month1_users m1
JOIN month2_users m2 ON m1.user_id = m2.user_id;
```

**Week 3 — Indexing + EXPLAIN**

```sql
-- Create a table and observe a sequential scan
CREATE TABLE events (id SERIAL, user_id INT, created_at TIMESTAMPTZ, type TEXT);
EXPLAIN ANALYZE SELECT * FROM events WHERE user_id = 42;
-- → Seq Scan on events (cost=0.00..1234.56 rows=10 ...)

-- Add a B-Tree index and observe the change
CREATE INDEX idx_events_user_id ON events(user_id);
EXPLAIN ANALYZE SELECT * FROM events WHERE user_id = 42;
-- → Index Scan using idx_events_user_id on events (cost=0.29..8.32 rows=10 ...)
```

Reading the EXPLAIN output: `cost=startup..total`, `rows=estimate`, `actual time=Xms`, `loops=N`. When `actual rows` is far from `rows`, statistics are stale — run `ANALYZE events` to refresh them.

**Week 4 — Try a NoSQL database (Redis + MongoDB)**

```python
import redis
r = redis.Redis()
r.set("session:abc123", '{"user_id": 42, "role": "admin"}', ex=3600)
val = r.get("session:abc123")  # Returns bytes; decode to string
```

```javascript
// MongoDB aggregation pipeline: revenue by category
db.orders.aggregate([
  { $match: { status: "completed" } },
  { $group: { _id: "$category", total: { $sum: "$amount" } } },
  { $sort: { total: -1 } }
])
```

---

## Use It

### How real systems combine these layers

**E-commerce platform (Shopify-like)**:
- Postgres for orders, inventory (ACID, relational, complex joins)
- Redis for cart sessions and rate limiting (Key-Value, millisecond latency)
- Elasticsearch for product search (inverted index, full-text)
- BigQuery or Redshift for analytics (OLAP, columnar)

**Social media feed (Twitter-like)**:
- Cassandra for timelines (wide-column, write-heavy, time-ordered)
- Redis for follower/following counts and feed caching
- Neo4j or purpose-built graph service for recommendations
- MySQL for user accounts and settings (OLTP)

**Decision heuristic — when to use what**:

```
Need complex joins + strong consistency?         → Postgres / MySQL (RDBMS)
Need flexible schema + document hierarchies?     → MongoDB
Need sub-millisecond reads, ephemeral data?      → Redis
Need write-heavy, multi-region, no joins?        → Cassandra / DynamoDB
Need full-text search?                           → Elasticsearch / Typesense
Need OLAP / analytics on billions of rows?       → BigQuery / ClickHouse / Redshift
```

---

## Common Pitfalls

- **Treating NoSQL as "faster SQL"**: NoSQL trades away joins and transactions for scale. If your access patterns require multi-entity joins, a relational database is almost always the right call. Using MongoDB for highly relational data leads to application-level join spaghetti.

- **Forgetting indexes in development, noticing in production**: Local dev datasets are tiny; queries are fast even with sequential scans. Production data at 10 million rows reveals missing indexes brutally. Add indexes before data grows, not after.

- **Sharding prematurely**: Sharding is operationally complex and hard to undo. Most systems perform fine on a single well-tuned Postgres instance up to tens of millions of rows. Add read replicas first, then consider sharding.

- **Conflating replication lag with data loss**: A read replica can lag the primary by milliseconds to seconds. Reading from a replica immediately after a write can return stale data. Writes that must read their own data should go to the primary.

- **Using ORM magic without understanding generated SQL**: ORMs like Hibernate or SQLAlchemy can generate N+1 queries silently. Always log and inspect the SQL in development. An innocent `user.orders` traversal can become 500 SELECT statements.

---

## Exercises

1. **Easy** — Create a `users` and `orders` table in SQLite or Postgres. Write a query using a CTE that finds all users who have placed more than 3 orders in the past 30 days. Run `EXPLAIN` on your query.

2. **Medium** — Take the same `orders` table and add 1 million rows (use `generate_series` in Postgres or a script). Observe the query plan before and after adding a composite index on `(user_id, created_at)`. Record the actual execution time difference and explain why the composite index helps more than a single-column index.

3. **Hard** — Design the data model for a real-time ride-sharing system (drivers, riders, trips, locations). Decide which parts go into Postgres, which into Redis, and which into a time-series store. Write the schema for Postgres, justify why the location updates go elsewhere, and explain how you would handle the trip-completion transaction (fare calculation + driver payout) atomically.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| ACID | A feature you turn on in "enterprise" databases | Four guarantees (Atomicity, Consistency, Isolation, Durability) that define whether a database is safe for financial-grade writes |
| Index | A copy of the table that speeds things up | A separate data structure (often a B-Tree) that the database maintains alongside the table to enable O(log n) lookups instead of O(n) scans |
| Sharding | A way to make any database faster | Horizontal partitioning of data across multiple database nodes; multiplies write capacity but breaks cross-shard joins |
| Replication | Backup | A continuously updated copy of the primary on one or more standby nodes, used for both read scaling and high availability |
| NoSQL | A database without SQL | A broad category of databases that do not use the relational model; many have their own query languages |
| OLAP | OLTP but for big queries | Online Analytical Processing — workloads that scan large volumes of data for aggregations, best served by columnar storage |
| Query Plan | An internal implementation detail | The step-by-step execution strategy the query planner chooses; inspecting it with `EXPLAIN ANALYZE` is the fastest path to diagnosing slow queries |

---

## Further Reading

- [PostgreSQL Documentation — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — the canonical reference for understanding isolation levels with concrete examples.
- [Martin Kleppmann, *Designing Data-Intensive Applications*, O'Reilly, 2017](https://dataintensive.net/) — the single best book on databases and distributed systems for engineers; chapters 2–4 cover data models, storage engines, and encoding.
- [Use The Index, Luke](https://use-the-index-luke.com/) — a free, database-agnostic guide to SQL indexing that goes from B-Tree internals to practical tuning.
- [AWS Database Blog — Choosing the right database](https://aws.amazon.com/blogs/database/how-to-determine-if-amazon-dynamodb-is-appropriate-for-your-needs-and-then-plan-your-migration/) — real-world decision criteria from AWS engineers on when to use DynamoDB vs relational options.
- [CMU 15-445/645 Database Systems (Carnegie Mellon)](https://15445.courses.cs.cmu.edu/) — free lecture videos and slides covering storage engines, indexes, query execution, and concurrency control at a rigorous level.
