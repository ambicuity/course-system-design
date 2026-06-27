# Design A Search Autocomplete System

## Overview

Autocomplete (also called typeahead or search-as-you-type) shows suggested queries while users type. The challenge is designing a system that retrieves the top-k most popular search queries given a prefix.

---

## Step 1: Problem Definition and Scope

### Clarifying Questions & Answers

| Question | Answer |
|----------|--------|
| Prefix matching location | Beginning of query only |
| Number of suggestions | 5 results |
| Ranking methodology | Historical query frequency (popularity) |
| Spell check support | No |
| Language | English |
| Character constraints | Lowercase alphabetic only |
| User base | 10 million DAU |

### Core Requirements

1. **Speed**: Results within ~100 milliseconds
2. **Relevance**: Suggestions must match the prefix
3. **Ranking**: Ordered by popularity/frequency
4. **Scalability**: Millions of users, high QPS
5. **Availability**: Resilience against failures

### Back-of-Envelope Estimation

**Key Assumptions:**
- 10 million daily active users
- Average 10 searches per user daily
- 20 bytes per query string (4 words × 5 characters each)
- ~20 requests sent per search (character-by-character typing)

**Calculations:**

| Metric | Value |
|--------|-------|
| QPS (average) | ~24,000 (10M users × 10 queries/day × 20 chars ÷ 86,400 seconds) |
| Peak QPS | ~48,000 (2× average) |
| Daily new data | 0.4 GB (10M × 10 × 20 bytes × 20% new queries) |

---

## Step 2: High-Level Design

Two primary services form the architecture:

### 1. Data Gathering Service
- Collects raw search queries
- Aggregates them
- Stores frequency metadata

### 2. Query Service
- Accepts prefix input
- Returns top-5 most searched queries
- Leverages cached frequency data

**Flow Example:** User types "d", "di", "din", "dinn", "dinne", "dinner"—each keystroke triggers a separate request.

---

## Step 3: Deep Dive Design

### Core Data Structure: Trie

A trie is a tree-like data structure that can compactly store strings. Key properties:

- Root node represents empty string
- Each node contains a character with 26 possible children (one per letter)
- Each node represents a word or prefix
- Efficiently supports prefix-based searches

**Trie Structure Example:**

```
Root
├── t
│   ├── r
│   │   ├── e (tree: 10)
│   │   ├── u (true: 35)
│   │   └── y (try: 29)
├── w
│   └── e (web: 61)
```

**Algorithm: Get Top K Queries**

Three sequential steps with complexity analysis:

1. **Find the prefix node**: O(p) where p = prefix length
2. **Traverse subtree**: O(c) where c = number of children
3. **Sort and select top k**: O(c log c)

**Total complexity**: O(p) + O(c) + O(c log c)

**Example Process (prefix "tr"):**
- Locate "tr" node in trie
- Identify valid children: tree (10), true (35), try (29)
- Sort by frequency descending
- Return top 2: true (35), try (29)

### Trie Optimization Strategies

**Optimization 1: Limit Prefix Length**
- Users rarely type a long search query into the search box
- Cap prefix at ~50 characters
- Reduces "find prefix" from O(p) to O(1)

**Optimization 2: Cache Top K at Each Node**
- Store top-k queries at each trie node
- Eliminates sorting step
- Reduces traversal overhead
- Trade space for query speed

**Optimized Algorithm Complexity:**
- Find prefix: O(1)
- Return cached top k: O(1)
- **Total: O(1)**

---

### Data Gathering Service Architecture

**Why Not Real-Time Updates?**
- Billions of queries daily—constant updates would bottleneck the query service
- Top suggestions remain relatively stable; frequent updates unnecessary

**Component Breakdown:**

**Analytics Logs**
- Append-only storage of raw search queries
- Not indexed; serves as source of truth
- Example entries:

| Query | Timestamp |
|-------|-----------|
| apple | 2025-01-10 10:00:00 |
| apple | 2025-01-10 10:01:23 |
| apple pie | 2025-01-10 10:05:45 |

