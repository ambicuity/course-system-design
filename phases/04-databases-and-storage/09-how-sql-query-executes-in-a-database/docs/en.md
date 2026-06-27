# How SQL Query Executes In A Database?

> From `SELECT` to result set in four subsystems — the journey every query takes, and where it can go wrong.

**Type:** Learn
**Prerequisites:** Basic SQL, Postgres familiarity
**Time:** ~20 minutes

---

## The Problem

You write `SELECT * FROM users WHERE email = 'alex@example.com'`. The application receives the row. What actually happened between those two events? Most engineers can answer at the level of "the database parsed my query and returned a result." Few can answer at the level of "the parser built an AST, the rewriter applied views and rules, the planner chose a sequential scan because the table is small, the executor called the heap access method through the buffer manager, and the storage engine returned 0 rows because there is no index on email."

That gap matters when something goes wrong. A slow query that should be instant is usually slow because of one specific subsystem — and which one tells you what to fix. Knowing the four subsystems (transport, query processor, execution engine, storage engine) lets you localize problems and reason about query performance.

This lesson walks the path of a SQL query through every subsystem. By the end, you should be able to read an `EXPLAIN ANALYZE` output and know which subsystem produced each line.

---

## The Concept

### The four subsystems

```
   ┌──────────────────────────────────────────────────────────────┐
   │                                                              │
   │   1. TRANSPORT SUBSYSTEM                                     │
   │      - Connection management                                 │
   │      - Authentication & authorization                        │
   │      - Query routing                                         │
   │      ↓                                                      │
   │                                                              │
   │   2. QUERY PROCESSOR                                         │
   │      - Query parser (syntax → parse tree)                    │
   │      - Query rewriter (apply views, rules)                   │
   │      - Query optimizer (parse tree → execution plan)         │
   │      ↓                                                      │
   │                                                              │
   │   3. EXECUTION ENGINE                                        │
   │      - Walks the plan, step by step                          │
   │      - Calls storage engine for each step                    │
   │      - Combines results                                      │
   │      ↓                                                      │
   │                                                              │
   │   4. STORAGE ENGINE                                          │
   │      - Transaction manager                                   │
   │      - Lock manager                                          │
   │      - Buffer manager (in-memory pages)                      │
   │      - Recovery manager (WAL, crash recovery)                │
   │      - Disk access                                           │
   │                                                              │
   └──────────────────────────────────────────────────────────────┘
```

Every database engine has this four-layer split. Postgres calls them slightly differently (parser, analyzer, rewriter, planner, executor, storage). MySQL has similar layers. SQLite is simpler. Big distributed systems (Snowflake, BigQuery, ClickHouse) have more layers but the same shape.

---

### Step 1: Transport Subsystem

The transport subsystem is the front door. Its job is to accept connections, validate the caller, and pass the query along.

```
   Client app
        │
        │  TCP connection to port 5432
        ▼
   ┌─────────────────────────────────────┐
   │  TRANSPORT SUBSYSTEM                │
   │                                     │
   │  1. Accept TCP connection           │
   │  2. Read startup message            │
   │     (protocol version, parameters)  │
   │  3. Authenticate                    │
   │     - Check pg_hba.conf             │
   │     - Validate password / cert /    │
   │       Kerberos / LDAP               │
   │  4. Authorize                       │
   │     - Check role membership         │
   │     - Check database access         │
   │  5. If pooler (PgBouncer):          │
   │     - Acquire a backend from pool   │
   │  6. Forward query string            │
   └─────────────────────────────────────┘
```

**What can go wrong here:**

- Connection pool exhaustion — too many clients, not enough backends. Error: `FATAL: remaining connection slots are reserved`.
- Authentication failure — wrong password, expired cert. Error: `FATAL: password authentication failed`.
- Authorization failure — user does not have access to the database. Error: `FATAL: permission denied for database`.
- TLS handshake failure — cert mismatch. Error: `FATAL: SSL error`.

These errors all happen *before* the query is even parsed. You know you are in the transport subsystem if the error mentions connection, authentication, or permissions.

---

### Step 2: Query Processor

The query processor takes the string and produces an execution plan. Three substeps:

**2a. Parser — string → parse tree**

The parser takes the raw SQL string and checks it against the grammar of the SQL dialect. If the syntax is invalid, the parser rejects it here.

```
   Input:    SELECT * FROM users WHERE email = 'alex@example.com'

   Parser checks:
   - "SELECT" is a valid keyword
   - "*" is valid in this position
   - "FROM users" references a table
   - "WHERE email = '...'" is a valid expression
   - String is properly quoted
```

If valid, the parser produces a **parse tree** (an abstract syntax tree) representing the structure of the query.

