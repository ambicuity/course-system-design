# A Cheatsheet on Database Performance

> The metrics that matter, the strategies that work, and the order to apply them — a one-page reference for tuning any database.

**Type:** Learn
**Prerequisites:** SQL basics, some production database experience
**Time:** ~20 minutes

---

## The Problem

"Database is slow" is the most common production performance complaint. The fix is rarely one thing. It is a sequence of measurements, hypotheses, and changes — each addressing a specific bottleneck. Without a mental model of what to measure and what to try, you waste days changing settings that do not matter.

This lesson is a cheatsheet. It lists the metrics that tell you whether the database is healthy, the strategies that improve performance at each layer, and a recommended order for applying them. Treat it as a checklist to walk through when investigating slow queries or planning a performance project.

---

## The Concept

### The metrics that matter

Four categories of metrics describe database health:

```
   1. Latency
      - Query execution time (p50, p95, p99)
      - Time to first row
      - Lock wait time
      - Replication lag

   2. Throughput
      - Queries per second
      - Transactions per second
      - Rows read/written per second

   3. Resource utilization
      - CPU (per core, ideally)
      - Memory (used, cached, free)
      - Disk I/O (reads/sec, writes/sec, queue depth)
      - Network I/O

   4. Cache effectiveness
      - Buffer cache hit rate (pages read from cache / total pages read)
      - Index hit rate
      - Plan cache effectiveness (where applicable)
```

A healthy database has **low latency, high throughput, moderate resource utilization, and high cache hit rates** (above 99% for buffer cache in steady state). If any one of these is off, the system is unhealthy.

---

### Workload shapes

Different workloads stress the database differently:

| Workload | Characteristics | Optimization focus |
|---|---|---|
| **Read-heavy** | 95%+ SELECTs | Indexes, caching, read replicas |
| **Write-heavy** | Heavy INSERTs/UPDATEs | Batch writes, fewer indexes, faster disks |
| **Mixed** | Both, with peaks | Both sets of optimizations |
| **OLAP** | Complex aggregations, full scans | Columnar storage, materialized views, separate warehouse |
| **OLTP** | Simple point queries, high concurrency | Indexes, transactions tuned for short runs |

Identifying your workload shape is the first step. Optimizations for a read-heavy OLTP workload (more indexes, read replicas) make a write-heavy workload worse.

---

### Other factors that matter

| Factor | Why it matters |
|---|---|
| **Item size** | Wide rows mean fewer per page, less cache efficiency |
| **Item type** | JSON/text vs integers vs blobs — different compression, different storage |
| **Dataset size** | 10 GB fits in memory; 10 TB does not |
| **Concurrency** | High concurrency = more contention = slower individual queries |
| **Consistency requirements** | Strong consistency limits read replicas and caching |
| **HA requirements** | Replication topology affects write latency |
| **Geographic distribution** | Cross-region replication adds 50–200 ms round trip |

---

### The strategies, organized by layer

```
   ┌────────────────────────────────────────────┐
   │  1. Query & Schema                         │
   │     - Indexing                             │
   │     - Query rewriting                      │
   │     - Schema design                        │
   ├────────────────────────────────────────────┤
   │  2. Database Configuration                 │
   │     - Memory (buffers, work_mem)           │
   │     - Parallelism                          │
   │     - Cost model                           │
   ├────────────────────────────────────────────┤
   │  3. Hardware                               │
   │     - Faster storage (NVMe SSD)            │
   │     - More memory                          │
   │     - More CPU cores                       │
   ├────────────────────────────────────────────┤
   │  4. Architecture                           │
   │     - Replication (read replicas)          │
   │     - Sharding / partitioning              │
   │     - Caching layer (Redis, Memcached)     │
   │     - CQRS / read stores                   │
   └────────────────────────────────────────────┘
```

Always start at the top. Hardware and architecture changes are expensive and often unnecessary; query and schema fixes are cheap and high-impact.

---

### Strategy 1: Indexing

The single highest-impact strategy for read performance.

```
   Add an index on columns used in:
     - WHERE clauses (selective filters)
     - JOIN conditions
     - ORDER BY (with matching direction)
     - GROUP BY (sometimes)

   Avoid over-indexing:
     - Each index slows writes
     - Each index uses disk and buffer cache
     - Drop indexes that nothing uses
```

**Diagnostic query (Postgres):**

