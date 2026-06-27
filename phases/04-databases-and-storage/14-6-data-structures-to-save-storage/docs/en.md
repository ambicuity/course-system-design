# 6 Data Structures to Save Storage

> Approximate answers that fit in kilobytes beat exact answers that require gigabytes.

**Type:** Learn
**Prerequisites:** Hashing fundamentals, basic probability, database indexing
**Time:** ~35 minutes

---

## The Problem

A URL-shortening service needs to check whether a new alias already exists before inserting it. A naive approach queries the database on every write. At 100,000 writes per second, that is 100,000 synchronous reads hitting disk — expensive, slow, and wasteful when the majority of those reads return "not found."

A streaming analytics platform needs to count how many distinct users visited a page today. Storing every user ID in a set and counting at query time works fine at 10,000 users. At 500 million daily active users across 10 million pages, the memory alone would be in the hundreds of terabytes.

A recommendation engine needs to surface content similar to what a user has already seen. Comparing every piece of content pairwise across a catalog of 100 million documents would require quadrillions of comparisons.

These are not exotic edge cases — they are the everyday reality of systems at scale. The six data structures in this lesson attack the same root problem: **exact computation is too expensive, but approximate computation with bounded error is often good enough and orders of magnitude cheaper**. Understanding when to trade exactness for efficiency, and which structure to reach for, is a core system design skill.

---

## The Concept

All six structures exploit the same insight: you can often represent a set, a count, or a similarity value in a tiny fixed-size structure by allowing a controlled, quantifiable error. The trade-off is always:

| Property | Exact structure | Probabilistic structure |
|---|---|---|
| Memory | O(n) — grows with data | O(1) or O(log n) — nearly fixed |
| Error | Zero | Bounded and tunable |
| Deletions | Always supported | Often not |
| Speed | Varies | Usually O(1) or O(log n) |

Here is an overview before diving into each:

```
Problem               Structure          Error Type
─────────────────────────────────────────────────────────────
"Is X in the set?"   Bloom Filter        False positives only
"Is X in the set?"   Cuckoo Filter       False positives only
                     (+ supports delete)
"How many unique?"   HyperLogLog         ±0.81% at 12 KB
"How similar?"       MinHash             Jaccard approx
"How frequent?"      Count-Min Sketch    Overcount only
"Find fast in DB"    SkipList            No error (exact)
```

SkipList is the odd one out — it is not probabilistic. It saves on *implementation complexity* rather than memory, but it earns its place here because it is the backbone of sorted indexes in Redis and LevelDB.

---

### 1. Bloom Filter

A Bloom filter answers the question "have I seen this element before?" using a **bit array of size m** and **k independent hash functions**.

**Insert:** Hash the element with all k functions, set those k bit positions to 1.
**Query:** Hash the element with all k functions. If any bit is 0 → definitely not in the set. If all bits are 1 → probably in the set (false positive possible).

```
Bit array (m=16 bits):  0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
Insert "alice" (k=3):         ↓       ↓           ↓
                        0 0 0 1 0 0 0 1 0 0 0 0 0 1 0 0
Insert "bob"   (k=3):     ↓       ↓     ↓
                        0 1 0 1 0 0 0 1 0 1 0 0 0 1 0 0

Query "carol":  bits at her 3 positions → one is 0 → NOT IN SET (certain)
Query "dave":   bits at his 3 positions → all 1 (collision) → MAYBE IN SET
```

**False positive rate** is approximately `(1 - e^(-kn/m))^k` where n is elements inserted. At 1% FPR, a Bloom filter needs about 9.6 bits per element — versus 32–64 bits for storing the actual ID.

**Key property:** No false negatives. If the filter says "not present," it is definitively absent.

---

### 2. Cuckoo Filter

A Cuckoo filter stores **fingerprints** (short hashes, e.g., 8 bits) in a compact hash table with **two candidate buckets per item**, using cuckoo-hashing displacement on collision.

**Why it beats Bloom for many use cases:**
- Supports **deletion** (Bloom does not — you cannot unset bits safely)
- Better **cache locality** (accesses exactly 2 buckets per lookup)
- Lower false-positive rate at the same space: ~12 bits per item at 0.1% FPR vs. Bloom's ~15 bits