**Aggregators**
- Process massive log files
- Normalize and structure data
- Generate frequency counts

**Aggregated Data**
- Cleaned, deduplicated query frequency table

| Query | Frequency |
|-------|-----------|
| apple | 156 |
| apple pie | 42 |
| apple watch | 28 |

**Workers**
- Asynchronous job servers running at fixed intervals
- Build trie data structures from aggregated data
- Persist results to Trie DB
- Execute on weekly schedule (typical)

**Trie DB (Persistent Storage)**

Two storage options:

**Option 1: Document Store (MongoDB)**
- Flexible schema
- Natural representation of hierarchical trie structure

**Option 2: Key-Value Store**
- Map each prefix to a hash table key
- Store trie node data as values
- Example mapping:

| Key | Value |
|-----|-------|
| "t" | {frequency: 450, top_k: [true: 35, try: 29, tree: 10]} |
| "tr" | {frequency: 95, top_k: [true: 35, try: 29]} |

**Trie Cache**
- Distributed in-memory cache system
- Stores frequently accessed trie nodes
- Takes weekly snapshots from Trie DB
- Significantly reduces database queries

---

### Query Service Flow

**Request Processing Pipeline:**

1. User submits search query with prefix to load balancer
2. Load balancer routes to API servers
3. API servers query Trie Cache for prefix node
4. Trie Cache returns cached top-k results
5. Results returned to client

**Cache Miss Handling:**
- If data not in Trie Cache (server out of memory or offline)
- Replenish from Trie DB back to cache
- Subsequent requests for same prefix served from cache

**Performance Optimizations:**

| Optimization | Mechanism |
|--------------|-----------|
| AJAX requests | Requests don't reload entire page; smooth UX |
| Browser caching | Client-side cache stores previous results |
| Data sampling | Log only 1 of every N requests to reduce storage overhead |

---

### Trie Operations: Create, Update, Delete

**Create Operation**
- Workers build new trie from aggregated logs weekly
- Replaces previous trie version in cache and DB

**Update Operations**

| Strategy | Approach | Tradeoff |
|----------|----------|----------|
| Weekly replacement | Rebuild entire trie; replace old version atomically | Stale data for up to 7 days; simpler implementation |
| Node-by-node update | Update individual nodes with frequency changes | Keeps data fresher; higher operational complexity |

**Delete Operation**
- Filter layer removes offensive, unsafe, or inappropriate suggestions
- Maintains content policy compliance
- Applied before results returned to users

---

### Scaling and Sharding

**Challenge:** Single trie becomes bottleneck at scale

**Sharding Strategy: Prefix-Based**

Partition trie across servers by first character:

| Shard | Character Range | Assignment |
|-------|-----------------|------------|
| Shard 1 | 's' | Single shard (high query volume) |
| Shard 2 | 'u', 'v', 'w', 'x', 'y', 'z' | Combined shard (lower volume) |
| Shard 3 | 'a', 'b', 'c' | Three letters together |

**Dynamic Adjustment:**
- Monitor query distribution
- Adjust shard ranges dynamically to avoid uneven distribution
- Redistribute shards if character frequency patterns change
- Prevents hot-spot scenarios where one shard receives disproportionate traffic

**Benefits:**
- Horizontal scalability across servers
- Load balanced according to actual query patterns
- Independent scaling of high-traffic shards

---

## Step 4: Extensions and Advanced Features

### Multi-Language Support
- Implement Unicode character encoding in trie
- Supports non-ASCII alphabets
- Same trie structure applicable across languages

### Country-Specific Trends
- Build separate trie instances per geographic region
- Distribute with CDNs for rapid global distribution
- Captures local search patterns and language variations

### Real-Time Trending Queries
- Monitor emerging query patterns
- Lower aggregation intervals (hourly vs. weekly)
- Trie updates more frequently with fresh trends
- Higher resource consumption trade-off

---

## Key Design Principles & Tradeoffs

