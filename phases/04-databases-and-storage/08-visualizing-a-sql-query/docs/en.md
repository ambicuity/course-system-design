# Visualizing a SQL query

> SQL is declarative — you say *what* you want; the database decides *how* to get it.

**Type:** Learn
**Prerequisites:** Relational databases, Indexes, Query optimization basics
**Time:** ~25 minutes

---

## The Problem

You write a query that returns the right data on a small test table, deploy it to production, and watch your p99 latency spike to 8 seconds. You add an index, the problem mostly goes away — but you don't actually know *why*. You're flying blind.

Or consider a more subtle failure: a query with three JOINs runs fine for two years, then degrades over six months as the data grows. Nobody changed the schema. Nobody changed the query. Something inside the database made a different choice, and you have no visibility into what changed or why.

Without a mental model of how a database physically executes a SQL statement, tuning becomes guesswork. You can't read an EXPLAIN plan, you can't reason about when an index will or won't be used, and you can't predict how a query will scale. This lesson gives you the x-ray vision to look inside the execution engine.

---

## The Concept

### The Four Stages of Query Execution

A SQL statement travels through four distinct stages before a single row is returned to the client.

```
  SQL Text
     │
     ▼
┌─────────────┐
│   Parser    │  Tokenize + validate syntax → parse tree
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│  Semantic Analyzer  │  Resolve names, check types → logical plan (relational algebra)
└────────┬────────────┘
         │
         ▼
┌───────────────────────────────────────┐
│           Query Optimizer             │
│  - Enumerate candidate physical plans │
│  - Estimate row counts (statistics)   │
│  - Assign costs (I/O + CPU)           │
│  - Choose lowest-cost plan            │
└───────────────────┬───────────────────┘
                    │
                    ▼
           ┌────────────────┐
           │ Execution Engine│  Execute physical plan, stream rows to client
           └────────────────┘
```

### Stage 1 — Parsing

The SQL text is tokenized and parsed into a **parse tree** — a tree structure that mirrors the grammatical structure of the statement. At this stage the database only checks *syntax*: balanced parentheses, valid keywords, correct clause ordering. It knows nothing about whether the tables or columns you referenced actually exist.

### Stage 2 — Semantic Analysis (Binder / Resolver)

The parse tree is bound to the catalog (the database's internal metadata). Column names are resolved to their owning tables, type compatibility is checked (you can't compare `VARCHAR` to `INTEGER` without a cast), and ambiguous references are flagged. The output is a **logical plan** — an algebraic expression using relational operators: σ (select/filter), π (project), ⋈ (join), γ (aggregate).

A logical plan for:

```sql
SELECT u.name, COUNT(o.id)
FROM   users u
JOIN   orders o ON o.user_id = u.id
WHERE  u.country = 'US'
GROUP  BY u.name;
```

looks roughly like:

```
γ (GROUP BY u.name, COUNT)
└── σ (u.country = 'US')
    └── ⋈ (u.id = o.user_id)
        ├── users
        └── orders
```

### Stage 3 — Query Optimization

This is where the magic (and most of the complexity) lives. The optimizer takes the logical plan and searches for the cheapest equivalent **physical plan**. It has two jobs:

**a) Logical rewrites (rule-based)**  
Transformations that are *always* correct regardless of data:
- Push filters down below JOINs (predicate pushdown) — filter early, carry fewer rows
- Eliminate redundant projections
- Merge cascaded selections

**b) Physical plan selection (cost-based)**  
For each logical operator, there are multiple physical implementations. The optimizer uses *statistics* (row counts, histogram of value distributions, null fractions) to estimate cardinality at each step, then assigns I/O and CPU costs.

| Logical Op | Physical Alternatives |
|---|---|
| Scan | Sequential scan, Index scan, Index-only scan, Bitmap scan |
| Filter | Applied during scan or as a separate filter node |
| Join | Nested loop join, Hash join, Merge join, Index nested loop |
| Aggregate | Sort-then-aggregate, Hash aggregate |
| Sort | External merge sort, Top-N heap sort |

The optimizer evaluates combinations (especially join order, which grows as N! for N tables) and picks the plan with the lowest estimated total cost. Crucially: **the optimizer optimizes for its estimate, not reality**. Stale statistics or skewed data can make it choose badly.

### Stage 4 — Execution

The physical plan is a **pipeline** (or sometimes a pipeline with blocking operators like sorts). Rows flow from leaf nodes (scans) upward through operator nodes. Many modern databases use **vectorized execution**: instead of processing one row at a time, each operator works on a batch of ~1000 rows to amortize function-call overhead and improve CPU cache utilization.

```
Output
  │
  ▼ HashAggregate (group by u.name)
  │
  ▼ Hash Join (u.id = o.user_id)
 / \
/   \
SeqScan          IndexScan
users            orders
WHERE country='US'  (via idx_orders_user_id)
```

---

## Build It / In Depth