```sql
-- Find missing indexes (sequential scans on large tables)
SELECT relname, seq_scan, seq_tup_read, idx_scan, idx_tup_fetch,
       n_live_tup
FROM pg_stat_user_tables
WHERE seq_scan > 1000          -- many sequential scans
  AND n_live_tup > 50000       -- large table
ORDER BY seq_tup_read DESC;

-- Find unused indexes
SELECT schemaname, relname, indexrelname, idx_scan, pg_size_pretty(pg_relation_size(indexrelid))
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;
```

---

### Strategy 2: Query rewriting

Sometimes the query itself is the problem.

| Anti-pattern | Better pattern |
|---|---|
| `SELECT *` | Select only needed columns |
| Functions on indexed columns in WHERE | Expression index or rewrite |
| `WHERE col LIKE '%foo%'` (leading wildcard) | Full-text index or rewrite |
| `WHERE col IS NULL` without index | Partial index on `WHERE col IS NULL` |
| `DISTINCT` on large result sets | Rewrite to avoid duplicates upstream |
| Correlated subqueries | JOINs |
| Many small queries in a loop | Batch into one query |
| `OR` conditions on different columns | `UNION` of two indexed queries |

---

### Strategy 3: Schema design

| Principle | Why it helps |
|---|---|
| Use the right types | `INT` is faster than `VARCHAR` for numeric data; `TIMESTAMP` for dates |
| Normalize for write integrity | Reduces redundancy and update anomalies |
| Denormalize for read performance | Reduces joins at the cost of update complexity |
| Partition large tables | Time-based or hash partitioning makes large tables manageable |
| Avoid wide rows | Many columns = poor cache efficiency |
| Avoid blobs in main tables | Move blobs to object storage; store only URL/path |

---

### Strategy 4: Sharding and partitioning

Split a large table into smaller pieces. Two flavors:

**Horizontal partitioning (one node, many tables):**

```sql
CREATE TABLE orders_2024 PARTITION OF orders
FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

CREATE TABLE orders_2025 PARTITION OF orders
FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
```

The database routes queries to the right partition. Old partitions can be archived or dropped without affecting live data.

**Sharding (many nodes, each holds a subset):**

```
   Shard 1:  users with id % 4 == 0
   Shard 2:  users with id % 4 == 1
   Shard 3:  users with id % 4 == 2
   Shard 4:  users with id % 4 == 3
```

Each shard holds ~1/4 of the data. Cross-shard queries are expensive; application logic must be shard-aware. Postgres does not natively shard — tools like Citus add this.

---

### Strategy 5: Denormalization

Strategic duplication to avoid joins at read time.

| Pattern | Use case |
|---|---|
| Cached aggregates | `orders.total` derived from `order_items` |
| Snapshot columns | `customer_name` in `orders` even though it lives in `customers` |
| Materialized views | Pre-computed aggregations |
| Counter tables | Redis-style counters maintained in a separate table |

**Always** maintain denormalized values with triggers, application logic, or async jobs. **Always** test that the cached value matches the source.

---

### Strategy 6: Replication

```
   ┌──────────────────┐
   │   Primary        │  ← writes go here
   │   (writes)       │
   └────────┬─────────┘
            │ async stream
            ▼
   ┌──────────────────┐  ┌──────────────────┐
   │   Replica 1      │  │   Replica 2      │  ← reads served from here
   │   (reads)        │  │   (reads)        │
   └──────────────────┘  └──────────────────┘
```

Replicas serve reads, freeing the primary for writes. Adds lag (usually <1 second, but watch it). Use replicas for:

- Read-heavy query patterns
- Analytics queries that would slow the primary
- Geographic distribution (replica in each region)
- High availability (promote replica if primary fails)

---

### Strategy 7: Database locking and concurrency

| Technique | When to use |
|---|---|
| **Pessimistic locking** | High-contention writes; you cannot afford the work to be wasted |
| **Optimistic locking** (version columns) | Low-contention writes; detect conflicts at update time |
| **Row-level locking** | Default in Postgres; multiple writers can update different rows |
| **Table-level locking** | DDL operations; schema migrations |
| **Advisory locks** | Application-level coordination (e.g., "only one cron job runs at a time") |

**Common antipattern:** long-running transactions holding row locks and blocking other writes. Keep transactions as short as possible.

---

### Strategy 8: Caching layer

Add a cache in front of the database for read-heavy, slowly-changing data.

```
   App → Cache (Redis) → [if miss] → Database → [set cache]
```