```
Cuckoo filter (2 buckets per slot, fingerprint = fp):
                 Bucket A        Bucket B
Item "alice":    fp(alice) at h1(alice)  OR  fp(alice) at h2(alice)

Lookup:  compute fp, check h1 and h2. Found in either → maybe present.
Delete:  find fp in h1 or h2, clear it. ✓
```

Use Cuckoo filters when you need deletion (e.g., cache invalidation lists, ephemeral membership).

---

### 3. HyperLogLog

HyperLogLog estimates the **cardinality** (number of distinct elements) of a multiset. The core intuition: if you hash elements to uniformly random bit strings, the probability that the longest run of leading zeros you observe is ≥ k is `1/2^k`. Observing many elements, the maximum leading-zero run grows as `log2(n)`.

HyperLogLog uses `m` registers (sub-streams via the leading bits of the hash) and combines their estimates using a harmonic mean, giving ~1.04/√m relative error.

```
Hash space (binary):
  "user_001" → 0b00011010...   leading zeros = 3
  "user_002" → 0b10101100...   leading zeros = 0
  "user_003" → 0b00001101...   leading zeros = 4

Max leading zeros seen across all hashes ≈ log2(distinct count)
```

**Real numbers:**
- 12 KB memory → 16,384 registers → ±0.81% error over billions of distinct values
- Redis `PFADD` / `PFCOUNT` implement HyperLogLog with a 12 KB cap
- Merging two HyperLogLogs gives cardinality of their union — critical for distributed analytics

---

### 4. MinHash (Min-Wise Hashing)

MinHash estimates **Jaccard similarity** between two sets: `|A ∩ B| / |A ∪ B|`.

The key theorem: for a random hash function h, `P(min(h(A)) == min(h(B))) = Jaccard(A, B)`.

By applying k independent hash functions and comparing the k minimum values (a **signature**), you estimate Jaccard with variance 1/k.

```
Set A = {apple, banana, cherry}
Set B = {banana, cherry, durian}

True Jaccard = |{banana, cherry}| / |{apple, banana, cherry, durian}| = 2/4 = 0.5

Signature (k=4 hash functions):
  h1: min(A)=banana, min(B)=banana  → match
  h2: min(A)=apple,  min(B)=cherry  → no match
  h3: min(A)=cherry, min(B)=banana  → no match
  h4: min(A)=cherry, min(B)=cherry  → match

Estimated Jaccard = 2/4 = 0.5  ✓
```

In practice, MinHash signatures are used with **Locality-Sensitive Hashing (LSH)** to bucket similar documents for near-duplicate detection — reducing O(n²) pairwise comparisons to near-linear work.

---

### 5. SkipList

A SkipList is a **layered linked list** where each level is a randomly subsampled version of the level below, providing O(log n) expected time for search, insert, and delete.

```
Level 3:  head ────────────────────────── 50 ──────── tail
Level 2:  head ──── 10 ──────── 30 ────── 50 ── 70 ── tail
Level 1:  head ──── 10 ─── 20 ─ 30 ── 40 ─ 50 ─ 60 ─ 70 ── tail
Level 0:  head  5 ─ 10 ─ 15 ─ 20 ─ 25 ─ 30 ─ 35 ─ 40 ─ 45 ─ 50 ─...
```

Search starts at the highest level and drops down only when the next node exceeds the target — a "highway" analogy.

**Why SkipLists instead of balanced BSTs?**
- Simpler concurrent implementation: lock-free SkipLists are well-understood; lock-free red-black trees are notoriously complex
- Easier range scans (pointer-linked levels)
- Redis uses SkipLists for sorted sets (`ZADD`, `ZRANGE`, `ZRANGEBYSCORE`)
- LevelDB/RocksDB use SkipLists for in-memory memtables

Each node is promoted to the next level with probability p (usually 0.5 or 0.25). Expected space is O(n).

---

### 6. Count-Min Sketch

Count-Min Sketch tracks **approximate frequencies** of items in a high-velocity stream using a 2D array of counters with d hash functions and w counters per row.

**Insert(item, count):** For each row i, increment `table[i][h_i(item)]` by count.
**Query(item):** Return `min over i of table[i][h_i(item)]`.

```
d=3 hash functions, w=8 counters each:

Row 0:  [ 0, 3, 0, 1, 2, 0, 4, 1 ]
Row 1:  [ 1, 0, 5, 0, 1, 3, 0, 2 ]
Row 2:  [ 2, 1, 0, 4, 0, 1, 3, 0 ]

Query "nginx" maps to positions [1, 2, 5] → min(3, 5, 1) = 1

True count might be 1; sketch never undercounts, may overcount due to hash collisions.
```