| Principle | Implementation | Tradeoff |
|-----------|----------------|----------|
| Performance | Trie + caching achieves O(1) queries | Memory overhead for cached top-k |
| Freshness vs. Performance | Weekly batch aggregation | Up to 7-day lag in frequency data |
| Storage vs. Speed | Cache top-k at nodes | Increased memory usage |
| Scalability | Prefix-based sharding | Operational complexity; resharding required |
| Availability | Distributed cache with DB fallback | Cache miss handling latency |

---

## Summary

This design balances competing demands: the trie data structure enables rapid prefix matching with O(1) complexity after optimization; batch aggregation maintains performance while managing billions of daily queries; and prefix-based sharding scales to millions of users. The architecture prioritizes read performance for the query service while tolerating eventual consistency in data freshness through weekly trie rebuilds.

---

# Deep Dive Addendum

The remainder of this chapter is enrichment material for interview-grade depth: capacity math, architecture diagrams, trade-off tables, real-world case studies, failure modes, interviewer Q&A, and a glossary.

## Back-of-the-Envelope Math (Extended)

The chapter's headline numbers assume English-only, 10M DAU, 5 results per request. To defend those numbers and push them further, work the math end-to-end with powers of 2 and constants you can justify.

### Step 1 — derive QPS in powers of 2

Take the assumptions:

