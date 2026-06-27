# PostgreSQL 101: The Everything Database

> Forty years old, still the default — a tour of the architecture that powers most of the web.

**Type:** Learn
**Prerequisites:** Basic SQL, command-line comfort
**Time:** ~25 minutes

---

## The Problem

PostgreSQL has been called "the most loved database" by developers for over a decade. It is also, somehow, the database that most engineers use without really understanding. They write `SELECT` queries, add an index, ship the feature, and never look at the process model, the shared buffers, or the WAL writer.

That works for small apps. It stops working the moment you have real concurrency, real data volume, or a production incident. Then the questions change from "how do I write a query" to "why is this query slow," "why are connections exhausted," "why is replication lagging," "what is the autovacuum doing." Answering those questions requires understanding the architecture.

This lesson is a tour of PostgreSQL's internals — the process model, shared memory, background workers, and physical file layout. The goal is not to turn you into a Postgres contributor. The goal is to give you the vocabulary to read Postgres documentation, follow `pg_stat_*` views, and reason about production behavior.

---

## The Concept

### The high-level architecture

```
                         ┌─────────────────────┐
                         │   Client processes  │
                         │   (psql, app, etc.) │
                         └──────────┬──────────┘
                                    │ TCP (port 5432)
                                    ▼
                         ┌─────────────────────┐
                         │     Postmaster      │
                         │  (supervisor proc)  │
                         └──────────┬──────────┘
                                    │ forks
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
   │ Backend process │    │ Backend process │    │ Backend process │
   │  (client 1)     │    │  (client 2)     │    │  (client N)     │
   └────────┬────────┘    └────────┬────────┘    └────────┬────────┘
            │                      │                      │
            └──────────────────────┼──────────────────────┘
                                   ▼
                         ┌─────────────────────┐
                         │   Shared memory     │
                         │  (buffers, locks,   │
                         │   WAL, stats)       │
                         └──────────┬──────────┘
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                ┌─────────────────┐   ┌─────────────────┐
                │ Background      │   │ Physical files  │
                │ workers         │   │ (heap, WAL,    │
                │ (BG writer,     │   │  pg_xact, etc) │
                │  autovacuum,    │   └─────────────────┘
                │  WAL writer,    │
                │  checkpointer)  │
                └─────────────────┘
```

Three layers: **client processes**, **the postmaster and backend processes**, and **shared memory + background workers + physical files**. Every PostgreSQL deployment fits this pattern.

---

### The process model: one process per connection

PostgreSQL uses a **process-per-connection** model. Every client connection gets its own dedicated backend process. The postmaster (the main supervisor process) forks a new backend for each connection.

```
   Connection 1 ──► Backend process PID 1234
   Connection 2 ──► Backend process PID 1235
   Connection 3 ──► Backend process PID 1236
   ...
```

**Why this matters:**

- **Pros:** isolation. One bad query in one connection cannot corrupt another connection's state. Crashes are localized.
- **Cons:** each backend uses ~5–10 MB of memory just to exist. A thousand connections means a thousand processes. That is why connection pooling (PgBouncer, Pgpool) is essential at scale.

The default `max_connections` is 100. Production systems routinely run with 200–500 connections on a tuned server, or use pooling to multiplex thousands of client connections onto far fewer backends.

**Connection poolers (PgBouncer, Pgpool-II):**

```
   1000 client connections
            │
            ▼
   ┌─────────────────┐
   │   PgBouncer     │  multiplexes down to
   └────────┬────────┘
            │
            ▼
   20-50 backend processes (the real DB connections)
```

Pooling drops memory usage dramatically and is the first optimization to apply when connection counts climb.

---

### Shared memory: the heart of the system

All backends communicate through a region of shared memory. This is where the data caches, lock tables, and transaction state live.

```
   ┌─────────────────────────────────────────────────────────┐
   │                    SHARED MEMORY                         │
   │                                                         │
   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
   │  │ Shared       │  │ WAL          │  │ CLOG         │   │
   │  │ buffers      │  │ buffers      │  │ (commit log) │   │
   │  │              │  │              │  │              │   │
   │  │ (cached      │  │ (write-ahead │  │ (which txns  │   │
   │  │  data pages) │  │  log cache)  │  │  committed)  │   │
   │  └──────────────┘  └──────────────┘  └──────────────┘   │
   │                                                         │
   │  ┌──────────────┐  ┌──────────────┐                     │
   │  │ Temp         │  │ Lock         │                     │
   │  │ buffers      │  │ tables       │                     │
   │  └──────────────┘  └──────────────┘                     │
   └─────────────────────────────────────────────────────────┘
```

**Shared buffers** — the page cache for table and index data. When you read a row, the page (8 KB block) is loaded into shared buffers if not already there. When you write, the change goes to shared buffers first and is marked dirty. Sizing this is critical: too small means constant disk reads; too large leaves little memory for other things. The classic rule was 25% of RAM; modern Postgres (with the OS page cache) often does fine with less.