Error bound: with probability ≥ 1 − δ, the estimate exceeds the true count by at most `ε × N`, where N is total stream weight, ε ≈ e/w, δ ≈ e^(−d).

A 100×8 sketch (800 counters × 4 bytes = 3.2 KB) can track top-k URLs in a billion-request log stream.

---

## Build It / In Depth

### Worked Example: Deduplicating a Web Crawler

Suppose you are crawling 10 billion URLs. You need to avoid re-crawling URLs you have already seen. Storing 10 billion URLs verbatim (average 50 bytes each) = 500 GB. A Bloom filter at 10 bits per element = 12.5 GB — and most of that fits in RAM.

**Python sketch using `pybloom-live`:**

```python
from pybloom_live import BloomFilter

# 1% false positive rate, 10 billion expected items
bf = BloomFilter(capacity=10_000_000_000, error_rate=0.01)

def should_crawl(url: str) -> bool:
    if url in bf:
        return False   # probably already seen
    bf.add(url)
    return True        # definitely new

# False positive consequence: we skip ~1% of valid new URLs.
# False negative: impossible — we never re-crawl a seen URL.
```

**Choosing m and k:**

```
Optimal k = (m/n) * ln(2)
At 1% FPR:  m ≈ 9.6 * n  bits
At 0.1% FPR: m ≈ 14.4 * n bits

10B URLs at 1% FPR:
  m = 9.6 × 10^10 bits = 12 GB
  k = 7 hash functions
```

**Counting unique visitors with HyperLogLog (Redis):**

```bash
# Track unique visitors per page
redis-cli PFADD page:home:2024-06-26 user123 user456 user789
redis-cli PFADD page:home:2024-06-26 user123  # duplicate, ignored

redis-cli PFCOUNT page:home:2024-06-26
# → 3  (±0.81% error)

# Merge across shards (additive)
redis-cli PFMERGE site:total:2024-06-26 page:home:2024-06-26 page:about:2024-06-26
redis-cli PFCOUNT site:total:2024-06-26
```

**Count-Min Sketch for heavy hitter detection:**

```python
import hashlib, array, math

class CountMinSketch:
    def __init__(self, width=2048, depth=5):
        self.w = width
        self.d = depth
        self.table = [[0] * width for _ in range(depth)]
        self.seeds = [i * 2654435761 for i in range(depth)]

    def _hash(self, item: str, seed: int) -> int:
        h = int(hashlib.md5(f"{seed}{item}".encode()).hexdigest(), 16)
        return h % self.w

    def add(self, item: str, count: int = 1):
        for i, seed in enumerate(self.seeds):
            self.table[i][self._hash(item, seed)] += count

    def query(self, item: str) -> int:
        return min(
            self.table[i][self._hash(item, seed)]
            for i, seed in enumerate(self.seeds)
        )

cms = CountMinSketch()
for event in ["GET /api/search", "GET /api/search", "POST /login", "GET /api/search"]:
    cms.add(event)

print(cms.query("GET /api/search"))  # → 3 (exact or slight overcount)
```

---

## Use It

| Structure | Real Systems | Typical Use Case |
|---|---|---|
| **Bloom Filter** | Cassandra, HBase, PostgreSQL, Akamai CDN | Pre-filter disk lookups, block-list checks, cache membership |
| **Cuckoo Filter** | CloudFlare, custom CDN layers | Same as Bloom, plus deletion needed (TTL-based sets) |
| **HyperLogLog** | Redis (`PFADD`), BigQuery, Presto, Druid | Unique visitor counts, A/B test reach, cardinality in analytics |
| **MinHash + LSH** | Google Crawler dedup, Spotify, Pinterest | Near-duplicate detection, content recommendation, entity resolution |
| **SkipList** | Redis Sorted Sets, LevelDB memtable, MemSQL | Range queries, leaderboards, time-series ordering |
| **Count-Min Sketch** | Flink, Kafka Streams, Twitter trending | Top-K queries, DDoS source detection, rate limiting by key |

**Decision guide:**

```
Need to check set membership?
  ├── Deletes required?   → Cuckoo Filter
  └── No deletes?         → Bloom Filter

Need to count distinct values?             → HyperLogLog

Need to measure similarity between sets?   → MinHash

Need to count item frequencies in streams? → Count-Min Sketch

Need a sorted in-memory index?             → SkipList
```

