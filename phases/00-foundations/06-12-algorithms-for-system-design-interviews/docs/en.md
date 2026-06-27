# 12 Algorithms for System Design Interviews

> The right algorithm is a force multiplier — choose the wrong one at scale and no amount of hardware rescues you.

**Type:** Learn
**Prerequisites:** CAP Theorem, Consistent Hashing basics, Distributed Systems overview
**Time:** ~45 minutes

---

## The Problem

Most system design interviews fail at the same point: the candidate picks the simplest data structure (a hash set, a SQL row, a flat list) and then discovers it collapses at the scale the interviewer specifies. "Count unique visitors across 10 billion requests per day" — a standard `Set` would need hundreds of gigabytes of RAM. "Find all restaurants within 5 km of a user" — a naive lat/lng scan of millions of rows is a full table scan on every request. "Ensure two data center replicas agree on the same log entry" — without a formal consensus protocol, you get split-brain.

The 12 algorithms in this lesson are the interviewer's vocabulary for stress-testing your designs. Each one solves a class of problem that naive approaches cannot handle at production scale. They appear across distributed caching, location services, analytics pipelines, rate limiters, file sync, real-time collaboration, and consensus systems. Knowing them lets you name and justify choices rather than fumbling toward an ad-hoc approximation.

This lesson gives you the mental model, the mechanics, and the real-world wiring for each one so you can both explain them clearly and know exactly when to reach for them.

---

## The Concept

### 1. Bloom Filter

A **Bloom filter** is a probabilistic data structure that answers "Is this item in the set?" in O(1) time and O(1) space per item — at the cost of a tunable false-positive rate and no false negatives.

```
Insert "user-42":
  h1("user-42") = 3  →  bit[3] = 1
  h2("user-42") = 7  →  bit[7] = 1
  h3("user-42") = 12 →  bit[12] = 1

Query "user-99":
  h1("user-99") = 3  →  bit[3] = 1  ✓
  h2("user-99") = 5  →  bit[5] = 0  ✗  → definitely NOT in set
```

**Why it works:** k independent hash functions map each element to k bit positions in a fixed-size bit array. A query is "possibly present" only if all k bits are set. A zero bit is conclusive proof of absence. The false-positive rate is `(1 - e^(-kn/m))^k` where n = elements inserted, m = bit array size. You tune m and k to hit your target error rate.

**Trade-offs:** No deletions (use Counting Bloom Filter for that). False positives exist but are bounded. Extremely memory-efficient — storing 1 billion items with a 1% FP rate needs ~1.2 GB vs. ~32+ GB for a hash set of 64-bit integers.

---

### 2. Geohash

**Geohash** encodes a latitude/longitude pair into a short alphanumeric string by recursively subdividing the Earth's surface into rectangular cells.

```
Precision 6:  "u4pruyd"  → ~1.2 km × 0.6 km cell
Precision 5:  "u4pru"    → ~4.9 km × 4.9 km cell
Precision 4:  "u4pr"     → ~39 km × 20 km cell
```

Strings that share a prefix are spatially close (with one caveat: cells straddling a prefix boundary can be far apart — always query the 8 neighbors too). Geohash enables proximity queries with nothing more than a string prefix index.

---

### 3. HyperLogLog

**HyperLogLog (HLL)** estimates the cardinality of a set (count of distinct elements) using only ~1.5 KB of memory with a 2% standard error, regardless of how large the actual cardinality is.

**Core idea:** Hash each element to a binary string. Record the position of the leftmost `1` bit (a proxy for "how many leading zeros"). The maximum leading-zero count across all elements estimates log₂(n). Divide the input into m subsets (registers) and average their estimates (HyperLogLog) for accuracy.

| Memory | Max cardinality | Error |
|--------|----------------|-------|
| 1.5 KB | 10^18          | ~2%   |
| 12 KB  | 10^18          | ~0.7% |

Redis implements `PFADD` / `PFCOUNT` on top of HyperLogLog.

---

### 4. Consistent Hashing

In a plain hash ring, adding or removing a node remaps ~n/N fraction of keys (where N is the number of nodes). **Consistent hashing** reduces this to ~k/N keys moved when a node is added or removed (k = keys on that node).

```
Hash ring (0 – 2^32):

        0
     /     \
  N-C       N-A
    \       /
      N-B
       |
  Items hash to the next clockwise node.
  Remove N-B → only N-B's keys move to N-C.
```

Virtual nodes (vnodes) per physical node flatten the distribution and allow heterogeneous capacity.

