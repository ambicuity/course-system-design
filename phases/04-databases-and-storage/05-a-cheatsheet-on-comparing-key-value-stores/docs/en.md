# A Cheatsheet on Comparing Key-Value Stores

> The right key-value store depends on four axes — replication, consistency, discovery, and partitioning — and getting any one wrong is a production incident waiting to happen.

**Type:** Learn
**Prerequisites:** CAP Theorem, Database Replication Patterns, Consistent Hashing
**Time:** ~25 minutes

---

## The Problem

You need a fast, scalable store for session tokens, product catalogs, leaderboards, distributed locks, or feature flags. You search "key-value database" and find a dozen options. Redis, Cassandra, DynamoDB, etcd, Riak — they all store keys and values, so they are interchangeable, right?

Wrong. In a Black Friday traffic spike, Redis without persistence loses your cart data on restart. Cassandra gives you stale reads unless you tune the quorum. etcd grinds to a halt under heavy write load because it is designed for coordination, not data. Choosing by benchmark alone gets you a system that fails in the specific way your workload exposes.

The underlying differences come down to four structural axes: **how data is replicated**, **what consistency guarantee is offered**, **how nodes find each other**, and **how data is partitioned across nodes**. Read this cheatsheet once and those four lenses will guide every future database decision.

---

## The Concept

### The Four Axes

#### 1. Replication Style

Replication determines where writes land and how they propagate.

```
Leader-Follower (single-leader)
─────────────────────────────
Client ──▶ Leader ──▶ Follower 1
                 └──▶ Follower 2
Writes go to the leader. Followers replay the log.
Reads can hit leader (strong) or followers (stale risk).

Leaderless (peer-to-peer / Dynamo-style)
─────────────────────────────────────────
Client ──▶ Node A  (write)
       ──▶ Node B  (write)
       ──▶ Node C  (write)
Any node accepts writes. Reads repair stale replicas.
No single point of failure, but conflict resolution needed.

Multi-Leader (active-active)
─────────────────────────────
Client 1 ──▶ Leader A  ◀──▶  Leader B ◀── Client 2
Each datacenter has a leader. Leaders sync asynchronously.
Conflicts possible; last-write-wins or CRDT resolution used.
```

#### 2. Consistency Protocol

This is what the client observes after a write, under normal operation and under partition.

| Protocol | Guarantee | Trade-off |
|---|---|---|
| **Strong / Linearizable** | Every read sees the latest write | Higher latency; requires quorum or single leader |
| **Sequential** | All nodes see writes in the same order, not necessarily instantly | Slightly weaker; used by ZooKeeper |
| **Causal** | Causally related ops are ordered; concurrent ops may diverge | Good for collaborative apps |
| **Eventual** | Replicas will converge, but reads may be stale | Lowest latency; conflict resolution required |
| **Tunable** | Client specifies R+W > N for strong, or drops below for speed | Cassandra / DynamoDB model |

#### 3. Node Discovery

How nodes join the cluster and how clients find the right node.

- **Gossip protocol** — each node periodically exchanges membership state with a random peer. Scales to thousands of nodes, eventually consistent about topology. Used by Cassandra, ScyllaDB, Riak.
- **Raft / Paxos consensus** — a quorum of nodes elects a leader and maintains a strongly consistent log of membership changes. Used by etcd, ZooKeeper, FoundationDB.
- **Central coordinator** — ZooKeeper or etcd itself acts as the source of truth for cluster membership in databases like HBase and Kafka.
- **Proprietary managed** — the cloud provider handles discovery completely (DynamoDB, Firestore, CosmosDB).

#### 4. Partitioning Approach

How the keyspace is split across nodes.

```
Consistent Hashing (ring model)
───────────────────────────────
        N0
      /    \
    N3      N1
      \    /
        N2
Each node owns a range on the hash ring. Adding/removing
a node shifts responsibility for only a fraction of keys.
Used by: Cassandra, ScyllaDB, Riak, DynamoDB, Couchbase.

Range-Based Partitioning
───────────────────────────────
| Keys A-M → Node 1 | Keys N-Z → Node 2 |
Enables efficient range scans. Risks hotspots on sequential keys.
Used by: HBase, FoundationDB, MongoDB (with range shard key).

Hash Partitioning (fixed buckets)
───────────────────────────────
hash(key) % num_shards → shard ID
Simple; requires resharding (data migration) when shard count changes.
Used by: Redis Cluster (hash slots, 16384 total).
```

---

## Build It / In Depth

### The Comparison Table

This table maps 15 stores across the four axes. Several entries are included because they handle key-value workloads in practice even if they are not pure KV engines.