**What can go wrong here:** syntax errors. `ERROR: syntax error at or near "FORM"`. Fix: write valid SQL.

**2b. Rewriter — apply views and rules**

The rewriter takes the parse tree and applies transformations:

- **View expansion** — `SELECT * FROM user_view` becomes the underlying query
- **Rule application** — `CREATE RULE` transformations
- **Subquery flattening** — in some cases

For most simple queries, the rewriter does little. It matters most for systems with many views or custom rules.

**2c. Optimizer (Planner) — parse tree → execution plan**

This is where the magic happens. The optimizer takes the parse tree and figures out the most efficient way to execute it.

```
   Parse tree:    "find rows in users where email = 'alex@example.com'"

   Possible plans:
   1. Seq Scan on users, filter on email
   2. Index Scan on idx_users_email, lookup matching rows
   3. Index-Only Scan on idx_users_email (if covering)

   The optimizer picks one based on:
   - Table size (pg_class.reltuples)
   - Index selectivity (most rows have unique emails → index wins)
   - I/O cost vs CPU cost
   - Statistics from ANALYZE
```

The output is an **execution plan** — a tree of operators like `Seq Scan`, `Index Scan`, `Hash Join`, `Sort`, `Aggregate`. The plan is what `EXPLAIN` shows you.

**What can go wrong here:**

- Stale statistics → bad plan → slow query. Fix: `ANALYZE table_name`.
- Missing index → optimizer forced to scan. Fix: add an index.
- Wrong cost model → optimizer underestimates. Fix: tune `random_page_cost`, `cpu_tuple_cost`.
- Complex query → planner timeout (`geqo_threshold`). Fix: rewrite the query or raise the threshold.

This is where most production slow-query issues originate. `EXPLAIN ANALYZE` shows you exactly which plan was chosen and how long each step took.

---

### Step 3: Execution Engine

The execution engine takes the plan and walks it, node by node, calling the storage engine for each operation.

```
   Plan:
   ┌─────────────────────────┐
   │  Limit                  │
   │    ↓                    │
   │  Sort (created_at DESC) │
   │    ↓                    │
   │  Index Scan             │
   │    (orders, customer_id)│
   └─────────────────────────┘

   Execution:
   1. Open Index Scan on orders with condition customer_id = 42
      → call storage engine to start the scan
   2. For each row from the scan:
      → call storage engine to read the heap tuple
   3. Pass each row to Sort node, buffer in memory
   4. When all rows read, sort and emit in order
   5. Take first 10 rows
   6. Return to client
```

**The execution engine coordinates; it does not access data itself.** All actual data movement happens through the storage engine. This separation lets the database swap storage engines (Postgres supports pluggable storage engines via tablespaces) without rewriting the query layer.

**What can go wrong here:**

- Slow operator (e.g., Sort spilling to disk) — the operator ran but inefficiently. Fix: increase `work_mem` or rewrite the query to avoid the sort.
- Nested loop with huge outer table — the operator ran but timed out. Fix: change join order or add an index.

---

### Step 4: Storage Engine

The storage engine is where the data lives. It manages:

| Component | What it does |
|---|---|
| **Buffer manager** | Caches data pages in memory; checks if a requested page is already loaded |
| **Transaction manager** | Tracks active transactions, enforces isolation (MVCC) |
| **Lock manager** | Acquires row, page, table, and advisory locks |
| **Recovery manager** | Writes and replays WAL; handles crash recovery |
| **Disk manager** | Reads pages from disk, writes dirty pages back |

A typical read operation looks like:

```
   Executor: "Get me row id=42 from users"
        │
        ▼
   Storage Engine:
   1. Buffer manager: is the page containing row 42 in memory?
      YES → return it directly (cache hit, ~microseconds)
      NO  → load from disk (cache miss, ~milliseconds), update buffer
   2. Lock manager: acquire a row-level read lock (or none, depending on isolation)
   3. Transaction manager: is this row visible to my snapshot?
      YES → return it to executor
      NO  → return "no such row"
```

A typical write operation:

```
   Executor: "Update users SET name = 'Bob' WHERE id = 42"
        │
        ▼
   Storage Engine:
   1. Buffer manager: load the page containing row 42
   2. Lock manager: acquire row-level write lock
   3. Transaction manager: assign xmin to new tuple version
   4. Modify the tuple in the buffer
   5. Mark buffer dirty
   6. WAL manager: append WAL record describing the change
   7. WAL writer: flush WAL to disk (durability point)
   8. Return to executor
```

**What can go wrong here:**