---

### 5. Merkle Tree

A **Merkle tree** is a binary tree of cryptographic hashes where each leaf is the hash of a data block and each internal node is the hash of its children. The root hash summarizes the entire dataset.

```
        Root
       /    \
    H(AB)  H(CD)
    /  \   /  \
  H(A) H(B) H(C) H(D)
```

To sync two replicas, exchange root hashes. If they differ, recurse left/right until you find the differing leaves — O(log n) messages instead of O(n) data transfer. Used heavily in Git, Bitcoin, DynamoDB anti-entropy.

---

### 6. Raft Algorithm

**Raft** is a consensus algorithm for replicated logs. It decomposes consensus into three sub-problems:

1. **Leader election** — nodes vote; a majority elects one leader per term.
2. **Log replication** — the leader accepts writes, replicates to followers, commits once a majority acknowledges.
3. **Safety** — a committed entry is never lost; a new leader always has the most up-to-date log.

Key property: only the leader handles writes, which eliminates write conflicts. A leader failure triggers a new election (typically in 150–300 ms).

---

### 7. Lossy Count

**Lossy Count** finds "heavy hitters" — items whose frequency exceeds a threshold ε·N (where N is the stream length) — using bounded memory without storing every distinct item.

The stream is divided into windows of size ⌈1/ε⌉. Each item's estimated count carries a maximum undercount error of 1. At any time, only items with `count + error ≥ threshold · N` are retained. Memory bound: O(1/ε · log(ε·N)).

---

### 8. QuadTree

A **QuadTree** recursively divides 2-D space into four equal quadrants until each cell contains at most a fixed number of points.

```
+--------+--------+
|        |  ●   ● |
|        |        |
+--------+--------+
|   ●    |        |
|        |   ●    |
+--------+--------+
```

Proximity search: descend to the leaf containing the query point, then expand outward. Much faster than a 2-D full scan. Good for sparse point data; R-trees are preferred for polygon/region data.

---

### 9. Operational Transformation (OT)

**Operational Transformation** enables concurrent edits to a shared document without locking. Each edit is an operation (Insert at position i / Delete at position i). When two operations are concurrent, OT transforms them against each other so both can be applied in any order and produce the same result.

```
Doc: "hello"
User A: Insert(" world", 5)  → "hello world"
User B: Insert("!", 5)       → "hello!"

Transform B against A: Insert("!", 11)
Apply both → "hello world!"  ✓ (converges)
```

Used in Google Docs (historically). Modern systems often use **CRDTs** instead, but OT remains common in real-time collaboration stacks.

---

### 10. Leaky Bucket

The **Leaky Bucket** algorithm models a bucket of fixed capacity `B` that leaks at a constant rate `R`. Requests fill the bucket; if the bucket is full, the request is dropped or queued.

```
Incoming requests: burst of 100 rps
Bucket capacity: 50
Leak rate: 20 rps

  → Excess 80 rps discarded; output is smooth 20 rps
```

Guarantees a smooth output rate regardless of input burstiness. Compare with **Token Bucket**: allows short bursts up to bucket size, then throttles.

| Algorithm    | Burst allowed? | Output shape |
|--------------|---------------|--------------|
| Leaky Bucket | No            | Constant rate |
| Token Bucket | Yes (burst ≤ B) | Average rate |

---

### 11. Rsync Algorithm

**Rsync** minimizes data transferred when synchronizing files between two hosts. The receiver splits the file into fixed-size blocks, computes a weak checksum (rolling Adler-32) and a strong checksum (MD5) for each block. The sender rolls the weak checksum across the file byte-by-byte; when it matches a receiver block, the strong checksum confirms it. The sender transmits only new data plus a recipe of matching block references. Typically achieves 80–95% reduction in transfer volume for large, mostly-unchanged files.

---

### 12. Ray Casting

**Ray Casting** determines whether a point P is inside a polygon by casting a ray from P in any direction and counting how many polygon edges it crosses. An **odd** count means inside; **even** means outside (Jordan curve theorem).

```
      ___
     /   \
  --+--P--+---→   ray crosses 2 edges → P is INSIDE
     \___/
```

Used in GIS (point-in-polygon queries), game collision detection, and map feature lookup ("which country is this coordinate in?").

---

## Build It / In Depth

### Bloom Filter: Sizing in Practice

Given target false-positive rate `p` and expected element count `n`, the optimal bit array size is:

```
m = -(n * ln(p)) / (ln(2))^2
k = (m / n) * ln(2)
```

