# Database Types You Should Know in 2025

> Pick the wrong database and you're not just slow — you're rebuilding in six months.

**Type:** Learn
**Prerequisites:** Fundamentals of System Design, CAP Theorem, Data Modeling Basics
**Time:** ~35 minutes

---

## The Problem

A startup builds a social platform on PostgreSQL. Everything works at 10,000 users. At 10 million users, the friend-of-friend query that was 80 ms is now 40 seconds — because a relational JOIN across a 500 M-row edges table is fundamentally the wrong tool for a graph traversal. Swapping the query engine doesn't fix it. The database type is wrong.

Meanwhile, their recommendation engine ingests 50 GB of user-activity logs per day. Running aggregations on that in Postgres costs them $2,000/month in read replicas just to keep the OLAP queries from killing production. A columnar store would do the same work in a fraction of the time at a tenth of the cost.

Modern systems routinely use four or five database types simultaneously. The engineers who understand the taxonomy — why each type exists, what data shape it's optimized for, and what it sacrifices — are the ones who make the right call before the migration. Everyone else makes it after.

---

## The Concept

### The Core Mental Model

Every database type is an answer to one question: **what is the dominant access pattern?** Storage layout, indexing strategy, query language, and replication model all flow from that answer.

```
Access Pattern → Data Shape → Storage Layout → Database Type
─────────────────────────────────────────────────────────────
Flexible queries on structured records  →  Row store  →  Relational
Aggregations on many rows, few columns  →  Column store  →  Columnar
Fast O(1) point lookup                  →  Hash map  →  Key-Value
Sub-millisecond reads/writes            →  RAM  →  In-Memory
Sparse, wide rows, massive scale        →  LSM tree  →  Wide-Column
Ordered time + high ingest rate         →  Time-partitioned  →  Time-Series
Traversing relationships                →  Graph (adj. list/native)  →  Graph
Evolving document structure             →  BSON/JSON  →  Document
Similarity over high-dim vectors        →  ANN index  →  Vector
Spatial proximity / containment         →  R-tree / H3  →  Geospatial
Full-text relevance ranking             →  Inverted index  →  Text-Search
Unstructured binary blobs               →  Object store  →  Blob
Append-only tamper-proof audit          →  Merkle chain  →  Immutable Ledger
```

### Taxonomy at a Glance

| Type | Primary Index | Query Strength | Weak Spot | Representative Products |
|---|---|---|---|---|
| **Relational** | B-tree (row) | Joins, transactions | OLAP at scale | PostgreSQL, MySQL, CockroachDB |
| **Columnar** | Column segment | Aggregations, scans | Point lookups, OLTP | BigQuery, Redshift, ClickHouse |
| **Key-Value** | Hash / B-tree | O(1) get/put | Range scans, complex queries | DynamoDB, Redis (KV mode) |
| **In-Memory** | RAM hash / skip list | Ultra-low latency | Persistence, data size | Redis, Memcached, Apache Ignite |
| **Wide-Column** | Row key + CF | Distributed writes, large datasets | Ad-hoc queries | Cassandra, HBase, Bigtable |
| **Time-Series** | Time + tags | Aggregations over time windows | Relational joins | InfluxDB, TimescaleDB, Prometheus |
| **Graph** | Vertex/edge store | Multi-hop traversals | Bulk analytics | Neo4j, Amazon Neptune, TigerGraph |
| **Document** | _id + secondary | Flexible schema, nested docs | Cross-collection joins | MongoDB, Firestore, Couchbase |
| **Geospatial** | R-tree / H3 | Proximity, containment, routing | General OLTP | PostGIS, MongoDB geo, BigQuery geo |
| **Text-Search** | Inverted index | Ranked full-text search | Strict ACID transactions | Elasticsearch, OpenSearch, Typesense |
| **Blob** | Object key | Arbitrary binary, massive scale | Query by content | S3, GCS, Azure Blob Storage |
| **Vector** | ANN index (HNSW/IVF) | Similarity search on embeddings | Exact match at scale | Pinecone, Weaviate, pgvector |
| **Immutable Ledger** | Cryptographic hash chain | Verified audit trail | Mutability, throughput | Amazon QLDB, Hyperledger Fabric |

