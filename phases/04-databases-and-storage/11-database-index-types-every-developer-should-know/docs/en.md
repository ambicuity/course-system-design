# Database Index Types Every Developer Should Know

> The right index turns a full-table scan into a surgical pointer; the wrong index makes every write pay for reads you never do.

**Type:** Learn
**Prerequisites:** Relational Database Fundamentals, Storage Engines & How Databases Store Data, Query Execution Plans
**Time:** ~35 minutes

---

## The Problem

You ship a feature. Queries are fast in staging with 10 000 rows. Three months later, production has 50 million rows and the same query hangs for 12 seconds. You add an index and it drops to 8 ms. The data never changed — only the access path did.

But "add an index" is not a strategy. A B-Tree index on a status column with three possible values can make things *worse* by forcing the optimizer into a plan it then ignores. A composite index added in the wrong column order is functionally useless for half your queries. An index on a write-heavy table adds 20 ms of overhead to every insert while the read it was meant to speed up runs once a week.

Index design is one of the highest-leverage decisions in any system that touches a database. Understanding what each index type does under the hood — its internal structure, when the optimizer will actually use it, and what it costs — is the difference between a database that scales and one that becomes the bottleneck.

---

## The Concept

### What an Index Actually Is

An index is a **derived, redundant data structure** built from one or more columns of a table. It trades write overhead and storage for read speed. The database maintains the index automatically on insert, update, and delete. At query time, the optimizer inspects available indexes and estimates whether using one is cheaper than a full sequential scan.

The two fundamental questions for every index type:

1. **What data structure does it use?** (Determines what query shapes it accelerates.)
2. **Does it change the physical order of rows?** (Clustered vs. non-clustered.)

### Dense vs. Sparse Indexes

Before diving into named types, understand this foundational split:

```
Dense Index                         Sparse Index
─────────────────────────────       ────────────────────────────
One entry per row                   One entry per disk page / block

[key=1] → page 3, slot 0            [key=1]  → page 3
[key=2] → page 3, slot 1            [key=10] → page 4
[key=3] → page 3, slot 2            [key=20] → page 5
[key=4] → page 4, slot 0            ...
...
```

A dense index can locate any individual row without touching the table. A sparse index requires a secondary read into the data page but is far smaller on disk. Primary indexes are often implemented as sparse indexes because rows on a page are already sorted and the DB can scan within a page cheaply.

---

### Index Type Taxonomy

| Type | Structure | Clustered? | Best for |
|------|-----------|------------|----------|
| Primary | B-Tree (usually) | Can be either | Unique lookup by PK |
| Clustered | B-Tree | Yes — is the table | Range scans, ORDER BY |
| Secondary / Non-clustered | B-Tree | No | Arbitrary column lookup |
| Hash | Hash table | No | Exact-match equality |
| Composite | B-Tree over N cols | Either | Multi-column filters, covering |
| Covering | B-Tree (subset) | No | Read-only from index, no table fetch |
| Partial / Filtered | B-Tree (subset) | No | Narrow, high-selectivity predicates |
| Full-text | Inverted index | No | Keyword / phrase search |
| Bitmap | Bit arrays | No | Low-cardinality, analytics |
| Spatial (R-Tree) | R-Tree / GiST | No | Geo-coordinates, bounding boxes |

---

### 1. Primary Index

Automatically created when a PRIMARY KEY is defined. In most RDBMS (PostgreSQL, MySQL InnoDB, SQL Server), the primary index *is* the clustered index — the table rows are physically arranged in primary key order. The index structure maps key values to the physical location (page + slot) of each row.

In PostgreSQL, the "heap" stores rows in arbitrary insertion order and the primary index is a separate B-Tree structure — making PostgreSQL's primary index non-clustered by default. In MySQL InnoDB, the primary key always defines a clustered index.

### 2. Clustered Index

The clustered index defines the **physical sort order** of rows on disk. Because rows can only be sorted one way, there is at most one clustered index per table.

```
Clustered B-Tree (InnoDB PRIMARY KEY on user_id)

             [50 | 100]
            /     |     \
      [10|20]  [55|75]  [105|200]
      /  |  \   ...
[1][5][10][20]  ...    ← leaf pages contain actual row data
```

The leaf nodes of a clustered index hold the full row data, not a pointer to it. Range queries like `WHERE user_id BETWEEN 1000 AND 2000` benefit enormously because all matching rows are physically contiguous — a single sequential I/O pass retrieves them.

**Cost:** Insertions into a random key position (e.g., a UUID primary key) cause page splits, leading to fragmentation and write amplification. Sequential keys (auto-increment integers, ULIDs, snowflake IDs) avoid this.