- DAU = 10,000,000 ≈ 2^23 (10M)
- searches/user/day = 10 ≈ 2^3 (rounded down; 8 vs 10 doesn't change the order)
- chars typed / search ≈ 20 ≈ 2^4

Total keystroke events per day:

```
events / day = 2^23 × 2^3 × 2^4
             = 2^(23 + 3 + 4)
             = 2^30 events / day
```

Seconds per day ≈ 2^16 (= 86,400). Average QPS:

```
QPS_avg = 2^30 / 2^16
       = 2^14
       = 16,384 QPS (keystroke events)
```

The chapter quotes ~24,000 QPS because it uses 10 searches/user instead of 8; 2^14 * 24/16 ≈ 24,576. Same order of magnitude.

Peak QPS (assume 2× the average as a conservative factor; real systems use 5-10× for evening bursts):

```
QPS_peak ≈ 2 × 16,384 ≈ 32,768 QPS
```

For a heavily news-driven site, bursts during breaking events routinely hit 10× the daily average; budget for that.

### Step 2 — bandwidth from the user side

Each AJAX call carries roughly:

- request: ~200 bytes (URL, headers, prefix ~50 bytes)
- response: 5 results × ~40 bytes (query + freq) + JSON overhead ≈ 300 bytes

Round-trip ≈ 500 bytes/keystroke. Per second at peak:

```
bandwidth_in =  32,768 req/s × 200 B  ≈ 6.4 MB/s outbound from clients
bandwidth_out = 32,768 resp/s × 300 B ≈ 9.6 MB/s inbound to clients
```

This is a rounding error compared to the CDN's video traffic in chapter 15, so it is fine to overprovision the API tier.

### Step 3 — storage growth

Daily new query volume:

```
new_bytes / day = 2^23 × 2^3 × 2^4 × 0.20  (20% are new)
                = 2^30 × 0.20
                ≈ 214 MB / day  (≈ 0.2 GB)
```

The chapter rounds this to 0.4 GB. The 2× difference comes from a stricter assumption that 1 in 5 queries are unique vs. 1 in 10; either is plausible.

Yearly storage:

```
0.4 GB/day × 365 ≈ 146 GB / year
```

Even five years of raw logs ≈ 730 GB. With 3× replication:

```
730 × 3 ≈ 2.2 TB of raw log storage
```

That is two commodity disks. The bottleneck is not storage; it is read QPS.

### Step 4 — trie size

How many nodes does a trie for 146M unique queries have? Assume the English alphabet (26 letters) and an average word length of 5 characters (lowercased). Then:

- Branching factor max ≈ 26
- Depth ≈ 5
- A node per character along every stored path

A rough upper bound: each unique query adds ~5 nodes; for 146M queries:

```
nodes ≈ 5 × 146 × 10^6 ≈ 7.3 × 10^8 nodes
```

Each node, conservatively, holds:

- 26 child pointers (8 bytes each in a 64-bit process) ≈ 208 bytes
- top-5 cached list (5 × ~64 bytes) ≈ 320 bytes
- frequency, padding, flags ≈ 32 bytes
- ≈ 560 bytes per node (estimate)

```
trie_size ≈ 7.3e8 × 560 B  ≈ 408 GB  (single-process, naïve)
```

That is too large for one box, which is the justification for prefix-based sharding. In practice, two refinements shrink the trie dramatically:

1. **Compression**: paths of single-child nodes collapse into a single edge. Most English prefixes are sparse; compressed tries are typically 5-10× smaller.
2. **Discarding rare tails**: if a node has only one descendant below a frequency threshold, drop the path from the suggested trie and fall back to a full-text lookup. Twitter has published material describing exactly this hybrid (highly tuned top-k trie + fallback index for the long tail).

After compression, a realistic trie of 146M queries fits in roughly 40-80 GB and can live entirely in RAM on one or two well-provisioned servers per shard.

### Step 5 — cache sizing

If 1% of all distinct prefixes account for 80% of requests (a typical Zipf for autocomplete), then at the API tier:

```
hot_prefixes ≈ 146M × 0.01 ≈ 1.46M prefixes
```

Each prefix payload ≈ 300 bytes (top-5 list):

```
cache_size ≈ 1.46 × 10^6 × 300 B ≈ 438 MB
```

This comfortably fits in a single Redis instance with headroom for replication.

---

## ASCII Architecture Diagrams

### Diagram 1 — End-to-end data flow (batch build + online query)

```
                          OFFLINE BUILD PATH                                ONLINE QUERY PATH
                          =====================                              =================

   ┌──────────┐    ┌─────────────┐    ┌────────────┐    ┌─────────┐
   │  Client  │───▶│  Analytics  │───▶│ Aggregator │───▶│ Workers │     ┌────────┐
   │  search  │    │  log (Kafka │    │ (MapReduce/│    │ (build  │     │  User  │
   └──────────┘    │   /S3)      │    │  Spark)    │    │  trie)  │     │ typing │
        ▲          └─────────────┘    └────────────┘    └────┬────┘     └───┬────┘
        │                                                       │              │
        │                                                       ▼              ▼
        │                                                ┌──────────┐    ┌─────────┐
        │                                                │ Trie DB  │    │   LB    │
        │                                                │(snapshot)│    └────┬────┘
        │                                                └────┬─────┘         │
        │                                                     │               ▼
        │                                                     ▼          ┌─────────┐
        │        ┌──────────┐    ┌─────────────┐    ┌──────────────┐      │   API   │
        │        │  Filter  │◀───│ Trie Cache  │◀───│   Cache      │◀─────│ servers │
        │        │ (block   │    │  (Redis)    │    │  warmer      │      │(stateless)│
        │        │  NSFW)   │    └─────────────┘    └──────────────┘      └────┬────┘
        │        └────┬─────┘                                                    │
        │             │                                                         │
        └─────────────┴──────────── JSON: top-5 + freq ────────────────────────┘
```

Key idea: the build path is offline and idempotent (rebuild weekly, atomic swap). The query path is online and serves from in-memory snapshots. The two paths meet only at the cache swap.

### Diagram 2 — Trie lookup with cached top-k (read path, single shard)

```
User prefix "din"
        │
        ▼
┌──────────────────────────────┐
│  LBS: hash prefix → shard    │
│  "din" → shard 3 ("a".."c")  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Trie Cache lookup           │
│  GET /prefix/din             │
└──────────────┬───────────────┘
               │  cache hit (common)
               ▼
┌──────────────────────────────┐
│  Node "din":                 │
│   top_k = [                  │
│     "dinner"      : 142,103  │
│     "dining room" :  92,401  │
│     "diners"      :  61,228  │
│     "dingo"       :  18,990  │
│     "dink"        :   8,211  │
│   ]                          │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Filter: drop NSFW / policy  │
└──────────────┬───────────────┘
               │
               ▼
JSON to client: 5 suggestions
```

### Diagram 3 — Sequence: cache miss + rebuild

```
Client         API GW        Trie Cache      Trie DB       Worker (cron)
  │              │               │              │               │
  │ GET /din     │               │              │               │
  │─────────────▶│               │              │               │
  │              │ GET /din      │              │               │
  │              │──────────────▶│              │               │
  │              │◀────── miss ──│              │               │
  │              │ GET /din      │              │               │
  │              │─────────────────────────────▶│               │
  │              │◀──── top_k ───────────────────│               │
  │              │ SET /din  (5m TTL)           │               │
  │              │──────────────▶│              │               │
  │              │ return top_k  │              │               │
  │              │─────▶         │              │               │
  │              │               │              │               │
  │              │               │              │  weekly tick  │
  │              │               │              │◀──────────────│
  │              │               │              │ rebuild trie  │
  │              │               │◀── new snapshot ──────────────│
  │              │               │  warm keys   │               │
```

### Diagram 4 — Streaming trie builder (Kafka → Flink → trie)

```
Kafka topic          Flink job                  Output
"search.clicks"      (windowed aggregate)
   │                     │
   │  ─────▶ .map(parse) ─────▶ .keyBy(query)
   │                           .window(1h tumbling)
   │                           .aggregate(count)
   │                                │
   │                                ▼
   │                       RocksDB state backend
   │                                │
   │                                ▼
   │                       Sink: HDFS / S3  (hourly parquets)
   │                                │
   │                                ▼
   │                       Trie builder (Spark)
   │                                │
   │                                ▼
   │                       Trie snapshot to Trie Cache
```

---

## Trade-off Tables

### Trade-off 1 — Where to keep the autocomplete state

| Option | Read latency | Freshness | Build cost | Ops complexity |
|---|---|---|---|---|
| In-memory trie rebuilt weekly on every API node | <1 ms | Up to 7 days stale | One-shot per node | High (deploy = rebuild) |
| Redis hash per prefix (`HGET prefix:d:t`) | 1-3 ms | Up to 7 days stale | One batch job | Low |
| Trie DB + cache-aside | 5-10 ms | Up to 7 days stale | One batch job | Medium |
| Real-time streaming trie (Flink) | 5-15 ms | Minutes | Always-on Flink | High |

The chapter picks the third (Trie DB + cache-aside). Real production systems frequently pick the second (Redis hash) because Redis already ships with prefix-scan-friendly data structures; the trie is then collapsed into a hash per prefix.

### Trade-off 2 — Update strategy

| Strategy | Freshness | Storage | Engineering effort | Failure mode |
|---|---|---|---|---|
| Weekly rebuild | Hours-to-days | Cheap (one snapshot) | Low | Stale trends |
| Daily rebuild | Hours | Cheap | Low | Brief staleness |
| Hourly rebuild | Minutes | Moderate | Medium | Higher rebuild cost |
| Real-time streaming trie | Seconds | Higher (Flink state) | High | Operational; potential inconsistency |
| Node-by-node hot updates | Seconds | Highest | Very high | Race conditions; partial updates |

### Trade-off 3 — Prefix indexing schemes

| Scheme | Memory per prefix | Range query | Boundary handling | Read pattern |
|---|---|---|---|---|
| Hash table keyed by exact prefix | O(1) | Lookup only | N/A (we already have the prefix) | Get one prefix's top-k |
| Sorted set keyed by prefix | O(log N) | Range scan via lexicographic | Trivial (range scan) | "Return all matches in cell" |
| Trie (full character tree) | O(sum of word lengths) | O(prefix length) | Implicit by construction | "Walk prefix, return top-k" |
| Reverse index (each query → prefixes) | O(queries × avg length) | Lookup | Trivial | "Return prefixes for a query" |

For typeahead the **hash table** or **trie** is dominant; the sorted set is rarely a fit.

---

## Real-World Case Studies

### Case Study 1 — Google Search autocomplete

Google's autocomplete is a study in horizontal scale: queries per second are reported in public talks to be in the low hundreds of thousands, with strict latency budgets (~100 ms perceived). The system uses **precomputed prefix → suggestion mappings** shipped to edge caches; the canonical pipeline is:

1. Logs of past queries stream into an aggregation pipeline.
2. Aggregator filters out policy violations, personal results, and rare queries.
3. Resulting top-k per prefix is signed and pushed to edge caches worldwide.
4. Edge serves suggestions from memory; misses fall back to a regional aggregator.

Key tradeoffs Google has publicly discussed:

- **Personalization on the server is limited** for latency reasons; personalization is layered after the prefix match.
- **Trending queries** are computed in a separate short-window aggregator and merged with the longer-window top-k at the edge.
- **Spelling** is handled by a downstream layer; the trie itself holds canonical spellings.

This is the production analog of the chapter's design, with the addition of a global edge cache layer.

### Case Study 2 — Algolia

Algolia is a hosted search-as-you-type service. Notable details from their engineering blog and conference talks:

- The index is stored as **prefix-keyed arrays in memory** per shard, kept hot on every search node (no separate cache tier).
- Index updates are streamed from a coordinator to all replicas with millisecond-level propagation, supporting near-real-time indexing.
- They shard by tenant (not by prefix), which trades some prefix-locality for tenant isolation.
- Ranking is **typo-tolerant** and **customizable per tenant**, so the trie-only model is insufficient; the implementation is closer to a **finite-state transducer** with custom scoring.

Algolia is the counter-example to "build a trie in your database": at their scale, an in-memory FST per node with full incremental updates is the answer.

### Case Study 3 — Elasticsearch completion suggester

Elasticsearch ships a `completion` field type that is, internally, an FST (finite-state transducer) with payloads (the suggestions) attached to terminal states. Key characteristics:

- Indexed in memory per shard.
- Supports fuzzy queries (typo tolerance) via Damerau-Levenshtein up to a configurable edit distance.
- Supports contexts (categories, geo) to filter suggestions post-lookup.
- The on-disk form is a compact FST; the in-memory form is the same FST loaded at search time.

For an interview, naming Elasticsearch's completion field as "an FST in memory with payloads" earns credit, because FSTs are the practical upgrade over hand-rolled tries.

### Case Study 4 — Twitter typeahead

Twitter has published several talks and blog posts (notably a 2011 retrospective and a 2018 rewrite) describing its typeahead system:

- Originally, it was a **per-character in-memory hash map** on every API server, with a **partial replication scheme** so each server only held a subset of the suggestions.
- The 2018 rewrite moved to **Zen**, an internal key-value store built for typeahead, which stores **all known queries in RAM** and serves `top-k` by frequency in O(prefix length).
- The system handles **personalization** by post-filtering suggestions: it fetches the top-N candidates from Zen and re-ranks using a per-user model.

Twitter is the canonical reference for "store everything in RAM; query by prefix; personalize on top."

### Case Study 5 — Amazon search suggestions

Amazon's autocomplete is interesting because of the **catalog dimension**: suggestions are not just queries but also products and categories. They use a hybrid:

- An **inverted index** of query → product-clicks, scoring products by recent CTR.
- A **separate trie** for query completions, refreshed more frequently for seasonal terms (e.g., "ps5" before launch).
- The two are merged at the API tier, with the catalog layer dominating for high-intent prefixes.

This is a useful contrast: when "queries" are heterogeneous (queries, products, categories), a single trie is the wrong abstraction and you compose multiple indexes at the API layer.

### Case Study 6 — Quicksilver (Mac OS X)

Quicksilver is the historical reference for **client-side** typeahead: the entire index lives on the user's machine, indexed by an in-memory trie maintained by a background process. Lessons relevant to the chapter:

- **Cold start**: first launch is slow because the index must be built; production systems ship warm caches to dodge this.
- **Personalization**: Quicksilver's index is purely personal; ranking is by recency and frequency. This is a counter-example to "rank by global popularity" and a useful interview talking point.
- **Memory budget**: even a personal index of millions of items must stay within ~100 MB; this argues strongly for compressed tries / FSTs.

---

## Common Pitfalls & Failure Modes

### Pitfall 1 — A naive `SELECT ... WHERE query LIKE 'prefix%'` is fine until it isn't

A single-column B-tree range scan on `prefix LIKE 'abc%'` works in MySQL/Postgres because the leading characters are fixed. But:

- When the index is on the **full query string** and the table is billions of rows, the resulting range is huge and the buffer pool thrashes.
- When you need **top-k by frequency within the range**, the database must fetch and sort every match; that is O(N) work per request.

**Mitigation**: precompute and persist `top_k` per prefix (the chapter's optimization 2), or use an in-memory FST.

### Pitfall 2 — Stale top-k after a viral event

A weekly rebuild means that if a celebrity says a new word on Sunday, the suggestion does not appear until the next build. This was widely reported during major events (elections, sports finals). Mitigation:

- Layer a **trending queries feed** on top, refreshed every few minutes, merged at the API tier.
- Use **streaming aggregation** for a separate "trending" prefix index, not the long-tail popularity index.

### Pitfall 3 — Unicode normalization

The chapter scopes "lowercase alphabetic only." In practice, the same visual character can be encoded multiple ways (`é` as one codepoint vs. `e` + combining acute). Naive `LOWER()` comparison misses matches. Always normalize (NFC) before indexing, and use a Unicode-aware collation in the database.

### Pitfall 4 — Hot shard imbalance

Sharding by first character produces skewed shards (e in English is far hotter than z). Two fixes:

- **Frequency-aware sharding**: hash the prefix to N shards weighted by historical QPS.
- **Replicated hot shards**: shard 1 (s*) is replicated to N nodes with consistent hashing on a secondary key.

### Pitfall 5 — Personalization leaks

If you blend per-user history into top-k, you must **not** show personal results in shared contexts (e.g., embedded search on a public page). Bug classes:

- Cache poisoning: caching a personalized result under a non-personalized cache key.
- Race conditions on profile updates mid-query.

The mitigation is a strict separation: **non-personalized suggestions** are cached at the edge with long TTLs; **personalized suggestions** are computed post-cache, never stored against the cache key.

### Pitfall 6 — Query flooding during a partial outage

If the upstream autocomplete service degrades, the client will retry per keystroke and multiply traffic 10-20×. Mitigations:

- **Client-side debounce**: only fire after 50-150 ms of idle.
- **Server-side rate limit**: per-IP and per-prefix.
- **Negative caching**: cache "no results" for a short TTL.

---

## Interview Q&A

**Q1 — How do you handle 10× the current QPS?**

A: Layered answer. (1) **Cache deeper** — push the snapshot from regional Redis to edge caches (CDN-like), because the index is read-only and trivially cacheable. (2) **Shard wider** — instead of 26 first-character shards, hash prefixes to 256-1024 shards; this lowers per-shard load by 10-40×. (3) **Compress the payload** — fewer bytes per prefix response (top-5 with ~30-byte queries → ~150 B per response instead of 300). (4) **Reduce per-keystroke fan-out** — debounce aggressively; one request per word instead of one per character. The combination of (1) and (4) usually covers a 10× burst.

**Q2 — How do you make suggestions fresher without killing the build path?**

A: Decouple the **popularity index** from the **trending index**. Keep the long-window popularity rebuild on its weekly cadence; add a **short-window streaming job** (Flink/Spark Streaming) that updates a separate "trending" set every 1-5 minutes. The API merges the two sets with deterministic ordering: trending first if present, popularity second. This avoids touching the rebuild pipeline while making the top of the suggestions list feel live.

**Q3 — Why use a trie instead of just indexing the database?**

A: Database range scans on `LIKE 'prefix%'` are correct but two orders of magnitude slower than in-memory lookups, and they cannot easily answer "top-k by frequency within the range" without sorting. The trie (or FST) collapses both problems into one data structure that fits in RAM, supports O(prefix-length) lookups, and stores the top-k right at the node. The tradeoff is memory; that is why sharding is required.

**Q4 — How would you go global?**

A: Three concerns. (1) **Latency**: ship the snapshot to **edge caches** in each region (CDN, Cloudflare Workers, regional Redis). (2) **Locale**: build a **per-language trie** (or per-region merged trie). The data is different — French users type different prefixes than English users. (3) **Compliance**: PII handling differs by jurisdiction. Trending queries can be computed regionally to keep data residency clean. A common pattern is one trie per language per major region, replicated to 5-20 edge locations.

**Q5 — How do you handle typos?**

A: Two paths. (1) **Symspell / BK-tree** at the API tier: when no exact prefix matches, attempt fuzzy match by edit distance. (2) **Elasticsearch-style FST with edit-distance transducers**: the index itself supports approximate matching up to a configurable Levenshtein distance. Either way, fuzzy match is more expensive than exact match, so the API tries exact first and only falls back on empty result or single-character prefixes (where typos are common).

**Q6 — How do you measure "good" autocomplete?**

A: Track three metrics. (1) **Engagement**: CTR on the top suggestion, top-5, and "any" suggestion. (2) **Latency**: p50, p95, p99 end-to-end including network. (3) **Coverage**: fraction of sessions that show at least one suggestion; an empty box usually means the index is broken. For personalization, run A/B tests on CTR uplift and downstream conversion (clicks → search → dwell). Avoid optimizing for "dwell on suggestion" — that is engagement theater, not quality.

---

## Glossary

| Term | Definition | Common misconception |
|---|---|---|
| Typeahead | UI pattern returning results as the user types | Often conflated with autosuggest, which may include non-query items |
| Trie | Tree data structure where each edge is a character; prefixes share prefixes of paths | A "trie node" is not a character — it is a state; each edge is labeled |
| FST (Finite-State Transducer) | Compressed trie that shares common suffixes and supports output on transitions | "Faster than a trie" is wrong; both are O(prefix length). FSTs win on **memory** |
| Geohash | Base-32 encoding of recursively divided lat/long | Adjacent cells can have completely different prefixes (boundary problem) |
| Prefix code | Encoding where no code is a prefix of another | Geohashes are **not** strictly prefix-free at fixed length |
| Top-k | The k highest-scoring items by some scoring function | "Top-k by frequency" requires recomputing frequency on every update |
| Aggregation window | Time range over which counts are summed (tumbling, sliding) | A tumbling window **loses** the tail of the previous window unless combined |
| Lexicographic range | Range scan on a string column using `LIKE 'x%'` or `BETWEEN` | On collated columns, range order matches the **collation**, not byte order |
| Edge cache | Cache geographically close to the user (CDN POP) | An "edge cache" is not the same as a "regional cache"; latency differs by 10-100 ms |
| Debounce | Client-side delay before firing a request, resetting on each keystroke | Debounce ≠ throttle; throttle fires at most once per N ms regardless |
| Zipfian distribution | Distribution where frequency ∝ 1/rank^k | Pure Zipf (k=1) is rare in real autocomplete; empirical k is closer to 0.5-1.5 |
| Suggestion filter | Layer that removes policy-violating completions | Filters are usually applied **after** ranking, not before |
| Shard | Horizontal partition of the index | Shards must be **co-located with replicas** for read scaling; a hot shard is still hot |
| Personalized suggestion | Suggestion influenced by per-user history | Personalization usually **post-filters** the global top-k, not the other way around |
| Trending query | Query whose frequency is rising in a short window | Trending ≠ popular; a popular query can be flat |
| Bloom filter | Probabilistic structure for "is this prefix known?" membership tests | False-positive prone; never use as the source of truth |
| P99 latency | 99th percentile of response times | p99 ≠ tail latency; "tail" usually means p99.9 or p99.99 in production systems |