# 5 Data Structures That Make DB Queries Super Fast

> Five structures that turn "scan every row" into "jump straight to the answer" — and the trade-offs each one carries.

**Type:** Learn
**Prerequisites:** Basic data structures (trees, hash tables), SQL basics
**Time:** ~25 minutes

---

## The Problem

A naive database query reads every row in a table, checks each one against the WHERE clause, and returns the matches. For a table with a million rows, that is a million reads and a million comparisons — every single query, no matter how selective.

Indexes are the solution. An index is a separate data structure, derived from the table data, that lets the database find matching rows in O(log n) or O(1) time instead of O(n). Every index is a trade-off: faster reads, slower writes, more disk space, and (sometimes) a different set of queries it can answer.

Different indexes use different data structures underneath. Knowing what is inside lets you pick the right index for the workload, predict performance, and debug slow queries. This lesson covers the five structures you will encounter: B-Tree, B+Tree, Hash, Bitmap, and Inverted.

---

## The Concept

### What an index actually is

```
   Without index:
   SELECT * FROM users WHERE email = 'alex@example.com';
   → Full table scan: read every row, check email column, return matches

   With index:
   → Look up 'alex@example.com' in the index → get row location → fetch row

   Time: O(n)         → O(log n) or O(1)
```

An index is a **separate data structure** that maps key values to row locations. The database maintains it automatically — every INSERT, UPDATE, DELETE updates both the table and its indexes.

---

### 1. B-Tree Index

The workhorse. Used by default in almost every relational database for primary keys and most secondary indexes.

**Structure:** a balanced tree where every node contains keys and pointers to child nodes (and sometimes row data). Lookup proceeds by comparing the search key against node keys and descending the matching child.

```
                          [50 | 100 | 150]
                        /       |       \
              [20 | 30 | 40]  [70 | 80]  [120 | 130]
              /    |    \      /    \      /    \
           [10] [25] [35] [60] [75] [90] [110] [140]
```

**Properties:**

- **Balanced** — all leaves at the same depth; lookup time is O(log n) regardless of where the key is
- **Ordered** — keys within nodes are sorted; range queries (`WHERE x BETWEEN 10 AND 50`) can be answered by a sequential scan starting at the first match
- **Disk-friendly** — node size is tuned to match page size (typically 8–16 KB), minimizing disk I/O per level

**Trade-offs:**

- ✅ Excellent for: equality, range, prefix, and `ORDER BY` queries
- ✅ Good for: high-cardinality columns (unique or near-unique values)
- ❌ Bad for: low-cardinality columns (gender, status flag) — most of the tree is scanned anyway
- ❌ Slow for: very large text matching (LIKE '%pattern%' with leading wildcard)

**Used by:** every major relational database as the default index type.

---

### 2. B+Tree Index

A refinement of the B-Tree used by InnoDB (MySQL) and Postgres. The key difference: **all data pointers live in leaf nodes only**, and leaf nodes are linked together.

```
   Internal nodes (only keys):
                          [50 | 100 | 150]
                        /       |       \
              [20 | 30 | 40]  [70 | 80]  [120 | 130]

   Leaf nodes (keys + data pointers, linked left-to-right):
   [10→row1, 20→row2, 30→row3] ⇄ [40→row4, 50→row5] ⇄ [60→row6, 70→row7] ⇄ ...
```

**Properties:**

- **Higher fanout** — internal nodes hold only keys, so each node fits more keys; the tree is shorter; fewer disk I/Os
- **Sequential leaf access** — linked leaves mean range queries scan sequentially without tree traversal
- **Better for cache** — internal nodes are smaller; more fit in memory

**Trade-offs:** same as B-Tree, but with slightly better range-query performance and slightly higher constant factor for point lookups (one more level to traverse).

**Used by:** MySQL InnoDB (clustered primary key), Postgres (all indexes), most modern databases.

In InnoDB, the B+Tree is even more important: the primary key index *is* the table — the leaf nodes contain the actual row data, not just pointers. Secondary indexes then store primary-key values in their leaf nodes, requiring a second lookup (called a "bookmark lookup") to fetch the full row.

---

### 3. Hash Index

