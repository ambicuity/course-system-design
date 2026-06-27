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
|-----------|-----------------|----------|
| Performance | Trie + caching achieves O(1) queries | Memory overhead for cached top-k |
| Freshness vs. Performance | Weekly batch aggregation | Up to 7-day lag in frequency data |
| Storage vs. Speed | Cache top-k at nodes | Increased memory usage |
| Scalability | Prefix-based sharding | Operational complexity; resharding required |
| Availability | Distributed cache with DB fallback | Cache miss handling latency |

---

## Summary

This design balances competing demands: the trie data structure enables rapid prefix matching with O(1) complexity after optimization; batch aggregation maintains performance while managing billions of daily queries; and prefix-based sharding scales to millions of users. The architecture prioritizes read performance for the query service while tolerating eventual consistency in data freshness through weekly trie rebuilds.