---

### How Each Type Works Under the Hood

#### Relational
Data lives in heap files, one row per tuple. B-tree indexes let the engine skip to rows by key. MVCC (Multi-Version Concurrency Control) gives transactions snapshot isolation. The optimizer picks join algorithms (hash join, merge join, nested loop) based on statistics. Strong for any workload that needs ACID and ad-hoc querying. Struggles when the data model doesn't fit rows and columns (graphs, blobs) or when analytical scans must touch hundreds of millions of rows.

#### Columnar
Stores each column as a contiguous block on disk. A `SUM(revenue)` query reads only the revenue column — 10× less I/O than a row store reading entire tuples. Run-length encoding and dictionary compression work especially well on repeated values in a column (e.g., country codes). Writes are expensive because every column file must be updated. Not suitable for transactional workloads that update individual rows frequently.

#### Key-Value
The simplest possible interface: `put(key, value)` / `get(key)`. DynamoDB uses a hash on the partition key to route to a shard; within a shard, a B-tree handles sorted range queries on the sort key. Redis uses in-memory hash tables. The value is opaque — the database doesn't parse it. Extremely fast; zero support for querying inside the value.

#### In-Memory
All data lives in DRAM. Redis uses a single-threaded event loop with epoll, achieving sub-millisecond latency at the cost of memory size. Persistence comes via snapshots (RDB) or append-only files (AOF), but neither is zero-downtime-safe on failure. Use for caches, session stores, rate-limit counters, leaderboards — anything where you can afford to lose a few seconds of data.

#### Wide-Column
Cassandra and HBase organize data as `(row_key, column_family, column_qualifier, timestamp) → value`. Writes go to an in-memory memtable, then flush to SSTables. Compaction merges SSTables. Reads merge multiple SSTables and the memtable (expensive). Denormalization is mandatory — you design tables around your query patterns, not around your data model. Excellent for high-write, eventually-consistent workloads.

#### Time-Series
Time is the partition key. InfluxDB's TSM (Time-Structured Merge Tree) stores measurements in time-ordered blocks, compressing timestamps via delta-delta encoding and values via run-length/XOR encoding. Most time-series DBs auto-expire old data via retention policies. Built-in aggregation functions (rate, moving average, downsampling) are first-class. The mental model: a stream of `(timestamp, tags, fields)` tuples, not a table of rows.

#### Graph
Vertices and edges are first-class citizens stored in a native adjacency structure. A friend-of-friend query traverses edges directly without a JOIN. Cypher (Neo4j) and Gremlin are graph query languages. Graph DBs shine when relationship depth matters — fraud rings, dependency graphs, identity graphs. They are not designed for bulk analytics across all vertices.

#### Document
A document is a self-contained JSON/BSON object. No schema migration needed to add a field. Secondary indexes can point into nested fields. MongoDB stores documents in collections; Firestore uses a hierarchy of collections and sub-collections. Joins across collections require `$lookup` (MongoDB) or application-side merging. Good for product catalogs, CMS content, user profiles with varying attributes.