**Example:** Cache miss check for 100 million URLs, 1% FP rate.

```python
import math

n = 100_000_000   # items
p = 0.01          # 1% false positive rate

m = -(n * math.log(p)) / (math.log(2) ** 2)
k = (m / n) * math.log(2)

print(f"Bit array size: {m/8/1024/1024:.1f} MB")   # ~119.1 MB
print(f"Hash functions: {round(k)}")                # 7
```

A Redis `SET` of 100 million 20-byte URLs ≈ 2 GB. The Bloom filter needs only ~120 MB and avoids the disk read entirely when it reports "definitely not present."

---

### Consistent Hashing: Adding a Node

```
Before (3 nodes on ring):
  N-A owns keys [0, 100)
  N-B owns keys [100, 200)
  N-C owns keys [200, 300)

Add N-D at position 150:
  N-B now owns [100, 150)
  N-D now owns [150, 200)  ← only keys in this range moved, nothing else changes
```

With 150 virtual nodes per physical node (common in Cassandra/DynamoDB), the standard deviation of key distribution falls below 5%.

---

### Merkle Tree: Anti-Entropy Sync

```
Replica A:         Replica B:
  Root: H(8f3a)     Root: H(9c12)   ← differ
  Left: H(ab1c)     Left: H(ab1c)   ← same
  Right: H(3d9e)    Right: H(4f2a)  ← differ → only right subtree needs sync
```

DynamoDB and Cassandra run background Merkle tree comparisons between replicas. Without them, detecting divergence would require transferring all data.

---

### Leaky Bucket: Redis Implementation Sketch

```python
import time, redis

r = redis.Redis()

def leaky_bucket(user_id: str, rate: float, capacity: int) -> bool:
    key = f"bucket:{user_id}"
    now = time.time()
    pipe = r.pipeline()

    # Atomic read of last timestamp and current level
    pipe.hmget(key, "ts", "level")
    ts, level = pipe.execute()[0]

    ts    = float(ts or now)
    level = float(level or 0)

    # Drain leaked tokens since last check
    leaked = (now - ts) * rate
    level  = max(0, level - leaked)

    if level + 1 > capacity:
        return False  # drop

    level += 1
    r.hmset(key, {"ts": now, "level": level})
    r.expire(key, int(capacity / rate) + 1)
    return True
```

---

## Use It

| Algorithm             | Where you'll find it                                              |
|-----------------------|-------------------------------------------------------------------|
| Bloom Filter          | Cassandra (SSTable lookup), PostgreSQL (join optimization), CDN cache miss checks |
| Geohash               | Uber/Lyft driver lookup, Yelp search, PostGIS `ST_GeoHash`       |
| HyperLogLog           | Redis `PFCOUNT`, BigQuery `APPROX_COUNT_DISTINCT`, Spark          |
| Consistent Hashing    | DynamoDB, Cassandra, Memcached, Nginx upstream hash               |
| Merkle Tree           | Git, Bitcoin/Ethereum, DynamoDB anti-entropy, IPFS                |
| Raft                  | etcd, CockroachDB, TiKV, Consul, YugabyteDB                      |
| Lossy Count           | Network traffic analysis, Kafka Streams heavy hitter detection    |
| QuadTree              | Google Maps spatial index, PostGIS, Unity/game engines            |
| Operational Transform | Google Docs (legacy), Firepad, ShareDB                           |
| Leaky Bucket          | Nginx rate limit, AWS API Gateway throttling, Envoy proxy         |
| Rsync Algorithm       | `rsync` CLI, Dropbox delta sync, AWS DataSync                    |
| Ray Casting           | GIS point-in-polygon, MaxMind IP geolocation, game hit detection  |

**Decision heuristic:**
- Need probabilistic membership? → **Bloom Filter**
- Need to partition geographic data? → **Geohash** (points) or **QuadTree** (sparse/dynamic points)
- Need distinct count at massive scale? → **HyperLogLog**
- Need to distribute data across a cluster? → **Consistent Hashing**
- Need to compare/sync replicas cheaply? → **Merkle Tree**
- Need distributed consensus on writes? → **Raft** (or Paxos)
- Need to find frequent items in a stream? → **Lossy Count**
- Need collaborative real-time editing? → **OT** or CRDTs
- Need rate limiting with smooth output? → **Leaky Bucket**
- Need efficient file sync? → **Rsync**
- Need point-in-region lookup? → **Ray Casting**

---

## Common Pitfalls