**Cache patterns:**

- **Cache-aside** — app reads from cache, falls back to DB, populates cache
- **Read-through** — cache itself reads from DB on miss
- **Write-through** — writes go through cache to DB
- **Write-behind** — writes go to cache, async-flush to DB

**Common cache pitfalls:**

- Stale data — set appropriate TTLs
- Cache stampede — many requests miss at once; use locking or stale-while-revalidate
- Cache invalidation — the famous "hard problem"

---

## Build It / In Depth

### The optimization order

When a database is slow, work through these in order. Stop when performance is acceptable.

```
   1. MEASURE first
      - What query is slow? (pg_stat_statements, slow query log)
      - Is it CPU-bound, I/O-bound, or lock-bound?
      - Is it cache-friendly or constantly missing?

   2. ADD INDEXES
      - For the slow query's WHERE / JOIN / ORDER BY columns
      - Re-run the query, confirm improvement
      - Time: hours, cost: zero

   3. REWRITE QUERIES
      - Look for anti-patterns (SELECT *, leading wildcards, etc.)
      - Try alternative formulations
      - Time: hours, cost: zero

   4. TUNE CONFIGURATION
      - Increase shared_buffers if cache hit rate is low
      - Increase work_mem if sorts spill to disk
      - Run ANALYZE if statistics are stale
      - Time: hours, cost: zero

   5. ADJUST SCHEMA
      - Add or remove indexes
      - Partition large tables
      - Denormalize hot paths
      - Time: days, cost: zero to medium (depending on migration)

   6. SCALE HARDWARE
      - Faster disks (NVMe SSD)
      - More RAM
      - More CPU
      - Time: days, cost: hundreds to thousands per month

   7. ADD CACHING
      - Redis or Memcached for hot reads
      - Cache-aside pattern
      - Time: days, cost: low (Redis is cheap)

   8. ADD REPLICATION
      - Read replicas for read-heavy workloads
      - Time: days, cost: medium (each replica is a server)

   9. SHARD
      - Last resort. Only when single-node capacity is exhausted.
      - Time: weeks to months, cost: high (architectural complexity)
```

**Skip steps and they come back to bite you.** Adding a cache before fixing a missing index means the cache fills with stale wrong results.

---

### Common diagnostic queries

```sql
-- What's running right now?
SELECT pid, now() - query_start AS duration, state, query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC;

-- What queries are slow on average?
SELECT calls, round(mean_exec_time::numeric, 1) AS ms, query
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 20;

-- What's the cache hit rate?
SELECT
  sum(heap_blks_read) AS heap_read,
  sum(heap_blks_hit)  AS heap_hit,
  round(100.0 * sum(heap_blks_hit) /
        NULLIF(sum(heap_blks_hit) + sum(heap_blks_read), 0), 2) AS hit_pct
FROM pg_statio_user_tables;

-- Which tables are bloated?
SELECT schemaname, relname,
       pg_size_pretty(pg_total_relation_size(relid)) AS total,
       pg_size_pretty(pg_relation_size(relid)) AS table,
       pg_size_pretty(pg_indexes_size(relid)) AS indexes,
       n_live_tup, n_dead_tup,
       round(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 1) AS dead_pct
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

---

### The settings that matter most

For a typical Postgres production server:

```ini
# Memory (most important)
shared_buffers = 25% of RAM        # 4 GB on 16 GB
effective_cache_size = 70% of RAM  # planner uses this for cost estimates
work_mem = 64MB                    # per sort/hash; watch connections × work_mem
maintenance_work_mem = 512MB       # for VACUUM, CREATE INDEX

# Parallelism
max_worker_processes = 8
max_parallel_workers_per_gather = 4
max_parallel_workers = 8

# WAL and checkpoints
wal_level = replica
synchronous_commit = on
checkpoint_timeout = 15min
max_wal_size = 4GB