#### Geospatial
Spatial indexes partition 2D (or 3D) space for fast proximity queries. PostGIS adds geometry types and an R-tree (GiST) index to PostgreSQL. H3 (Uber's hex grid) converts lat/lng to a cell ID — proximity becomes integer comparison. Use for "find all restaurants within 2 km", geofencing, route optimization, map tile serving.

#### Text-Search
An inverted index maps each token to the list of documents containing it. At query time, the engine intersects posting lists, scores with TF-IDF or BM25, and applies boosting and filters. Analyzers handle tokenization, stemming, and stop words. Not a transactional store — Elasticsearch indices are eventually consistent. Typical pattern: write to Postgres, replicate to Elasticsearch for search.

#### Blob (Object Store)
Flat namespace: bucket + key → binary object. S3 scales to exabytes with 11 nines of durability by replicating across three AZs using erasure coding. There is no SQL, no schema, no index on content. Access control is IAM policies + presigned URLs. The correct model for images, videos, ML model weights, log archives, data lake files.

#### Vector
Stores high-dimensional float arrays (embeddings) and answers approximate nearest-neighbor (ANN) queries. HNSW (Hierarchical Navigable Small World) builds a multi-layer graph; queries traverse layers from coarse to fine in O(log n). Products like Pinecone and Weaviate are dedicated vector DBs. pgvector adds vector support to Postgres. The trade-off: approximate (not exact) results for acceptable latency.

#### Immutable Ledger
All writes are appended to a cryptographic hash chain (Merkle tree). Each record includes a hash of the prior record, making retroactive tampering detectable. Amazon QLDB exposes a SQL-like interface over an immutable journal. Used for financial audit trails, supply chain provenance, healthcare records. Not suitable for frequent mutations or high-throughput OLTP.

---

## Build It / In Depth

### Worked Example: Designing the Storage Layer for a Ride-Share Platform

Let's map the data entities to database types using concrete reasoning.

```
Ride-Share Platform: Entities & Access Patterns
═══════════════════════════════════════════════════════════════
Entity              Access Pattern                 DB Type
──────────────────────────────────────────────────────────────
User profiles       CRUD, auth lookup              Relational (Postgres)
Active sessions     Read in <1 ms, TTL             In-Memory (Redis)
Driver locations    Write 1/sec per driver,        Geospatial (PostGIS or
                    "find drivers near (lat,lng)"  Redis GEO)
Trip records        Append-only, query by time,    Relational or Time-Series
                    revenue analytics              + Columnar for BI
Pricing features    100 K rps, low-latency read    Key-Value (DynamoDB)
Driver earnings     Audit trail, no tampering      Immutable Ledger (QLDB)
Ride events (Kafka) Stream aggregation (ETA, etc.) Time-Series (InfluxDB)
Search ("Downtown") Full-text, autocomplete        Text-Search (Elasticsearch)
Fraud graph         Who shared device/card?        Graph (Neptune)
ML recommendations  Embedding similarity           Vector (Pinecone)
```

#### Step 1 — Driver Location: Redis GEO

```bash
# Driver updates position every second
GEOADD drivers:active 77.5946 12.9716 "driver:42"

# Rider requests nearby drivers within 3 km
GEORADIUS drivers:active 77.5910 12.9700 3 km ASC COUNT 5
```

Redis GEO stores coordinates as a geohash inside a sorted set. Radius queries run in O(N+log M) where N is the result size — sub-millisecond at scale.

#### Step 2 — Pricing Features: DynamoDB

```
Table: pricing_features
PK: feature_name    SK: version
─────────────────────────────────
surge_multiplier    v1  →  2.1
base_fare_usd       v1  →  1.50
```

```python
import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("pricing_features")

# Ultra-fast read at request time (single-digit ms P99)
response = table.get_item(Key={"feature_name": "surge_multiplier", "version": "v1"})
surge = response["Item"]["value"]
```

#### Step 3 — Earnings Audit: QLDB

```python
import boto3

qldb = boto3.client("qldb-session", region_name="us-east-1")

# Every payout is appended; the hash chain guarantees integrity
# Query the full history of a driver's earnings
statement = """
    SELECT * FROM history(driver_earnings)
    WHERE metadata.id = 'driver:42'
"""
```

QLDB returns a cryptographic proof that any past record was not altered.

#### Step 4 — Analytics: ClickHouse Columnar

```sql
-- 50 GB/day of trip data lands in ClickHouse via Kafka
-- This aggregation runs in <2 seconds on 1 billion rows
SELECT
    toStartOfHour(completed_at) AS hour,
    city,
    sum(fare_usd)               AS revenue,
    avg(trip_duration_seconds)  AS avg_duration
FROM trips
WHERE completed_at >= now() - INTERVAL 30 DAY
GROUP BY hour, city
ORDER BY hour DESC;
```

The same query on a row-based PostgreSQL table would require a full sequential scan of the fare column across rows containing many unneeded columns. ClickHouse reads only `completed_at`, `city`, `fare_usd`, and `trip_duration_seconds`.

---

## Use It

### Mapping Cloud Services to Database Types

| Type | AWS | GCP | Azure | Self-Hosted OSS |
|---|---|---|---|---|
| Relational | RDS Aurora | Cloud SQL, AlloyDB | Azure SQL | PostgreSQL, MySQL |
| Columnar | Redshift | BigQuery | Synapse Analytics | ClickHouse, DuckDB |
| Key-Value | DynamoDB | Firestore (KV mode) | Cosmos DB (Table) | Redis, ScyllaDB |
| In-Memory | ElastiCache (Redis) | Memorystore | Azure Cache | Redis, Memcached |
| Wide-Column | DynamoDB (sort key) | Bigtable | Cosmos DB (Cassandra) | Cassandra, HBase |
| Time-Series | Timestream | BigQuery (partitioned) | Azure Data Explorer | InfluxDB, TimescaleDB |
| Graph | Neptune | — | Cosmos DB (Gremlin) | Neo4j, ArangoDB |
| Document | DocumentDB | Firestore | Cosmos DB (Mongo) | MongoDB, Couchbase |
| Geospatial | RDS+PostGIS, Location | BigQuery geo | Azure Maps | PostGIS, Redis GEO |
| Text-Search | OpenSearch | Vertex AI Search | Cognitive Search | Elasticsearch, Typesense |
| Blob | S3 | GCS | Blob Storage | MinIO, Ceph |
| Vector | OpenSearch KNN, pgvector | Vertex AI Matching | Azure AI Search | Pinecone, Weaviate, pgvector |
| Immutable Ledger | QLDB | — | Azure Confidential Ledger | Hyperledger Fabric |

### Decision Heuristic

```
Is the value opaque (binary, file)?
  → Blob (S3)

Do you need similarity search on embeddings?
  → Vector DB (Pinecone, pgvector)

Is time the primary dimension (metrics, logs, IoT)?
  → Time-Series (InfluxDB, Timestream)

Are relationships the primary query concern?
  → Graph (Neo4j, Neptune)

Need sub-millisecond latency, data fits in RAM?
  → In-Memory (Redis)

High-write, massive scale, eventual consistency OK?
  → Wide-Column (Cassandra, Bigtable)

Full-text search with ranking?
  → Text-Search (Elasticsearch, Typesense)

OLAP / analytics on large datasets?
  → Columnar (BigQuery, ClickHouse)

General-purpose OLTP with strong consistency?
  → Relational (PostgreSQL, Aurora)
```

---

## Common Pitfalls

- **Using a relational DB for everything and adding indexes forever.** A graph traversal that requires joining a 500 M-row edges table five times is not fixable with an index. Know when to reach for a graph DB or pre-materialized adjacency.

- **Treating Redis as a primary database.** Redis AOF + RDB persistence is not equivalent to PostgreSQL durability. Data loss windows exist. Use Redis for cache and ephemeral state; keep the source of truth in a durable store.

- **Using Elasticsearch as the write path.** Elasticsearch is eventually consistent and not ACID. Writing directly to ES and reading back immediately is a race condition. The correct pattern: write to Postgres, stream changes to ES via CDC (Debezium or similar).

- **Choosing a wide-column DB before designing queries.** Cassandra requires you to know your query patterns before table design. Schema-first thinking ("let me normalize this") leads to unavoidable full-cluster scans or expensive secondary indexes.

- **Assuming one vector DB handles all retrieval.** ANN indexes (HNSW, IVF) return *approximate* neighbors. For compliance or financial use cases that require exact retrieval, this trade-off may be unacceptable. Understand whether your use case requires exact or approximate results.

---

## Exercises

1. **Easy — Classification drill.** A healthcare app stores patient vitals (heart rate, blood pressure) from 10,000 wearables, sampled every 10 seconds. Identify the database type and explain *why* — including what specific feature of that type makes it the right fit.

2. **Medium — Multi-DB design.** Design the database layer for a job board (LinkedIn-style). You need: user profiles, job postings with full-text search, a recommendation feed (personalized via ML embeddings), connections between users (1st, 2nd, 3rd degree), and session tokens. Assign a database type to each concern and justify your choices.

3. **Hard — Migration design.** A legacy e-commerce platform runs entirely on MySQL. The product team wants to add: (a) real-time search-as-you-type on product catalog, (b) "customers who viewed this also viewed" recommendations using embedding similarity, and (c) a fraud detection system that checks whether a new order's device fingerprint is connected to previously flagged accounts. Design the incremental migration: what new databases do you introduce, how do you keep data in sync, and what failure modes must you handle?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **NoSQL** | "anything that isn't SQL" | Umbrella for non-relational models (KV, document, wide-column, graph). Many NoSQL databases support SQL-like query languages. |
| **OLTP vs OLAP** | Two separate systems | OLTP = row-oriented, high-concurrency, short transactions. OLAP = column-oriented, low-concurrency, analytical scans. One workload is hostile to the other's storage layout. |
| **Eventual Consistency** | "data might be wrong" | Writes propagate asynchronously; replicas converge *eventually*. Reads may see stale data during the convergence window — not permanently incorrect data. |
| **ANN (Approximate Nearest Neighbor)** | "close enough" search | Sacrifices exactness for speed. HNSW can return 95–99% recall at 10× the speed of exact KNN. The 1–5% miss rate is usually acceptable for ML retrieval. |
| **LSM Tree** | "some kind of index" | Log-Structured Merge Tree: writes go to a WAL + in-memory buffer, flushed to sorted immutable files (SSTables), merged by compaction. Optimizes write throughput at the cost of read amplification. Used by Cassandra, RocksDB, InfluxDB. |
| **Sharding** | "splitting data across servers" | Horizontal partitioning by key. Queries that cross shard boundaries require scatter-gather, which multiplies latency. Schema and access-pattern design must minimize cross-shard queries. |
| **Columnar Compression** | "storage savings" | Compressing a column of the same data type achieves 5–20× compression vs. row storage. This means less I/O for scans, which directly translates to faster analytical queries — not just smaller storage. |

---

## Further Reading

- [PostgreSQL Documentation — Index Types](https://www.postgresql.org/docs/current/indexes-types.html) — Deep reference on B-tree, Hash, GiST, GIN, and BRIN indexes; foundational for understanding how relational indexing works.
- [ClickHouse Architecture Overview](https://clickhouse.com/docs/en/development/architecture) — Official explanation of the MergeTree engine, columnar storage, and compression — the canonical columnar DB internals reference.
- [Designing Data-Intensive Applications — Martin Kleppmann (O'Reilly)](https://dataintensive.net/) — Chapter 3 (Storage and Retrieval) covers SSTables, LSM trees, B-trees, and column-oriented storage with the depth no blog post matches.
- [Cassandra Data Modeling Guide](https://cassandra.apache.org/doc/latest/cassandra/data_modeling/intro.html) — Official DataStax/Apache guide on query-first modeling for wide-column stores; explains why denormalization is mandatory.
- [Pinecone — Vector Database Fundamentals](https://www.pinecone.io/learn/vector-database/) — Vendor-neutral explanation of HNSW, IVF, ANN trade-offs, and how vector indexes differ from traditional database indexes.