| Store | Replication Style | Consistency | Node Discovery | Partitioning |
|---|---|---|---|---|
| **Redis** | Leader-Follower (Cluster: sharded leaders) | Eventual (async replication); strong on primary | Gossip (Redis Cluster bus) | Hash slots (16,384 fixed slots) |
| **Cassandra** | Leaderless (peer-to-peer) | Tunable (ANY / ONE / QUORUM / ALL) | Gossip (Scuttlebutt) | Consistent hashing + virtual nodes |
| **DynamoDB** | Multi-AZ leader-follower (managed) | Eventual default; strongly consistent opt-in per read | Proprietary managed | Consistent hashing (managed) |
| **ScyllaDB** | Leaderless (Cassandra-compatible) | Tunable (same as Cassandra) | Gossip | Consistent hashing + virtual nodes |
| **Riak** | Leaderless (Dynamo-inspired) | Tunable (R, W, N quorums) | Gossip | Consistent hashing |
| **Couchbase** | Leader-Follower per vBucket (active/replica) | Eventual; strong via SDK durability | Gossip-like (Erlang distribution) | Consistent hashing (1,024 vBuckets) |
| **CouchDB** | Multi-Leader (multi-master) | Eventual (MVCC; revision-based) | Gossip-like | Consistent hashing (Ringo-style) |
| **HBase** | Leader-Follower (RegionServer + WAL) | Strong (single RegionServer owns a region) | ZooKeeper | Range-based (Regions) |
| **MongoDB** | Leader-Follower (Replica Set) | Strong by default (primary reads); tunable | Raft-like election (replica set protocol) | Range or hash (shard key) |
| **FoundationDB** | Multi-Paxos | Strong (ACID; serializable) | Coordinator processes (Paxos) | Range-based |
| **etcd** | Leader-Follower (Raft) | Strong (linearizable) | Raft peer list (static or dynamic) | None (single cluster, no sharding) |
| **ZooKeeper** | Leader-Follower (Zab — Paxos variant) | Sequential (ZooKeeper sequential consistency) | Quorum config (static membership) | None (single ensemble) |
| **CosmosDB** | Multi-region active-active or active-passive (managed) | Five levels: strong → bounded staleness → session → consistent prefix → eventual | Proprietary managed | Hash partitioning (logical + physical) |
| **Firestore** | Multi-region (managed, Spanner-derived) | Strong within a session; external consistency opt-in | Proprietary managed | Collection-based (managed) |
| **Neo4j** | Leader-Follower (Causal Clustering, Raft) | Causal (bookmarks ensure read-your-writes) | Raft discovery | None (graph; not key-partitioned) |

### Decision Procedure

Use this flowchart to narrow your choice in under two minutes.

```
Need ACID transactions across keys?
  YES → FoundationDB
  NO  ↓

Need coordination / distributed locks / leader election only?
  YES → etcd or ZooKeeper
  NO  ↓

Need sub-millisecond latency, data fits in RAM?
  YES → Redis
  NO  ↓

Need multi-region active-active with tunable consistency?
  YES → Cassandra / ScyllaDB  (self-managed)
        DynamoDB / CosmosDB   (managed cloud)
  NO  ↓

Need strong consistency + range scans + Hadoop ecosystem?
  YES → HBase
  NO  ↓

Need document model with flexible schema?
  YES → MongoDB, Couchbase, Firestore, CouchDB
  NO  ↓

General key-value, cloud-managed?
  → DynamoDB (AWS), Firestore (GCP), CosmosDB (Azure)

General key-value, self-managed?
  → Cassandra or ScyllaDB
```

---

## Use It

### When to Reach for Each Category

| Workload | Recommended Store | Why |
|---|---|---|
| Session store, rate limiting, pub/sub | Redis | In-memory speed; rich data structures (sorted sets, streams) |
| Global leaderboard, time-series counters | Redis (sorted sets) | O(log N) rank queries built-in |
| Distributed config, service discovery | etcd, ZooKeeper | Strong consistency; watch API for change notification |
| High-throughput write-heavy (IoT, logs) | Cassandra, ScyllaDB | Leaderless; write to any node; linear scale |
| Serverless / managed cloud KV | DynamoDB, Firestore | No ops; auto-scaling; pay-per-request |
| Multi-cloud or multi-region SLA | CosmosDB | Five consistency levels; global distribution built-in |
| Analytics on HBase (OLAP layer) | HBase + Phoenix | Range scans over row keys; integrates with Hadoop/Spark |
| Offline-first mobile / sync | CouchDB, Firestore | Multi-master replication and conflict resolution to edge |
| ACID multi-key transactions | FoundationDB | Only KV store with serializable ACID at scale |

### Consistency Level Quick Reference (Cassandra / DynamoDB Tunable Model)

In a cluster of N replicas, a write goes to W nodes and a read consults R nodes.