# Planner cost model
random_page_cost = 1.1    # for SSD storage (default 4.0 is for HDD)
effective_io_concurrency = 200  # for SSD
```

Most other settings can stay at defaults. These have the biggest impact per minute spent.

---

## Use It

### Quick reference

| Symptom | Likely fix |
|---|---|
| Slow SELECT with WHERE | Add index on the column |
| Slow JOIN | Add index on the JOIN columns |
| Slow aggregate | Increase work_mem; consider materialized view |
| Slow disk I/O | Move to SSD; increase shared_buffers |
| Lock contention | Shorten transactions; lower isolation |
| Slow writes | Fewer indexes; batch writes; faster disks |
| Bloated tables | Tune autovacuum; manual VACUUM FULL if needed |
| Stale statistics | Run ANALYZE; tune autovacuum_analyze_scale_factor |
| Out of connections | Use PgBouncer; raise max_connections cautiously |
| Slow queries after data growth | Re-evaluate indexes; the right index yesterday may not be right today |

---

### Tools to know

| Tool | What it does |
|---|---|
| **`pg_stat_statements`** | Tracks query execution stats; must-have |
| **`pg_stat_activity`** | Current activity; what is running now |
| **`pg_stat_user_tables`** | Per-table stats: scans, tuples, vacuum |
| **`pg_stat_user_indexes`** | Per-index stats: usage, size |
| **`pg_statio_*`** | I/O stats; cache hit rates |
| **`EXPLAIN (ANALYZE, BUFFERS)`** | Per-node timing and I/O for a specific query |
| **`pg_locks`** | Current locks held |
| **`pg_stat_replication`** | Replication lag and state |
| **`auto_explain`** | Auto-EXPLAIN slow queries to a log |

---

## Common Pitfalls

- **Skipping the measurement step.** Tuning without measurement is guessing. Identify the slowest query first, then tune it.

- **Hardware before schema.** Throwing faster disks at a sequential-scan problem is expensive and doesn't address the underlying issue. Index first.

- **Caching before indexing.** A cache masks the symptom but does not fix the database. The slow query is still slow for cache misses.

- **Indexing everything.** Every index slows writes and uses memory. Index for the queries you actually run.

- **Not running ANALYZE.** Stale statistics lead to bad plans. After data changes, refresh them.

- **Ignoring transaction length.** Long-running transactions hold locks and bloat tables. Keep transactions short.

- **Premature sharding.** Sharding is the last resort, not the first. Single-node Postgres can handle far more load than most teams need.

- **No regression testing.** Tuning changes plans and behavior. Test that performance improved without breaking other queries.

---

## Exercises

1. **Easy** — List the four categories of database metrics. For each, name one specific metric and what healthy looks like.

2. **Medium** — Take a slow query you have encountered (or invent one). Walk through the nine-step optimization order. For each step, decide whether it applies and what specific change you would make.

3. **Hard** — Design a performance optimization plan for a database that has grown to 1 TB, handles 50k queries/second, and is starting to show p99 latency spikes during peak hours. Use `pg_stat_*` queries to identify what to investigate. Specify the changes you would make, in order, and the metrics you would track to confirm improvement.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Index | A way to make queries faster | A separate data structure mapping key values to row locations; B-Tree by default; trades write speed for read speed |
| Buffer cache | The cache | In-memory cache of data pages; sized by `shared_buffers` in Postgres; high hit rate (95%+) is the goal |
| Replication | Backing up | Streaming copies of the database used for read scaling, HA, and geographic distribution; introduces lag |
| Sharding | Partitioning | Splitting a large database across multiple nodes; last-resort scaling; adds cross-shard query complexity |
| Caching | A performance trick | Storing query results outside the database (usually Redis) to avoid hitting the DB at all; introduces staleness |
| Cache hit rate | A number | The fraction of reads served from cache vs. from disk; the single most important database performance metric |
| p99 latency | A SLA target | The 99th-percentile query latency; the experience of the slowest 1% of queries; what users feel as "the system is slow today" |
| EXPLAIN ANALYZE | A debug tool | The Postgres command that runs a query and shows per-node timing, row counts, and buffer usage; the most important diagnostic tool |

---

## Further Reading

- **Use The Index, Luke** — the canonical guide to SQL indexing: https://use-the-index-luke.com/
- **"PostgreSQL: Up and Running"** — practical guide to Postgres performance: https://www.oreilly.com/library/view/postgresql-up-and/9781098101908/
- **pgtune** — online tool that suggests Postgres config based on your hardware: https://pgtune.leopard.in.ua/
- **pg_stat_statements docs** — the must-have extension for query performance tracking: https://www.postgresql.org/docs/current/pgstatstatements.html
- **CMU 15-445 Lecture Videos** — Andy Pavlo's full course on database internals and performance: https://15445.courses.cs.cmu.edu/
- **Percona Database Performance Blog** — deep technical posts on MySQL, Postgres, and MongoDB performance: https://www.percona.com/blog/