### Reading an EXPLAIN Plan (PostgreSQL)

`EXPLAIN` shows the physical plan the optimizer chose without executing the query. `EXPLAIN ANALYZE` actually runs it and shows real timings alongside estimates.

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT u.name, COUNT(o.id)
FROM   users u
JOIN   orders o ON o.user_id = u.id
WHERE  u.country = 'US'
GROUP  BY u.name;
```

Sample output (annotated):

```
HashAggregate  (cost=4321.50..4521.50 rows=20000 width=36)
               (actual time=93.211..97.340 rows=18432 loops=1)
  Group Key: u.name
  Batches: 1  Memory Usage: 4113kB
  ->  Hash Join  (cost=1250.00..4021.50 rows=120000 width=28)
                 (actual time=12.834..77.901 rows=121044 loops=1)
        Hash Cond: (o.user_id = u.id)
        Buffers: shared hit=3210 read=740
        ->  Seq Scan on orders o  (cost=0.00..2100.00 rows=200000 width=8)
                                  (actual time=0.017..31.200 rows=200000 loops=1)
        ->  Hash  (cost=937.50..937.50 rows=25000 width=28)
                  (actual time=12.601..12.602 rows=25000 loops=1)
              Buckets: 32768  Batches: 1  Memory Usage: 1624kB
              ->  Seq Scan on users u  (cost=0.00..937.50 rows=25000 width=28)
                                       (actual time=0.009..6.832 rows=25000 loops=1)
                    Filter: ((country)::text = 'US'::text)
                    Rows Removed by Filter: 75000

Planning Time: 1.432 ms
Execution Time: 98.214 ms
```

**How to read the cost tuple `(cost=start..total)`:**
- `start` — cost before the first row can be returned (e.g., a sort must read everything first)
- `total` — cost to return all rows
- Units are arbitrary but consistent: 1 unit ≈ 1 sequential page I/O

**Key signals to look for:**

| Signal | What it means |
|---|---|
| `Seq Scan` on a large table with a filter | Missing index or optimizer decided index isn't worth it |
| `rows=` estimate far from `actual rows=` | Stale statistics; run `ANALYZE` |
| `loops=N` with N > 1 | This node ran N times (inside a nested loop) |
| `Buffers: read=N` (high) | Data not in cache; I/O bound |
| `Batches: N > 1` on a Hash Join | Hash table spilled to disk; insufficient `work_mem` |

### Predicate Pushdown — Before and After

Consider filtering after a join (what you'd naively write) vs. filtering before:

```
BEFORE pushdown:           AFTER pushdown (optimizer rewrites):

σ (country='US')           ⋈
└── ⋈                     / \
    ├── users              σ (country='US')   orders
    └── orders             └── users
```

After pushdown, the join handles 25 000 rows instead of 100 000. The optimizer applies this automatically, but you need to understand it to know *why* writing the filter in the WHERE clause is equivalent to writing it in the subquery — and why sometimes it isn't (e.g., with OUTER JOINs).

### Join Algorithm Selection

```
Table sizes:        users = 25 000 rows     orders = 200 000 rows

Nested Loop:  25 000 × 200 000 = 5 billion comparisons   ← terrible
Hash Join:    build hash of users (smaller side),
              probe with each orders row
              Cost ≈ O(users + orders)                    ← chosen

Merge Join:   both sides must be sorted on join key
              Good when both sides already have an index-ordered scan