---

## Common Pitfalls

- **Over-filling a Bloom filter.** The false-positive rate degrades sharply once insertions exceed the design capacity. Always set capacity to 2× your P90 estimate, or use a scalable Bloom filter that allocates new layers when full. Monitor fill ratio in production.

- **Assuming HyperLogLog merges work across different precisions.** Redis `PFMERGE` requires all HyperLogLogs to use the same number of registers. If you mix encodings (sparse vs. dense) without understanding the threshold, estimates silently degrade.

- **Using Count-Min Sketch for negative-count streams.** CMS assumes non-negative increments. Decrements break the overcount guarantee. Use a conservative update variant or a separate CMS for deletions.

- **Forgetting MinHash requires the same hash family across services.** If two services independently compute MinHash signatures with different seeds, their signatures are incompatible. Fix seeds in a shared config and version them.

- **Treating SkipList level probability p as a tuning knob without understanding the memory trade-off.** p=0.5 gives O(2n) expected pointers; p=0.25 gives O(1.33n) with slower expected search at small n. Redis hardcodes p=0.25 and max level 32 — copy this default unless you have strong evidence otherwise.

---

## Exercises

1. **Easy:** A Bloom filter is configured with m=1,000,000 bits and k=7 hash functions. After inserting n=100,000 elements, estimate the false positive rate using the formula `(1 − e^(−kn/m))^k`. What does the FPR become at n=200,000?

2. **Medium:** You are designing a rate limiter for an API that allows 100 requests per minute per user. You have 1 million active users, and tracking exact counts per user costs too much memory. Describe how you would combine a Count-Min Sketch with a sliding-window counter. What error guarantees can you give, and what is the worst-case false-throttle scenario?

3. **Hard:** A social network wants to detect near-duplicate posts (spam) in real time as posts arrive. Posts are sets of word tokens. Design a pipeline using MinHash + LSH that: (a) generates a signature per post, (b) identifies candidates with Jaccard ≥ 0.8, and (c) stores only signatures — not raw posts — for membership lookups. Estimate the memory and latency of your design at 10,000 posts per second with a vocabulary of 500,000 tokens.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **False positive** | A bug in the filter | An intentional trade-off: the filter says "present" but the element was never inserted. Rate is bounded and tunable. |
| **False negative** | The symmetric opposite of a false positive | Bloom and Cuckoo filters guarantee zero false negatives — "not present" is always correct. |
| **Cardinality** | Just "count" | The number of **distinct** elements in a multiset; HyperLogLog estimates this, not total element count. |
| **Jaccard similarity** | A fuzzy equality score | `|A ∩ B| / |A ∪ B|` — the ratio of shared elements to all elements across both sets. Ranges 0 (disjoint) to 1 (identical). |
| **Hash collision** | Something to eliminate | In Count-Min Sketch, controlled collisions are the mechanism; the overcount error they introduce is bounded by the sketch dimensions. |
| **Fingerprint (Cuckoo)** | The full key | A short hash (e.g., 8 bits) of the key stored in the table — not the key itself. Multiple keys can share a fingerprint (false positive source). |
| **Register (HyperLogLog)** | A database register | One of m sub-estimators, each tracking the max leading-zero run for a subset of hashed elements. More registers → lower error. |

---

## Further Reading

- [Redis HyperLogLog documentation](https://redis.io/docs/data-types/probabilistic/hyperloglogs/) — official reference with complexity guarantees and merge semantics
- [Cuckoo Filter paper — Fan et al., 2014 (CMU)](https://www.cs.cmu.edu/~dga/papers/cuckoo-conext2014.pdf) — the original paper with benchmarks against Bloom filters
- [Mining of Massive Datasets, Ch. 3 — Leskovec, Rajaraman, Ullman](http://www.mmds.org/) — authoritative textbook covering MinHash, LSH, Bloom filters, and stream algorithms with derivations
- [Stream-lib (Java)](https://github.com/addthis/stream-lib) — production implementations of HyperLogLog, Count-Min Sketch, Bloom filters used at scale
- [Probabilistic Data Structures for Web Analytics and Data Mining — Sergiy Matusevych](https://highlyscalable.wordpress.com/2012/05/01/probabilistic-structures-web-analytics-data-mining/) — practical engineering blog post that bridges theory to real deployments