**Structure:** a hash table that maps key values to row locations via a hash function.

```
   Key                  Hash function    Bucket
   "alex@x.com"    →    hash() → 0x3A   → bucket[0x3A] → row pointer
   "bob@x.com"     →    hash() → 0xF1   → bucket[0xF1] → row pointer
```

**Properties:**

- **O(1) lookup** for equality (`WHERE email = 'alex@example.com'`)
- **Compact** for point lookups — fewer comparisons than a tree

**Trade-offs:**

- ✅ Excellent for: pure equality lookups (key-value stores)
- ❌ Cannot do range queries — there is no ordering in a hash table
- ❌ Cannot do `ORDER BY` on the indexed column
- ❌ Cannot do prefix matches (`WHERE name LIKE 'Alex%'`)
- ❌ Collisions degrade performance (rare with a good hash function, but possible)

**Used by:** Postgres has hash indexes but rarely recommends them (B-Tree is usually better even for equality). Some key-value stores (Redis, DynamoDB) use hash indexes internally. Memory databases (Memcached) are essentially hash indexes.

**When to actually use hash in Postgres:** almost never. B-Tree handles equality just as fast in practice and supports far more query types.

---

### 4. Bitmap Index

**Structure:** for each possible value of a column, store a bitmap where bit `i` is 1 if row `i` has that value.

```
   Table:                       Bitmap index for status:
   id | status                  status=active:  1 0 0 1 1 0 1 0
   1  | active                  status=pending: 0 1 0 0 0 1 0 0
   2  | pending                 status=closed:  0 0 1 0 0 0 0 1
   3  | closed
   4  | active
   5  | active
   6  | pending
   7  | active
   8  | closed
```

**Query:** `WHERE status = 'active'` → return rows where bit is 1 (rows 1, 4, 5, 7). `WHERE status IN ('active', 'pending')` → bitwise OR of two bitmaps.

**Properties:**

- **Tiny storage** for low-cardinality columns (a few possible values)
- **Fast set operations** — bitwise AND, OR, XOR are fast
- **Excellent for analytics queries** with multiple filter conditions

**Trade-offs:**

- ✅ Excellent for: low-cardinality columns (gender, status, country)
- ✅ Excellent for: queries that combine multiple low-cardinality filters (`WHERE status='active' AND country='US'`)
- ❌ Bad for: high-cardinality columns (each value gets its own bitmap; storage explodes)
- ❌ Bad for: write-heavy workloads (updating a row requires updating many bitmaps)

**Used by:** Oracle, Postgres (using a workaround), data warehouses (Snowflake, BigQuery).

In Postgres, the equivalent is a partial index (`CREATE INDEX ... WHERE status = 'active'`) or a multi-column B-Tree. True bitmap indexes are not the default in most OLTP databases.

---

### 5. Inverted Index

**Structure:** maps each unique term to a list of row IDs (or positions) where it appears. The basis of full-text search.

```
   Documents:
   doc1: "the quick brown fox"
   doc2: "the lazy dog"
   doc3: "the quick dog"

   Inverted index:
   brown  → [doc1]
   dog    → [doc2, doc3]
   fox    → [doc1]
   lazy   → [doc2]
   quick  → [doc1, doc3]
   the    → [doc1, doc2, doc3]
```

**Properties:**

- **Fast text search** — find all documents containing "quick" in O(1) lookup + list traversal
- **Supports relevance ranking** — TF-IDF, BM25 can be computed from the index
- **Supports phrase queries** — "quick dog" becomes positions in the postings lists

**Trade-offs:**

- ✅ Excellent for: full-text search, log search, document search
- ❌ Bad for: structured data queries
- ❌ Storage-heavy for large corpora
- ❌ Updating requires re-indexing

**Used by:** Elasticsearch, Solr, Lucene (the library behind both). Postgres has `tsvector` + GIN indexes which are an inverted-index-style structure for full-text search. Most search engines use some form of inverted index.

---

### The five structures, side by side