**WAL buffers** — write-ahead log in memory. Every change is written to WAL before being applied to data pages. WAL is the recovery mechanism: on crash, Postgres replays the WAL to bring the database to a consistent state.

**CLOG (commit log)** — a bitmap tracking which transactions committed and which aborted. Used for MVCC visibility checks.

**Lock tables** — shared and exclusive locks held by transactions.

---

### Background workers: the helpers

While backends serve client queries, a set of background workers handles continuous maintenance:

| Worker | What it does | Why it matters |
|---|---|---|
| **BG Writer** | Periodically writes dirty buffers to disk | Smooths out checkpoint spikes, improves crash recovery |
| **WAL Writer** | Flushes WAL buffers to disk | Ensures durability of committed transactions |
| **Autovacuum** | Removes dead tuples, updates statistics | Without it, tables bloat and queries slow down |
| **Checkpointer** | Flushes all dirty buffers at checkpoint time | Determines recovery time after a crash |
| **Stats Collector** | Gathers per-table and per-index statistics | Powers the query planner's cost estimates |
| **System Logger** | Writes log messages | The trail you read when things go wrong |
| **Archiver** | Copies completed WAL files to archive storage | Enables point-in-time recovery |
| **Replication launcher** | Manages replication slots and workers | For streaming replicas and logical replication |

**Autovacuum** deserves special attention. PostgreSQL uses **MVCC (Multi-Version Concurrency Control)** — every UPDATE creates a new row version and marks the old one as dead. Without autovacuum, dead tuples accumulate forever, tables bloat, indexes bloat, and queries slow down. The most common production performance issue in Postgres is autovacuum not keeping up.

```sql
-- Check autovacuum status
SELECT schemaname, relname, last_autovacuum, last_autoanalyze, n_dead_tup
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
```

---

### Physical files: what is on disk

```
   /var/lib/postgresql/data/
   ├── PG_VERSION              -- version marker
   ├── postgresql.conf          -- main config
   ├── pg_hba.conf              -- authentication rules
   ├── pg_ident.conf            -- user mapping
   ├── base/                    -- per-database directories
   │   └── 16384/               -- default database OID
   │       ├── 1247             -- heap data files
   │       ├── 1247.1           -- file fork (e.g., FSM, VM)
   │       └── ...
   ├── global/                  -- cluster-wide tables (pg_database, etc.)
   ├── pg_wal/                  -- write-ahead log files
   │   ├── 000000010000000000000001
   │   └── ...
   ├── pg_xact/                 -- commit log files
   ├── pg_multixact/            -- multi-transaction status
   ├── pg_subtrans/             -- subtransaction status
   ├── pg_stat/                 -- permanent stats files
   ├── pg_stat_tmp/             -- temp stats (in-memory mostly)
   ├── pg_notify/               -- LISTEN/NOTIFY status
   ├── pg_serial/               -- serializable conflict info
   ├── pg_snapshots/            -- exported snapshots
   ├── pg_logical/              -- logical replication state
   ├── pg_replslot/             -- replication slot state
   ├── pg_dynshmem/             -- dynamic shared memory
   ├── pg_notify/
   └── pg_snapshots/
```

**Key directories:**

- **`base/`** — the actual table and index data files, organized by database OID then file number. Each file is 1 GB max; large tables span multiple files (`.1`, `.2`, etc.).
- **`pg_wal/`** — write-ahead log files, 16 MB each by default. The recovery log.
- **`pg_xact/`** — commit log files. Tracks transaction status.
- **`pg_replslot/`** — replication slot state for streaming replication.

The WAL is the most operationally critical. Loss of WAL means loss of committed transactions. Backup strategies must include WAL archiving for point-in-time recovery.

---

### MVCC: why your queries see old data

PostgreSQL's MVCC model explains a lot of otherwise puzzling behavior:

- **Every UPDATE creates a new row version.** The old version is marked as dead but stays in the table until VACUUM removes it.
- **Every DELETE marks the row as dead.** Same story.
- **SELECT sees a consistent snapshot.** Even if another transaction commits mid-query, your SELECT ignores those changes.
- **No read locks.** Readers never block writers and writers never block readers. This is why Postgres scales well under mixed workloads.

```
   UPDATE users SET name = 'Bob' WHERE id = 42;

   Physical layout after the UPDATE:
   ┌──────────────────────────────────────────────────┐
   │  Tuple A: id=42, name='Alice', xmin=100, xmax=101 │  (dead, will be vacuumed)
   │  Tuple B: id=42, name='Bob',   xmin=101, xmax=∞  │  (live)
   └──────────────────────────────────────────────────┘

   Concurrent SELECT sees Tuple B.
   Other backends see whichever tuple is visible to their snapshot.
```