### 3. Secondary / Non-Clustered Index

A non-clustered index stores a copy of the indexed column(s) plus a **row locator** (the clustered key in InnoDB, a physical row ID in PostgreSQL heap tables). It does not change where rows are stored.

```
Secondary Index on email column

B-Tree leaf: [email_value | primary_key]

"alice@ex.com" → PK=42   → then fetch row 42 from clustered index
"bob@ex.com"  → PK=7    → then fetch row 7 from clustered index
...
```

In InnoDB this means a secondary index lookup does **two B-Tree traversals**: once into the secondary index to find the PK, then once into the clustered index to fetch the row (a "double dip" or "bookmark lookup"). This is why covering indexes matter.

### 4. Hash Index

Stores a hash of the indexed value mapped to a row pointer. Lookups are O(1) average case for exact equality matches.

```
HASH("alice@ex.com") = 0xA3F2 → bucket → [row_ptr1]
HASH("bob@ex.com")   = 0x12B9 → bucket → [row_ptr2]
```

Hash indexes cannot satisfy range queries (`>`, `<`, `BETWEEN`), prefix matches, or ORDER BY. In PostgreSQL, hash indexes are durable (WAL-logged) since v10. MySQL MEMORY tables use hash by default. InnoDB has an **Adaptive Hash Index** (AHI) built automatically in memory — you do not create it manually.

### 5. Composite (Multi-Column) Index

A B-Tree built on multiple columns in a defined left-to-right order.

```sql
CREATE INDEX idx_orders ON orders (customer_id, status, created_at);
```

The index sorts first by `customer_id`, then by `status` within each `customer_id`, then by `created_at` within each status. This makes the **leftmost prefix rule** critical:

| Query predicate | Uses index? |
|-----------------|-------------|
| `WHERE customer_id = 5` | Yes — leftmost prefix |
| `WHERE customer_id = 5 AND status = 'open'` | Yes — two-column prefix |
| `WHERE customer_id = 5 AND status = 'open' AND created_at > '2024-01-01'` | Yes — full index |
| `WHERE status = 'open'` | No — skips first column |
| `WHERE customer_id = 5 AND created_at > '2024-01-01'` | Partial — uses customer_id, then scans for created_at |

### 6. Covering Index

A covering index includes **all columns** the query needs so the database never touches the base table. The index "covers" the query.

```sql
-- Query: SELECT email, created_at FROM users WHERE status = 'active';
-- Covering index:
CREATE INDEX idx_users_covering ON users (status, email, created_at);
```

The optimizer sees that the index leaf contains `status`, `email`, and `created_at` — everything required — so it reads only the index pages. This eliminates the second B-Tree lookup in InnoDB and removes heap I/O entirely in PostgreSQL.

### 7. Partial (Filtered) Index

Indexes only a subset of rows satisfying a WHERE condition. Smaller, faster, cheaper to maintain.

```sql
-- Only index unprocessed orders (the minority)
CREATE INDEX idx_pending_orders ON orders (created_at)
WHERE status = 'pending';
```

If 95% of orders are `completed`, this index is 20x smaller than a full index on `created_at`. The optimizer uses it only when the query's WHERE clause matches the index predicate.

### 8. Full-Text Index

Uses an **inverted index**: maps every distinct word/token to the list of documents/rows containing it.

```
Inverted index:
"database" → [doc_id=1, doc_id=4, doc_id=9]
"index"    → [doc_id=1, doc_id=2, doc_id=5]
"btree"    → [doc_id=2, doc_id=5]
```

Supports `MATCH ... AGAINST` (MySQL), `tsvector @@ tsquery` (PostgreSQL), or `CONTAINS` (SQL Server). Handles stemming, stop words, ranking. Not suitable for prefix wildcard queries without trigram extensions.

### 9. Bitmap Index

For each distinct value of a low-cardinality column, stores a bit vector with one bit per row — 1 if the row has that value, 0 otherwise. ANDing and ORing these bit vectors is extremely fast in columnar/analytics databases.

```
status = 'open'   : 1 0 0 1 0 1 1 0 0 1 ...
status = 'closed' : 0 1 1 0 1 0 0 1 1 0 ...
status = 'pending': 0 0 0 0 0 0 0 0 0 0 ...
```

Bitmap indexes are native to Oracle, Redshift, and OLAP systems. PostgreSQL simulates bitmap behavior internally during query execution (bitmap heap scan) but does not expose it as a user-facing index type. Terrible for OLTP tables with frequent writes because updating a bit vector for a busy column requires row-level locking across many rows.