| Structure | Best for | Range queries | Equality | Storage | Write cost |
|---|---|---|---|---|---|
| **B-Tree** | General purpose | ✅ | ✅ | Medium | Medium |
| **B+Tree** | General purpose (refined) | ✅ | ✅ | Medium | Medium |
| **Hash** | Pure key-value lookups | ❌ | ✅✅ | Low | Low |
| **Bitmap** | Low-cardinality analytics | Limited | ✅ | Low | High |
| **Inverted** | Full-text search | Limited | ✅ | High | High |

---

### Choosing the right index

| Query pattern | Index type |
|---|---|
| `WHERE id = 42` | B-Tree (primary key) |
| `WHERE created_at > '2025-01-01'` | B-Tree |
| `WHERE email = 'x@y.com'` | B-Tree (unique) or Hash |
| `WHERE status = 'active' AND country = 'US'` | Multi-column B-Tree or Bitmap |
| `WHERE name LIKE 'Alex%'` | B-Tree (prefix match) |
| `WHERE description LIKE '%fox%'` | Inverted (full-text) |
| `WHERE tags @> ARRAY['urgent']` | GIN (generalized inverted) |
| `WHERE location ST_DWithin(...)` | GiST / SP-GiST (PostGIS) |

---

## Build It / In Depth

### How a B+Tree lookup works, step by step

For a B+Tree with fanout 100 and 1 million rows:

```
   Tree depth = log_100(1,000,000) ≈ 3

   Lookup 'alex@example.com':
   1. Read root node (1 disk I/O)
      → keys: [a...m...z] (alphabetical)
      → 'alex...' falls in 'a-m' bucket
   2. Read intermediate node (1 disk I/O)
      → keys: [alex, alle, alma, ...]
      → exact match in 'alex'
   3. Read leaf node (1 disk I/O)
      → contains 'alex@example.com' → row pointer

   Total: 3 disk I/Os
   Without index: 1,000,000 disk I/Os (sequential scan)
   Speedup: ~333,000x
```

This is why indexes matter. A B+Tree of depth 3 turns a million-row scan into 3 page reads.

---

### A composite index and column order

Composite (multi-column) indexes have a critical property: **column order matters**.

```sql
CREATE INDEX idx_orders_user_date ON orders (user_id, created_at);
```

This index can answer:
- ✅ `WHERE user_id = 42` (leading column)
- ✅ `WHERE user_id = 42 AND created_at > '2025-01-01'` (both columns)
- ✅ `WHERE user_id = 42 ORDER BY created_at` (leading column + sort)
- ❌ `WHERE created_at > '2025-01-01'` (skipping leading column)
- ❌ `ORDER BY created_at` alone

**Rule of thumb:** put the most selective (highest cardinality, most filtering) column first; put columns used in `ORDER BY` last.

---

### Indexes have costs

Every index has three costs:

1. **Disk space.** An index is a separate data structure that can be 10–50% the size of the indexed column. A table with 10 indexes uses much more disk than the same table with 1.

2. **Write amplification.** Every INSERT, UPDATE, DELETE must update every index that includes the modified columns. A table with 10 indexes writes 10× as much for each change.

3. **Memory pressure.** Indexes compete for buffer pool space. Too many indexes means the working set does not fit in memory.

**Index hygiene:**

```sql
-- Find unused indexes
SELECT schemaname, relname, indexrelname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;

-- Find duplicate indexes (same columns, same order)
SELECT a.indexrelid::regclass, b.indexrelid::regclass
FROM pg_index a, pg_index b
WHERE a.indexrelid != b.indexrelid
  AND a.indrelid = b.indrelid
  AND a.indkey = b.indkey;
```

Drop indexes that nothing uses. The query planner's choice of index depends on usage stats; stale indexes still slow writes.

---

## Use It

### Decision cheat sheet

| Query pattern | Index to create |
|---|---|
| Point lookup by ID | Primary key (B-Tree, automatic) |
| Equality on a column | Unique B-Tree if values are unique, B-Tree otherwise |
| Range scan on a column | B-Tree |
| Equality on multiple columns | Multi-column B-Tree (selective first) |
| Full-text search | GIN with `to_tsvector` (Postgres) or external (Elasticsearch) |
| Array contains / JSON path | GIN |
| Geospatial | GiST (PostGIS) |
| Low-cardinality filter (status, country) | Partial index or BRIN (block range) |