The `xmin` and `xmax` columns (hidden by default) record which transaction created and which (if any) "expired" each tuple. VACUUM removes tuples where no active transaction can see them.

---

### Write-ahead logging (WAL): the durability guarantee

Every change goes through this sequence:

```
   1. Transaction begins
   2. For each change:
      a. Write to WAL buffer in shared memory
      b. Modify data page in shared buffers (mark dirty)
   3. Transaction commits:
      a. WAL writer flushes WAL to disk  ← durability point
      b. Commit record appended to WAL
      c. Backend confirms commit to client
   4. BG writer / checkpointer eventually writes dirty data pages to disk
```

The commit point is when WAL hits disk. Even if the database crashes immediately after, the change survives because the WAL is on disk.

**Tuning WAL:**

- `wal_level` — replica, logical, minimal
- `synchronous_commit` — on (safe), off (faster, may lose last few transactions on crash)
- `fsync` — on (always), off (dangerous, only for testing)
- `checkpoint_timeout` — how often checkpoints happen
- `max_wal_size` — when to force a checkpoint

---

## Build It / In Depth

### A 60-second tour of a running Postgres instance

```bash
# 1. Connect to the database
psql -h localhost -U postgres

# 2. See what's running right now
SELECT pid, usename, application_name, state, query
FROM pg_stat_activity
WHERE state != 'idle';

# 3. Find the slowest queries
SELECT calls, mean_exec_time, query
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

# 4. See which tables need vacuuming
SELECT schemaname, relname, n_live_tup, n_dead_tup,
       ROUND(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 1) AS dead_pct
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 10;

# 5. Check index usage
SELECT schemaname, relname, indexrelname, idx_scan, idx_tup_read
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC
LIMIT 10;
```

These five queries answer the most common production questions: what is running, what is slow, what needs maintenance, what indexes are unused.

---

### Configuration priorities

The Postgres configuration file has 300+ settings. Most can be left at defaults. These are the ones that actually matter for production:

```ini
# Memory (most important)
shared_buffers = 4GB                # 25% of RAM is the classic rule
effective_cache_size = 12GB         # OS cache estimate, helps planner
work_mem = 64MB                     # per-operation sort/hash memory
maintenance_work_mem = 512MB        # for VACUUM, CREATE INDEX

# WAL and checkpoints
wal_level = replica
synchronous_commit = on             # safety; off only for non-critical loads
checkpoint_timeout = 15min
max_wal_size = 4GB
min_wal_size = 1GB

# Connections
max_connections = 200               # actual limit; use pooler for more

# Autovacuum (CRITICAL — do not disable)
autovacuum = on
autovacuum_max_workers = 4
autovacuum_naptime = 30s
```

For a full server: total RAM = sum of `shared_buffers` + `work_mem × max_connections × average active operations` + OS overhead. The connection-level work_mem is the trap — at 200 connections and 64 MB work_mem, you can use 12 GB just for sort memory in a worst case.

---

### Reading a Postgres EXPLAIN ANALYZE

The most important skill for production Postgres:

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM orders WHERE customer_id = 42 ORDER BY created_at DESC LIMIT 10;
```

```
   Limit  (cost=0.43..1.85 rows=10 width=120) (actual time=0.05..0.08 rows=10 loops=1)
     Buffers: shared hit=4
     ->  Index Scan using idx_orders_customer_created on orders
           (cost=0.43..1.85 rows=10 width=120) (actual time=0.05..0.07 rows=10 loops=1)
           Index Cond: (customer_id = 42)
   Planning Time: 0.15 ms
   Execution Time: 0.08 ms