- **Bloom filters cannot delete elements.** Using a standard Bloom filter in a cache eviction path causes phantom positives for evicted keys forever. Use a Counting Bloom Filter or accept and bound the risk with periodic rebuilds.

- **Geohash edge cases at cell boundaries.** Two points 10 meters apart can share zero prefix characters if they straddle a cell boundary. Always query the target cell plus all 8 neighbors. Skipping this makes your "nearby" results silently wrong at boundaries.

- **Confusing Leaky Bucket and Token Bucket.** Interviewers often want burst-tolerance (Token Bucket) but candidates name Leaky Bucket. State which you're using and why — smooth constant output vs. allowed bursting up to capacity are meaningfully different behaviors.

- **Assuming Raft is always fast.** Raft commit latency is bounded by the slowest majority member. In multi-region deployments, a quorum crossing a WAN link adds 50–200 ms per write. Pre-emptively discuss read-from-follower options (`ReadIndex`, lease reads) when the interviewer mentions cross-region.

- **Treating Merkle tree comparison as free.** Building the tree and comparing it is O(n). In large clusters, systems like Cassandra throttle anti-entropy reads to avoid overwhelming nodes. Don't present Merkle sync as an instant zero-cost operation.

---

## Exercises

1. **(Easy)** A URL shortener needs to know whether a short code has ever been used (to avoid re-issuing it). It stores 500 million codes. Size a Bloom filter for a 0.1% false-positive rate. How many bits per element does this require?

2. **(Medium)** Design the backend of a "find nearby drivers" feature for a ride-hailing app. The system must handle 1 million drivers updating their location every 5 seconds and must return drivers within 2 km of a user in under 50 ms. Discuss your choice between Geohash and QuadTree and how you'd store/query the index.

3. **(Hard)** A distributed key-value store uses Consistent Hashing across 20 nodes and Merkle Trees for anti-entropy. A network partition isolates 6 nodes for 30 seconds. Describe the full reconciliation sequence after the partition heals: which nodes initiate comparison, how they traverse the tree, how conflicts are resolved, and what observable behavior a client sees during and after the partition.

---

## Key Terms

| Term | What people think | What it actually means |
|------|-------------------|------------------------|
| Bloom Filter | "A fuzzy hash set" | A bit array + k hash functions; no false negatives, tunable false positives, no deletions |
| Consistent Hashing | "Just hashing with a ring" | A scheme that limits key remapping to O(k/N) when nodes change, using virtual nodes for balance |
| HyperLogLog | "An approximation algorithm" | A cardinality estimator using the max leading-zero position of hashed values; ~2% error with 1.5 KB |
| Raft | "A distributed database protocol" | A consensus algorithm for a replicated log; Raft ≠ a storage engine, it's the agreement layer underneath one |
| Merkle Tree | "A blockchain thing" | A hash tree for efficient subset comparison; used in Git, Dynamo, and Bitcoin for entirely different purposes |
| Leaky Bucket | "Same as Token Bucket" | Enforces a strictly constant output rate; Token Bucket allows short bursts — they are not interchangeable |
| Operational Transformation | "How real-time sync works" | A specific algorithm that transforms concurrent operations so they converge; CRDTs are the modern alternative |

---

## Further Reading

- **Bloom Filter deep dive** — [Network Applications of Bloom Filters (Broder & Mitzenmacher, 2004)](https://www.eecs.harvard.edu/~michaelm/postscripts/im2005b.pdf) — the authoritative survey covering extensions like Counting Bloom Filters.
- **Raft explained** — [In Search of an Understandable Consensus Algorithm (Ongaro & Ousterhout, 2014)](https://raft.github.io/raft.pdf) — the original paper; the [interactive visualization](https://raft.github.io) is the fastest way to build intuition.
- **Consistent Hashing** — [Consistent Hashing and Random Trees (Karger et al., 1997)](https://dl.acm.org/doi/10.1145/258533.258660) — the original DHT paper; also see the DynamoDB 2007 SOSP paper for production virtual-node decisions.
- **HyperLogLog** — [HyperLogLog: the analysis of a near-optimal cardinality estimation algorithm (Flajolet et al., 2007)](http://algo.inria.fr/flajolet/Publications/FlFuGaMe07.pdf) — the foundational paper; Redis's implementation notes extend it with bias correction.
- **System Design Interview Vol. 2 (Alex Xu)** — Chapter on proximity services covers Geohash vs. QuadTree trade-offs with concrete capacity calculations.