### Postgres-specific index types worth knowing

| Type | Use case |
|---|---|
| **B-Tree** (default) | General purpose |
| **Hash** | Rarely useful in Postgres (B-Tree handles equality) |
| **GIN** (Generalized Inverted) | Full-text, JSONB, arrays |
| **GiST** (Generalized Search Tree) | Geospatial, range types, full-text |
| **SP-GiST** | Space-partitioned (large sparse data) |
| **BRIN** (Block Range) | Very large tables where data is naturally clustered (time series, logs) |
| **Partial** | Index only a subset (e.g., `WHERE status = 'active'`) |
| **Expression** | Index on a function of a column (`lower(email)`) |

---

## Common Pitfalls

- **Over-indexing.** Every index slows writes and uses disk. Index for the queries you run, not the ones you might run.

- **Wrong column order in composite indexes.** `(A, B)` is not the same as `(B, A)`. Put the most selective column first; put ORDER BY columns last.

- **Indexing low-cardinality columns with B-Tree.** A column with 3 values (active/pending/closed) indexed with B-Tree is rarely useful. Use a partial index instead.

- **Forgetting to analyze after schema changes.** Postgres's query planner uses table statistics to decide which index to use. After heavy data changes, run `ANALYZE table_name`.

- **Creating an index that the planner cannot use.** `LIKE '%pattern%'` (leading wildcard), functions on indexed columns (`WHERE lower(email) = ...` without an expression index), and type mismatches all prevent index use.

- **Ignoring index bloat.** On a high-update table, indexes can become bloated (dead pointers to deleted rows). Run `REINDEX` periodically or use `pg_repack` for online rebuilds.

- **Not testing with realistic data.** An index that helps on a 1000-row table may be useless on a 100M-row table — or vice versa. Always test at production scale.

---

## Exercises

1. **Easy** — For each of the five data structures (B-Tree, B+Tree, Hash, Bitmap, Inverted), give one query pattern where it is the best fit and one where it is the worst fit.

2. **Medium** — Take a real query from your application (or invent one). Run `EXPLAIN ANALYZE` on it. Identify the index it uses (or does not use). If it is doing a sequential scan, propose an index that would help, and predict whether the planner will actually use it.

3. **Hard** — A table has 50 columns, 1 billion rows, and receives 100k writes/second. You need indexes to support 20 distinct query patterns. Design the index set: which columns to index, in what order for composite indexes, which indexes to make partial, and which to drop. Justify each choice with the trade-off.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Index | A way to make queries faster | A separate data structure derived from table data that maps key values to row locations; maintained automatically by the database |
| B-Tree | The only index type | A balanced tree with keys in internal and leaf nodes; the default index type in nearly every relational database |
| B+Tree | A B-Tree variant | A B-Tree where all data pointers live in leaf nodes and leaves are linked; better range queries, used by InnoDB and Postgres |
| Hash index | The fastest | A hash table mapping keys to row locations via a hash function; O(1) equality but no range queries or ordering |
| Bitmap index | For analytics | A bitmap per possible value, with bit i set if row i has that value; fast for low-cardinality filters and set operations |
| Inverted index | For search | A mapping from terms to postings lists (document IDs containing the term); the basis of full-text search engines |
| Composite index | An index on multiple columns | An index on (A, B) supports queries on A or A+B but not B alone; column order matters |
| Partial index | An index on a subset | An index built only for rows matching a WHERE clause; smaller and faster for hot subsets of data |

---

## Further Reading

- **Use The Index, Luke** — the definitive guide to SQL indexing by Markus Winand: https://use-the-index-luke.com/
- **"Database Internals"** — Alex Petrov's book on storage engines and index structures: https://www.oreilly.com/library/view/database-internals/9781492040330/
- **PostgreSQL Documentation — Indexes** — the official reference, covering every index type: https://www.postgresql.org/docs/current/indexes.html
- **"SQL Performance Explained"** — covers the physics of B-Tree lookups and why some queries don't use indexes: https://sql-performance-explained.com/
- **CMU 15-445 (Database Systems) Lecture Videos** — Andy Pavlo's excellent course on indexing and storage: https://15445.courses.cs.cmu.edu/