```

What to look for:

| Symptom | What it means | What to do |
|---|---|---|
| `Seq Scan` on a large table | No usable index | Add an index on the WHERE column |
| `Sort` node with high cost | In-memory sort spilling to disk | Increase `work_mem` or add an index that provides order |
| `Nested Loop` with large outer | Slow join | Consider `Hash Join` or different join order |
| Estimated vs actual rows off by 10×+ | Stale statistics | Run `ANALYZE table_name` |
| `Buffers: shared read=10000` | Heavy disk I/O | Add indexes, increase `shared_buffers`, or warm the cache |
| `Execution Time: 5000 ms` | Something is wrong | Read the slowest node, fix that |

The single most useful production tool is `EXPLAIN (ANALYZE, BUFFERS)`. Run it on every slow query.

---

## Use It

### When PostgreSQL is the right choice

| Situation | Why Postgres fits |
|---|---|
| General OLTP application | Strong ACID, mature, ubiquitous |
| You need JSON + relational in one | JSONB is first-class in Postgres |
| You need full-text search | Built-in tsvector + GIN indexes |
| You need geospatial queries | PostGIS is the gold standard |
| You need vector search (RAG) | pgvector extension is production-ready |
| You need streaming replication + HA | Battle-tested, well-documented |
| Strict SQL compliance matters | Postgres is the most SQL-compliant open DB |

### When to consider alternatives

| Situation | Better choice |
|---|---|
| Pure OLAP / analytics at huge scale | ClickHouse, Snowflake, BigQuery, DuckDB |
| Sub-millisecond key-value lookups at millions/sec | Redis, Memcached, DynamoDB |
| Massive write throughput, eventual consistency OK | Cassandra, ScyllaDB, DynamoDB |
| Time-series data | TimescaleDB (still Postgres), InfluxDB, QuestDB |
| Graph relationships are the core | Neo4j, Memgraph |
| Embedded / edge | SQLite |

### Extensions worth knowing

| Extension | What it adds |
|---|---|
| **pg_stat_statements** | Tracks query execution stats (must-have) |
| **pgvector** | Vector similarity search for RAG |
| **PostGIS** | Geospatial queries and indexes |
| **pg_trgm** | Trigram-based fuzzy text matching |
| **pgCrypto** | Cryptographic functions |
| **pgAudit** | Detailed audit logging |
| **TimescaleDB** | Time-series optimizations |
| **pglogical** | Logical replication (row-level) |

---

## Common Pitfalls

- **Running without a connection pooler.** Thousands of client connections = thousands of backend processes = memory exhaustion. Use PgBouncer.

- **Disabling autovacuum.** Tables bloat, queries slow down, indexes rot. Always-on autovacuum is the default for a reason.

- **No `pg_stat_statements`.** Without it, you cannot find your slowest queries. Enable it on day one.

- **Work_mem too high.** At 200 connections with 64 MB work_mem, a complex query can use gigabytes. Tune per workload.

- **No backup of WAL.** Without WAL archiving, you cannot do point-in-time recovery. Backups without WAL are snapshots, not full backups.

- **Over-indexing.** Every index slows down writes and uses disk. Index for the queries you actually run, not the ones you might run.

- **Treating Postgres like MySQL.** The process model, MVCC, vacuum model, and JSON handling are all different. Patterns that work in one may not translate.

- **Ignoring replication lag.** A replica with hours of lag is a backup that cannot be promoted safely. Monitor lag.

---

## Exercises

1. **Easy** — Sketch the Postgres architecture with the postmaster, backends, shared memory, and background workers. Label each component's role in one sentence.

2. **Medium** — Run `EXPLAIN (ANALYZE, BUFFERS)` on three real queries in your database (or a sample one). Identify the slowest node in each. Propose a fix (index, query rewrite, work_mem increase) and explain why.

3. **Hard** — A production Postgres server is showing 80% CPU, high I/O wait, and slow queries during peak hours. Using the architecture from this lesson, walk through the diagnosis: which subsystems to check first, what `pg_stat_*` views to query, what configuration changes to consider, and how to verify the fix worked.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| PostgreSQL | A SQL database | A 40-year-old, actively maintained, SQL-compliant, extensible relational database; the default for most new applications |
| Postmaster | The database | The supervisor process that listens for connections and forks backends; not the database itself |
| Backend process | A connection | A dedicated OS process forked per client connection; ~5–10 MB of memory each; the unit of isolation in Postgres |
| MVCC | A concurrency feature | Multi-Version Concurrency Control — every UPDATE creates a new tuple version; readers never block writers; requires vacuuming to reclaim space |
| WAL | A log | Write-Ahead Log — every change is recorded here before being applied to data pages; the durability and recovery mechanism |
| Autovacuum | Cleanup | The background process that removes dead tuples and updates statistics; without it, every Postgres database bloats and slows down |
| Shared buffers | The cache | The in-memory cache of data pages shared across all backends; sized via `shared_buffers` config |
| EXPLAIN ANALYZE | A debugging tool | The most important production tool for understanding query performance; shows the actual execution plan with row counts, timings, and buffer usage |

---

## Further Reading

- **PostgreSQL Documentation — Architecture** — the canonical reference: https://www.postgresql.org/docs/current/tutorial-arch.html
- **"The Internals of PostgreSQL"** — a free, deep online book by Hironobu Suzuki: https://www.interdb.jp/pg/
- **pg_explain — Visual EXPLAIN** — a tool that turns EXPLAIN output into clear visualizations: https://tatiyants.com/pev/
- **PostgreSQL Configuration (PGTune)** — an online tool that suggests config values for your hardware: https://pgtune.leopard.in.ua/
- **Use The Index, Luke** — a guide to SQL indexing by Markus Winand: https://use-the-index-luke.com/
- **"PostgreSQL: Up and Running"** — Regina Obe and Leo Hsu's practical book: https://www.oreilly.com/library/view/postgresql-up-and/9781098101908/