### 10. Spatial Index (R-Tree / GiST)

R-Trees organize multidimensional data (2D coordinates, bounding boxes) by grouping nearby objects into nested rectangles. Useful for:

- `ST_DWithin(location, point, radius)` — find all restaurants within 5 km
- `ST_Intersects(region_a, region_b)` — geofencing

PostgreSQL uses GiST (Generalized Search Tree) indexes for PostGIS geometry types. MySQL and MariaDB use R-Tree indexes via `SPATIAL INDEX`.

---

## Build It / In Depth

### Worked Example: E-Commerce Order Search

**Schema:**

```sql
CREATE TABLE orders (
    order_id    BIGINT       PRIMARY KEY,   -- clustered index (InnoDB)
    customer_id BIGINT       NOT NULL,
    status      VARCHAR(20)  NOT NULL,      -- 'pending','processing','shipped','delivered'
    total_cents INT          NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL
);
```

**Step 1 — Baseline (no secondary indexes):**

```sql
EXPLAIN SELECT * FROM orders WHERE customer_id = 12345;
-- Full table scan: type=ALL, rows≈50,000,000
```

**Step 2 — Add a secondary index:**

```sql
CREATE INDEX idx_orders_customer ON orders (customer_id);

EXPLAIN SELECT * FROM orders WHERE customer_id = 12345;
-- type=ref, key=idx_orders_customer, rows≈200
```

But `SELECT *` causes a bookmark lookup per row — we fetch 200 rows from the secondary index and then 200 rows from the clustered index.

**Step 3 — Convert to a covering index:**

```sql
DROP INDEX idx_orders_customer ON orders;
CREATE INDEX idx_orders_covering ON orders (customer_id, status, created_at, total_cents);

EXPLAIN SELECT order_id, status, created_at, total_cents
FROM orders WHERE customer_id = 12345 ORDER BY created_at DESC;
-- Using index (no table fetch), Using index for ORDER BY
```

**Step 4 — Add a partial index for the ops dashboard (only pending):**

```sql
-- PostgreSQL syntax
CREATE INDEX idx_orders_pending ON orders (created_at DESC)
WHERE status = 'pending';

-- Query that uses it:
SELECT order_id, created_at FROM orders
WHERE status = 'pending' AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;
```

**Step 5 — Analyze index size and cost:**

```sql
-- PostgreSQL: check index sizes
SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass))
FROM pg_indexes
WHERE tablename = 'orders';
```

```
idx_orders_covering | 4328 MB    ← expensive but eliminates heap reads
idx_orders_pending  | 12 MB      ← tiny because only ~2% of rows are pending
```

Insight: `idx_orders_covering` is large. If writes are frequent, consider whether a narrower index plus an acceptable extra heap read is a better trade-off.

---

## Use It

### Which Index Type for Which System

| Scenario | Recommended Index |
|----------|-------------------|
| PK lookup, range scan by ID | Clustered B-Tree (default) |
| Equality filter on foreign key | Secondary B-Tree |
| Multi-column filter with known column order | Composite B-Tree (leftmost prefix rule) |
| Read-heavy, avoid heap fetch | Covering index |
| `WHERE status = 'active'` on a table where active rows are rare | Partial/Filtered index |
| Exact match on a hash like session token | Hash index (PostgreSQL ≥10, MEMORY engine) |
| Full-text search with ranking | Full-text / Inverted (PostgreSQL `tsvector`, Elasticsearch) |
| Low-cardinality column in analytics warehouse | Bitmap (Redshift, Oracle, ClickHouse) |
| Geo-coordinates, bounding box intersection | Spatial / R-Tree (PostGIS GiST, MySQL SPATIAL) |

### Technology-Specific Notes

- **PostgreSQL** — supports B-Tree, Hash, GiST, GIN, BRIN, SP-GiST. GIN is the go-to for full-text (`tsvector`) and JSONB containment. BRIN indexes are tiny and useful for naturally ordered time-series data (insertion-ordered `created_at` columns).
- **MySQL / InnoDB** — primary key is always the clustered index. All secondary indexes store the PK as the row locator. Adaptive Hash Index is automatic in-memory optimization. Full-text available via `FULLTEXT` index.
- **SQL Server** — explicit `CLUSTERED` / `NONCLUSTERED` keywords. Supports filtered indexes, columnstore indexes (excellent for analytics/OLAP on row-store tables), and included columns (`CREATE INDEX ... INCLUDE (col1, col2)`).
- **ClickHouse** — uses a sparse primary index over the sort key, plus skip indexes (bloom filter, minmax) for secondary filtering. Fundamentally different from RDBMS B-Tree semantics.
- **Elasticsearch / OpenSearch** — every field is indexed by default via an inverted index. Managing this aggressively is one of the first optimization levers.