- Buffer cache too small → constant disk reads → slow queries. Fix: increase `shared_buffers`.
- WAL flushing bottleneck → writes stall on commit. Fix: faster disks, batching, or `synchronous_commit = off` (with risk).
- Lock contention → queries block each other. Fix: lower isolation, shorter transactions, or row-level locking.
- Disk I/O saturation → everything slows down. Fix: faster storage (NVMe SSDs).

---

### The journey of a slow query

A slow query almost always fails in one specific subsystem. Identifying which one tells you what to fix.

```
   Symptom                          Likely subsystem    What to do
   ───────────────────────────────  ──────────────────  ──────────────────────
   Connection refused              Transport           Check PgBouncer, listen address
   "permission denied"             Transport           Fix role grants
   Syntax error                     Parser              Fix the SQL
   Slow on small tables             Optimizer (stats)   Run ANALYZE
   Slow on filtered queries         Optimizer (no idx)  Add an index
   Slow on JOIN                     Optimizer (order)   Tune planner cost constants
   Sort spills to disk              Execution           Increase work_mem
   Constant disk I/O                Storage             Increase shared_buffers, get SSD
   Lock waits                       Storage             Shorten transactions, lower isolation
   Autovacuum lag                   Storage             Tune autovacuum per table
```

---

## Build It / In Depth

### A query, dissected

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT)
SELECT u.id, u.name, COUNT(o.id) AS order_count
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE u.created_at > NOW() - INTERVAL '30 days'
GROUP BY u.id, u.name
HAVING COUNT(o.id) > 5
ORDER BY order_count DESC
LIMIT 20;
```

A typical output:

```
   Limit  (cost=1234.56..1240.78 rows=20 width=48) (actual time=45.2..45.3 rows=20 loops=1)
     Buffers: shared hit=842
     ->  Sort  (cost=1234.56..1235.10 rows=215 width=48) (actual time=45.1..45.2 rows=20 loops=1)
           Sort Key: (count(o.id)) DESC
           Sort Method: top-N heapsort  Memory: 27kB
           Buffers: shared hit=842
           ->  HashAggregate  (cost=1200.34..1230.10 rows=215 width=48) (actual time=44.5..44.9 rows=215 loops=1)
                 Group Key: u.id, u.name
                 Buffers: shared hit=842
                 ->  Hash Right Join  (cost=920.45..1180.23 rows=3000 width=44) (actual time=30.1..42.8 rows=215 loops=1)
                       Hash Cond: (o.user_id = u.id)
                       Buffers: shared hit=842
                       ->  Seq Scan on orders o  (cost=0.00..200.00 rows=10000 width=8) (actual time=0.01..2.1 rows=10000 loops=1)
                             Buffers: shared hit=120
                       ->  Hash  (cost=900.00..900.00 rows=1617 width=36) (actual time=27.5..27.5 rows=1617 loops=1)
                             Buckets: 2048  Batches: 1  Memory Usage: 95kB
                             Buffers: shared hit=722
                             ->  Seq Scan on users u  (cost=0.00..900.00 rows=1617 width=36) (actual time=0.02..26.1 rows=1617 loops=1)
                                   Filter: (created_at > (now() - '30 days'::interval))
                                   Rows Removed by Filter: 5000
                                   Buffers: shared hit=722
   Planning Time: 0.8 ms
   Execution Time: 45.4 ms
```

Walk through it:

| Line | Subsystem | Insight |
|---|---|---|
| `Limit (actual time=45.2..45.3)` | Execution engine | 20 rows returned; took 45ms |
| `Sort` | Execution engine | Top-N heapsort, 27kB memory (didn't spill) |
| `HashAggregate` | Execution engine | Grouped by id, name; 215 groups |
| `Hash Right Join` | Execution engine | Right join because of LEFT JOIN semantics; 215 rows after join |
| `Seq Scan on orders` | Storage engine | Full table scan of orders (10k rows) — could be indexed |
| `Hash` | Execution engine | Built hash table on 1617 users |
| `Seq Scan on users` | Storage engine | Full scan, filtered 5000 rows out — could be indexed on `created_at` |
| `Planning Time: 0.8 ms` | Optimizer | Query was parsed and planned in <1ms — not the bottleneck |
| `Execution Time: 45.4 ms` | End-to-end | Total time, dominated by the two Seq Scans |

**Diagnosis:** the slow part is the two sequential scans. **Fix:** add `idx_users_created_at` and `idx_orders_user_id`. The next execution will use index scans and probably drop from 45ms to under 5ms.

---

### Reading time estimates

Every plan node has two time numbers: `cost` (estimated) and `actual time` (measured).

```
   Seq Scan on users  (cost=0.00..900.00 rows=1617 width=36)
                     (actual time=0.02..26.1 rows=1617 loops=1)