- **Strong consistency**: R + W > N (e.g., N=3, W=2, R=2 → 2+2=4 > 3)
- **Eventual consistency**: R + W ≤ N (e.g., N=3, W=1, R=1)
- Raising W hurts write throughput; raising R hurts read throughput. This is the core trade-off.

---

## Common Pitfalls

- **Using Redis as a primary database without persistence configured.** Redis defaults to no persistence (`noSave`). A restart drops all data. Enable `appendonly yes` (AOF) for durability or `RDB` snapshots — and understand that even AOF may lose the last second of writes on crash.

- **Assuming Cassandra quorum reads are always fresh.** If a write only reached W=1 nodes and you read with R=1, you can read stale data even with `QUORUM` configured — because `QUORUM` means majority of the *replica factor*, not all nodes. Always verify your N, R, W math matches your replication factor.

- **Using etcd or ZooKeeper as a general-purpose data store.** Both are designed for small, infrequently changing coordination data (< a few GB). Storing application payload in etcd causes Raft log bloat, slow compaction, and leader instability. Store only pointers or config; keep bulk data in a separate store.

- **Ignoring cross-partition transaction limits in DynamoDB.** DynamoDB transactions (`TransactWriteItems`) span up to 25 items but must complete within 10 seconds and add ~2x read/write cost. Designing schemas that require frequent cross-partition transactions kills both performance and cost efficiency.

- **Conflating "high availability" with "strong consistency."** Leaderless stores (Cassandra, Riak) are highly available under network partition but sacrifice consistency by default. Leader-based stores (etcd, HBase) maintain consistency but the leader becomes unavailable during re-election. CAP theorem is not optional — know which side your store is on.

---

## Exercises

1. **Easy** — Take the comparison table in this lesson and highlight in green every store that offers *tunable* consistency and uses *gossip* for node discovery. What do all the highlighted stores have in common architecturally?

2. **Medium** — You are building a feature flag system that must serve flags with < 5 ms latency, survive the loss of one datacenter, and guarantee that a flag disabled by an operator is never served as enabled after the disable propagates. Which store(s) from this cheatsheet would you use? Justify your R, W, N settings or your consistency level choice.

3. **Hard** — FoundationDB offers serializable ACID transactions over a distributed key-value store. Cassandra offers tunable consistency but no multi-key transactions. Explain the architectural reason Cassandra cannot offer ACID transactions without a fundamentally different design. Then describe what you would layer on top of Cassandra (external components or protocols) to approximate multi-key atomic writes, and what trade-offs those approaches introduce.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Eventual consistency** | The database is eventually broken | Replicas will converge to the same value *if* writes stop; reads may be temporarily stale, but no data is lost |
| **Leaderless replication** | No coordination happens | Any node accepts writes; the cluster uses quorums and read-repair/anti-entropy to converge without a designated primary |
| **Virtual nodes (vnodes)** | An abstraction over physical nodes | Multiple small token ranges assigned to each physical node; improves load balance during node addition/removal without full resharding |
| **Gossip protocol** | Nodes gossip = unreliable metadata | A scalable, self-healing epidemic protocol where each node shares state with a random peer every heartbeat interval; O(log N) convergence |
| **Tunable consistency** | You can get both consistency and availability | You shift the trade-off: stronger consistency costs latency/availability; weaker consistency costs correctness. CAP still applies |
| **Strong consistency (linearizability)** | Reads always return the latest write | Every read observes a result consistent with a single total order of operations; requires coordination (quorum or single writer) |
| **Consistent hashing** | All hashing algorithms are consistent | A specific scheme where adding/removing a node reassigns only `keys / N` keys instead of rehashing the entire dataset |

---

## Further Reading

- [Dynamo: Amazon's Highly Available Key-value Store (2007 SOSP paper)](https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf) — the blueprint for leaderless, tunable-consistency KV stores; Cassandra, Riak, and DynamoDB all trace their lineage here.
- [etcd documentation — data model and clustering](https://etcd.io/docs/v3.5/learning/data_model/) — concise explanation of the Raft-based KV model and why etcd is suited for coordination, not general storage.
- [Apache Cassandra Architecture Guide](https://cassandra.apache.org/doc/latest/cassandra/architecture/overview.html) — official deep-dive on gossip, consistent hashing with vnodes, and the tunable consistency model.
- [FoundationDB: A Distributed Unbundled Transactional Key Value Store (2021 SIGMOD paper)](https://www.foundationdb.org/files/fdb-paper.pdf) — explains how ACID transactions are achieved over a distributed KV layer using a separation of storage and transaction management.
- [Martin Kleppmann, *Designing Data-Intensive Applications*, Chapter 5–7](https://dataintensive.net/) — the definitive reference on replication, partitioning, and consistency models across all database categories covered in this lesson.