```

The optimizer knows these formulas and picks accordingly. If you add `ORDER BY u.id` to the query and there's an index on `users.id`, the optimizer might switch from Hash Join to Merge Join — same result, different plan.

---

## Use It

### Tools Across Databases

| Database | EXPLAIN variant | Notable extras |
|---|---|---|
| PostgreSQL | `EXPLAIN (ANALYZE, BUFFERS)` | `auto_explain` extension, `pg_stat_statements` |
| MySQL / MariaDB | `EXPLAIN`, `EXPLAIN FORMAT=JSON` | `EXPLAIN ANALYZE` (MySQL 8.0+) |
| SQLite | `EXPLAIN QUERY PLAN` | Minimal output; good for index verification |
| SQL Server | Execution plan in SSMS, `SET STATISTICS IO ON` | Graphical plan with cost % per node |
| BigQuery | `EXPLAIN` in query editor | Shows shuffle bytes between stages |
| Snowflake | Query Profile UI | Partition pruning stats, spill-to-disk info |

### Query Visualization Tools

- **pgAdmin / DBeaver** — renders PostgreSQL EXPLAIN output as a graphical tree; node width encodes relative cost.
- **explain.dalibo.com** — paste PostgreSQL EXPLAIN JSON, get an interactive diagram.
- **pt-visual-explain** (Percona Toolkit) — command-line MySQL plan visualizer.
- **SQL Server Management Studio** — built-in graphical execution plan with hover-over statistics.

### When the Optimizer Gets It Wrong

Real triggers that degrade plan quality:

1. **Stale statistics** — run `ANALYZE` (PostgreSQL) or `UPDATE STATISTICS` (SQL Server) after large bulk loads.
2. **Parameter sniffing / plan caching** — SQL Server and MySQL cache plans; a plan compiled for an unusual parameter value gets reused for typical values. Use query hints or `OPTION (RECOMPILE)` sparingly.
3. **Extremely skewed data** — a column with 99% NULLs needs a partial index and histogram buckets biased to the non-null values. Use extended statistics in PostgreSQL 10+.
4. **Too many joins** — PostgreSQL's optimizer switches to a genetic algorithm (GEQO) above 8 tables; plans may not be globally optimal. Consider rewriting as CTEs with `MATERIALIZED` hints to force intermediate materialization.

---

## Common Pitfalls

- **Trusting estimates instead of actuals.** `EXPLAIN` without `ANALYZE` shows only estimates. A plan that looks cheap can be catastrophically wrong if the estimates are off. Always run `EXPLAIN ANALYZE` in a development environment with representative data.

- **Ignoring the `loops` multiplier.** A node might show `actual time=0.050..0.052 ms` but have `loops=50000`. Total actual time is 2 600 ms — this is a hidden nested-loop killer. Always multiply `actual time` by `loops` to get the true contribution.

- **Adding indexes without re-checking the plan.** An index being *present* doesn't mean the optimizer will *use* it. Low-selectivity columns (e.g., a boolean `is_active` that's true for 95% of rows), implicit type casts, or function wrapping (`WHERE LOWER(email) = ...`) can prevent index usage. Verify with EXPLAIN after every schema change.

- **Assuming `SELECT *` is harmless.** Projecting all columns prevents Index-Only Scans (which can serve the query purely from the index without touching the heap). It also bloats the result set transferred over the network. Project only what you need.

- **Confusing query cost with query time.** Cost units are not milliseconds. A plan with cost=100 000 might run in 20 ms if everything is in the buffer cache; a plan with cost=5 000 might take 2 seconds due to disk I/O. `BUFFERS` output and `actual time` are what actually matter.

---

## Exercises

1. **Easy** — Run `EXPLAIN (ANALYZE, BUFFERS)` on a query against a table with at least 10 000 rows. Identify the scan type used, the estimated vs. actual row count, and whether any data came from disk (`Buffers: read > 0`). Add an index on the filtered column and re-run. Document the plan change.

2. **Medium** — Write a query that joins three tables. Examine the join order the optimizer chose. Force a different join order using `SET join_collapse_limit = 1` (PostgreSQL) or `STRAIGHT_JOIN` (MySQL) and compare costs and actual runtimes. Explain why the optimizer's original choice was better or worse.

3. **Hard** — Identify a slow query in a real or sample database (e.g., the pgbench or Northwind dataset). Run `EXPLAIN ANALYZE` and find the worst-contributing node by multiplying `actual time × loops`. Diagnose whether the problem is a missing index, stale statistics, or a suboptimal join algorithm, then fix it. Verify the fix with a second EXPLAIN ANALYZE run and quantify the improvement.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Parse tree | The final representation used to run the query | An intermediate syntax tree used only for grammar validation; discarded before optimization |
| Logical plan | The same as the execution plan | An algebraic expression of the query in relational operators — no physical implementation decisions made yet |
| Physical plan | What you see when you write the SQL | The actual tree of physical operators (hash join, index scan, etc.) the engine will execute |
| Cost | Time in milliseconds | An abstract, unitless number used by the optimizer; not a wall-clock prediction |
| Cardinality | Table size | The number of rows *after filtering* at a given plan node — the key input to cost estimation |
| Predicate pushdown | A manual optimization you apply | An automatic logical rewrite that moves filters earlier in the plan to reduce rows flowing through joins |
| Statistics | Row count metadata | Histograms, most-common values, null fractions, and correlation coefficients stored in the catalog and used by the cost model |

---

## Further Reading

- [PostgreSQL Documentation — Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — the canonical reference for reading PostgreSQL execution plans, including all EXPLAIN options and output fields.
- [Use The Index, Luke](https://use-the-index-luke.com/) — free book covering indexes, execution plans, and query optimization across PostgreSQL, MySQL, Oracle, and SQL Server; exceptional depth on why indexes are or aren't used.
- [explain.dalibo.com](https://explain.dalibo.com/) — paste any PostgreSQL EXPLAIN JSON output and get an interactive, annotated visualization.
- [MySQL 8.0 EXPLAIN Format Reference](https://dev.mysql.com/doc/refman/8.0/en/explain-output.html) — official documentation for MySQL's EXPLAIN output columns and values.
- [CMU 15-445 Lecture Notes — Query Execution](https://15445.courses.cs.cmu.edu/fall2023/notes/11-execution.pdf) — graduate-level database course notes on iterator models, vectorized execution, and parallel query processing.