```

- `cost=0.00..900.00` — estimated cost in arbitrary units (start cost .. total cost)
- `actual time=0.02..26.1` — measured time in milliseconds (time to first row .. time to last row)
- `rows=1617` — both estimate and actual match here (good)

If estimate and actual diverge by 10× or more, the planner's statistics are stale. Run `ANALYZE users`.

---

## Use It

### When to suspect each subsystem

| Symptom | First subsystem to investigate |
|---|---|
| Connection failures, auth errors | Transport |
| Queries fail with syntax error | Parser |
| Plan looks wrong (Seq Scan when index should be used) | Optimizer (run ANALYZE) |
| Query uses a different plan than yesterday | Optimizer (statistics drift) |
| Slow operator (Sort, HashAggregate with high memory) | Execution engine (work_mem) |
| High disk I/O, low cache hit rate | Storage engine (buffer cache) |
| Lock waits, deadlocks | Storage engine (lock manager) |
| Replication lag | Storage engine (WAL apply lag) |

---

### The diagnostic checklist

When a query is slow:

```
   1. Run EXPLAIN (ANALYZE, BUFFERS) on it.
   2. Identify the slowest node (highest actual time).
   3. Classify the node:
      - Seq Scan? Index missing or table small.
      - Sort / HashAggregate spilling? work_mem too low.
      - Nested Loop with huge outer? Join order is wrong.
      - Bitmap Heap Scan with high buffers read? Cache miss; check shared_buffers.
   4. Compare estimated vs actual rows.
      - 10×+ off? Run ANALYZE on the involved tables.
   5. Apply the fix.
   6. Re-run EXPLAIN to confirm the plan changed and time dropped.
```

---

## Common Pitfalls

- **Confusing the plan with the actual execution.** `EXPLAIN` (without `ANALYZE`) only estimates. Always use `EXPLAIN (ANALYZE, BUFFERS)` for real numbers.

- **Adding indexes without checking the plan first.** The slow part might be a sort, not a scan. Indexes do not fix sort spills.

- **Ignoring BUFFERS output.** A plan that hits shared buffers 1000 times is much better than one that reads 1000 pages from disk. The plan nodes look identical without the buffer counts.

- **Not running ANALYZE.** The optimizer's plan is only as good as its statistics. After large data changes, run `ANALYZE` to refresh them.

- **Tuning the wrong subsystem.** Increasing `work_mem` does not help a query that is bottlenecked on disk I/O. Identify the bottleneck first.

- **Trusting the first plan you see.** Sometimes the planner picks a terrible plan for a specific query. Test alternatives with hints (or rewrite the query) before assuming the planner is always right.

---

## Exercises

1. **Easy** — List the four subsystems in query execution. For each, describe its job in one sentence and one symptom of failure.

2. **Medium** — Run `EXPLAIN (ANALYZE, BUFFERS)` on a real query in your database. Identify the slowest node. Classify which subsystem produced it (parser, optimizer, executor, storage). Propose a fix.

3. **Hard** — You are investigating a production slow-query report. The same query runs in 50ms in staging and 5 seconds in production, with identical data sizes. Walk through each subsystem and list the possible reasons for the difference. What would you check first?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Transport subsystem | The connection | The layer that accepts connections, authenticates callers, authorizes database access, and forwards queries |
| Parser | The SQL checker | The component that converts a query string into a parse tree (AST); rejects syntax errors |
| Optimizer | The smart part | The component that chooses the execution plan — which index, which join order, which sort strategy; depends on table statistics |
| Execution engine | The runner | The component that walks the plan and calls the storage engine for each step; coordinates but does not access data directly |
| Storage engine | The disk | The component that manages buffers, locks, transactions, and WAL; where data physically lives |
| Execution plan | The query | A tree of operators (Seq Scan, Index Scan, Hash Join, Sort, Aggregate, Limit) that describes how the query will be executed |
| Parse tree | The query | An abstract syntax tree representing the structure of the query; output of the parser, input to the optimizer |
| EXPLAIN ANALYZE | A debug tool | The command that runs the actual query and reports per-node timing, row counts, and buffer usage; the most important diagnostic for slow queries |

---

## Further Reading

- **"The Internals of PostgreSQL"** — a free deep dive into each subsystem: https://www.interdb.jp/pg/
- **Use The Index, Luke** — a guide to indexes and query performance: https://use-the-index-luke.com/
- **PostgreSQL Documentation — Performance Tips** — the official guide: https://www.postgresql.org/docs/current/performance-tips.html
- **pg_explain Visualizer** — turns EXPLAIN output into clear diagrams: https://tatiyants.com/pev/
- **"SQL Performance Explained"** — Markus Winand's book on the physics of query performance: https://sql-performance-explained.com/