---

## Common Pitfalls

- **Indexing a low-cardinality column alone.** An index on `gender` (two values) on a 50-million row table is often slower than a full scan because the optimizer picks it, then fetches 25 million rows via expensive random I/O. The optimizer should ignore it, but plans are not always perfect. Add it only as part of a composite index where it further narrows an already-selective prefix.

- **Violating the leftmost prefix rule.** Adding a composite index `(a, b, c)` and then wondering why `WHERE b = 1` does a full scan. The index is useless unless the query anchors on `a`. Map your most common query patterns before deciding column order.

- **Over-indexing write-heavy tables.** Every index on a table is maintained on every `INSERT`, `UPDATE` (if indexed columns change), and `DELETE`. A table with 15 indexes pays 15 index updates per write. Profile write throughput before adding speculative indexes.

- **Using UUID v4 as a clustered key in InnoDB.** Random UUIDs cause every insert to land on a random leaf page, causing constant page splits and a fragmented, bloated clustered index. Use auto-increment, snowflake IDs, or UUID v7 (time-ordered) for clustered keys.

- **Forgetting that `SELECT *` defeats covering indexes.** A well-designed covering index is undermined the moment someone adds a `*` or requests a column not in the index. Enforce column selection discipline in application queries — ORMs that default to `SELECT *` are a common offender.

---

## Exercises

1. **Easy — Leftmost prefix analysis.** Given the index `CREATE INDEX idx ON events (user_id, event_type, occurred_at)`, list five queries and predict which ones will use the index and which will not.

2. **Medium — Index design for a query workload.** A `payments` table has columns: `payment_id (PK)`, `user_id`, `merchant_id`, `amount`, `currency`, `status`, `created_at`. You have three high-frequency queries: (a) find all payments by user, (b) find all pending payments by merchant, (c) fetch total amount grouped by currency for a date range. Design the minimum set of indexes to cover all three efficiently. Justify each choice.

3. **Hard — Benchmark clustered vs. non-clustered key patterns.** Using PostgreSQL or MySQL locally, create two identical tables with 5 million rows — one with a BIGSERIAL primary key and one with a UUID v4 primary key. Measure insert throughput, table size on disk, and range scan latency for each. Explain the differences in terms of B-Tree structure and page splits.

---

## Key Terms

| Term | What people think | What it actually means |
|------|--------------------|------------------------|
| Clustered Index | An index that groups related rows together | An index whose leaf nodes **are** the table rows; defines physical sort order |
| Covering Index | Any index that "helps" a query | An index containing **every column** the query reads, so the table itself is never accessed |
| Cardinality | How many rows a table has | The number of **distinct values** in a column — high cardinality = more selective, better candidate for indexing |
| Selectivity | How fast an index is | The fraction of rows an index predicate eliminates — higher selectivity means fewer rows survive, making the index more useful |
| Index Scan vs. Seq Scan | Index scan is always faster | An index scan with many matching rows causes random I/O; a sequential scan may be faster when >10-20% of rows match |
| Composite Index | An index on two columns | A B-Tree over multiple columns in a **specific left-to-right order** — order matters critically for which queries it supports |
| Partial Index | A small index | An index that only includes rows satisfying a WHERE predicate — smaller, faster to maintain, used only when the query matches the predicate |

---

## Further Reading

- [PostgreSQL Index Types Documentation](https://www.postgresql.org/docs/current/indexes-types.html) — Official reference covering B-Tree, Hash, GiST, GIN, BRIN, SP-GiST with when to use each.
- [MySQL InnoDB Index Internals](https://dev.mysql.com/doc/refman/8.0/en/innodb-index-types.html) — Covers clustered vs. secondary index behavior, adaptive hash index, and the double-dip lookup pattern.
- [Use the Index, Luke](https://use-the-index-luke.com/) — Free, database-agnostic guide with deep coverage of B-Tree internals, composite indexes, and execution plan analysis.
- [SQL Server Columnstore Indexes Overview](https://learn.microsoft.com/en-us/sql/relational-databases/indexes/columnstore-indexes-overview) — Microsoft's reference on columnstore indexes; useful mental model for OLAP index strategies applicable across systems.
- [Designing Data-Intensive Applications, Chapter 3 — Kleppmann](https://dataintensive.net/) — Storage engine internals (B-Trees vs. LSM-Trees, SSTables) that explain the cost model behind every index type.
