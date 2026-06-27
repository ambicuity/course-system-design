# How can Cache Systems go wrong?

> Four classic cache failure modes — thundering herd, penetration, breakdown, crash — and the patterns that prevent each.

**Type:** Learn
**Prerequisites:** Basic caching concepts
**Time:** ~15 minutes

---

## The Problem

A cache in front of a database is one of the most reliable performance optimizations — until it isn't. Caches fail in specific, well-understood ways. Teams that know the failure modes in advance prevent them; teams that do not learn them in production at 3 AM.

This lesson walks through the four classic cache failure modes, what causes them, what they look like in production, and the patterns that mitigate each. Knowing these is what separates a caching strategy from a caching accident.

---

## The Concept

### The four failure modes

```
   Failure mode       What goes wrong               Symptom
   ─────────────      ─────────────────            ──────────────────────
   Thundering herd    Many keys expire together    Sudden DB load spike
   Cache penetration  Queries for non-existent keys Sustained DB load
   Cache breakdown    Hot key expires              DB overload from hot data
   Cache crash        Cache server is down         Total DB overload
```

Each has a distinct cause and a distinct mitigation. Knowing which is which is the skill.

---

### 1. Thundering Herd (Cache Stampede)

**What it is:** a large number of cache keys expire at the same moment. The queries that follow all miss the cache simultaneously and hit the database. The database is overwhelmed.

```
   Timeline:
   09:00:00  Cache populated (TTL = 60s for all keys)
   10:00:00  All keys expire at once
   10:00:00  1000 requests arrive → all miss → 1000 DB queries
            DB CPU spikes to 100% — outage begins

   Why it happens:
   - Bulk-set operation (e.g., cache warming script) sets the same TTL
   - TTL is computed deterministically (e.g., "next hour boundary")
   - Configuration mistake (e.g., `expire=60` applied to all keys)
```

**Mitigations:**

- **Random TTL jitter.** Add a random offset to every TTL: `ttl = 60 + random(0, 10)` seconds. Keys expire at different times.
- **Stagger expirations.** When setting TTLs programmatically, distribute the expiry times across a window.
- **Pre-warm before expiry.** Refresh hot keys before they expire.
- **Locking on miss.** When a key misses, only one request actually queries the DB; others wait for the result. (Redis: `SETNX`-based lock.)
- **Rate limiting at the application.** Even if the DB sees many queries, throttle them so the DB can recover.

**Stale-while-revalidate pattern:**

```
   1. Request comes in
   2. Check cache → value exists but expired
   3. Return the stale value immediately
   4. Asynchronously refresh the cache in the background
   5. Next request sees the fresh value
```

This guarantees users never wait for a cache refresh, even at the moment of expiry.

---

### 2. Cache Penetration

**What it is:** queries for keys that do not exist in the cache *or* the database. The cache cannot help; the database is queried for every request, but returns nothing.

```
   Timeline:
   09:00:00  Attacker sends 10000 requests for /users/nonexistent-ids
            Every request: cache miss → DB query → DB returns null
            DB CPU: 100%
            No way to tell malicious from legitimate empty results
```

**Why it happens:**

- Malicious traffic probing for valid IDs
- Bugs that generate non-existent IDs
- User typos in URL paths
- Data that legitimately does not exist (deleted user, expired session)

**Mitigations:**

- **Cache null values.** When a query returns null, cache `null` for a short time. Subsequent identical requests hit the cache, not the DB.
  ```python
  result = db.query("SELECT * FROM users WHERE id = %s", user_id)
  if result is None:
      redis.setex(f"user:{user_id}:null", 60, "1")  # cache null for 60s
      return None
  ```

- **Bloom filter.** A probabilistic data structure that answers "this key definitely does not exist." Add it in front of the cache to short-circuit negative lookups.
  ```
  if not bloom_filter.might_contain(user_id):
      return None  # definitely doesn't exist; don't even check cache or DB
  ```

- **Input validation.** Reject malformed inputs before they hit the cache or DB.
- **Rate limit by IP / user.** Block abusive traffic at the edge.

---

### 3. Cache Breakdown (Hotspot Invalidation)

**What it is:** a single, very hot key expires. All concurrent requests for that key miss simultaneously and hit the database. The DB is overloaded by requests for *one* piece of data.

```
   Timeline:
   14:00:00  Celebrity posts a video
   14:05:00  Video metadata cache expires (TTL = 5 min)
   14:05:00  100,000 requests arrive → all miss → 100,000 DB queries for one row
            DB CPU: 100%
```

**Why it happens:**

- A few keys receive a disproportionate share of traffic (the "long tail" or the "head" of the distribution)
- Those keys expire on the same schedule as everything else
- The DB is sized for average load, not for a sudden 100x spike on one query

**Mitigations:**

- **No TTL on hot keys.** Refresh them in the background; never let them expire.
- **Background refresh.** A job proactively updates hot keys before they expire.
- **Locking on miss.** Only one request queries the DB; others wait.
- **Read replicas.** Spread the hot-key read load across replicas.
- **Pre-computed aggregates.** For things like "trending posts," maintain a counter or pre-computed list rather than recomputing on every cache miss.

---

### 4. Cache Crash

**What it is:** the cache server (Redis cluster) goes down. All requests bypass the cache and hit the database directly. If the cache was absorbing most of the load, the DB is now expected to handle 10× or 100× its normal traffic.

```
   Timeline:
   14:00:00  Redis cluster network partition
   14:00:00  All app servers fail to reach Redis; circuit breaker opens
   14:00:01  All requests fall through to DB
   14:00:30  DB CPU: 100%; DB connection pool exhausted; request timeouts
   14:01:00  Outage
```

**Why it happens:**

- Hardware failure on cache node
- Network partition
- Software bug in cache cluster
- Cache cluster overloaded

**Mitigations:**

- **Circuit breaker.** When the cache is unreachable, the application stops trying it for a cooldown period. Prevents every request from spending time waiting for a timeout.
  ```python
  # pseudo-code
  if circuit_breaker.is_open("redis"):
      return query_db_directly(query)
  try:
      return redis.get(key)
  except ConnectionError:
      circuit_breaker.open("redis", cooldown=30s)
      return query_db_directly(query)
  ```

- **Redis cluster / replica set.** Run Redis with replicas and automatic failover. One node failure does not mean the cluster is down.

- **DB connection pooling sized for cache-down scenarios.** If the cache is down, the DB must handle the full load; the connection pool must be large enough to allow that without exhausting.

- **Local fallback cache.** Each app server keeps a tiny in-process cache for the hottest keys. When Redis is down, the local cache absorbs some of the load.

- **Cache-aside with timeout.** Set short timeouts on cache calls. If the cache is slow, fall back to the DB rather than waiting.

---

## Build It / In Depth

### Detecting each failure mode

| Failure mode | Detection signal |
|---|---|
| Thundering herd | Sudden spike in cache miss rate; DB CPU spikes immediately after cache TTL boundary |
| Cache penetration | High cache miss rate for non-existent keys; DB queries return null at high rate |
| Cache breakdown | High cache miss rate for one specific key; DB sees identical queries repeatedly |
| Cache crash | Cache server unreachable; circuit breaker open; DB connection pool saturates |

**Monitor in production:**

```python
# Cache hit / miss metrics
cache_hits.labels(cache="redis", key_type="user").inc()
cache_misses.labels(cache="redis", key_type="user").inc()

# Detect thundering herd: watch for periodic miss spikes
# Alert when miss_rate > 80% over 1 minute

# Detect cache breakdown: track per-key miss rates
# Alert when a single key has > 1000 misses per second

# Detect cache crash: monitor cache connectivity
# Alert when cache_errors / cache_calls > 5% over 30 seconds
```

---

### The mitigation toolkit

```
   Thundering herd
     ├── Random TTL jitter (Redis: EXPIRE key rand(0,10))
     ├── Stale-while-revalidate
     ├── Background refresh for hot keys
     └── Locking on miss (Redis SETNX)

   Cache penetration
     ├── Cache null values with short TTL
     ├── Bloom filter for "definitely doesn't exist"
     ├── Input validation
     └── Rate limiting

   Cache breakdown
     ├── No TTL on hot keys (background refresh only)
     ├── Pre-computed aggregates
     ├── Read replicas
     └── Locking on miss

   Cache crash
     ├── Circuit breaker (open after N failures)
     ├── Replica set with automatic failover
     ├── Short timeouts on cache calls
     └── Local fallback cache for hottest keys
```

---

### Implementation: a resilient cache layer

```python
import time
import random
import json
from typing import Callable, Optional, Any

class ResilientCache:
    def __init__(self, redis_client, fallback_local=None):
        self.redis = redis_client
        self.local = fallback_local or {}
        self.circuit_open_until = 0
        self.failure_count = 0
        self.MAX_FAILURES = 5
        self.COOLDOWN = 30  # seconds

    def get_or_load(self, key, load_fn, ttl=60, null_ttl=10):
        # 1. Check local fallback first (no network)
        if key in self.local:
            return self.local[key]

        # 2. Check circuit breaker
        if time.time() < self.circuit_open_until:
            return self._load_from_db(key, load_fn)

        # 3. Try the cache
        try:
            cached = self.redis.get(key)
            if cached is None:
                # Cache miss; might be a null cache
                if self.redis.get(f"{key}:null") is not None:
                    return None
                # Load from DB
                value = self._load_from_db(key, load_fn)
                if value is None:
                    self.redis.setex(f"{key}:null", null_ttl, "1")
                else:
                    # TTL jitter prevents thundering herd
                    jitter = random.randint(0, 10)
                    self.redis.setex(key, ttl + jitter, json.dumps(value))
                return value
            return json.loads(cached)
        except ConnectionError:
            self._trip_circuit()
            return self._load_from_db(key, load_fn)

    def _load_from_db(self, key, load_fn):
        try:
            value = load_fn(key)
            self.local[key] = value  # local fallback
            if len(self.local) > 1000:
                self.local.pop(next(iter(self.local)))  # simple eviction
            return value
        except Exception:
            return None

    def _trip_circuit(self):
        self.failure_count += 1
        if self.failure_count >= self.MAX_FAILURES:
            self.circuit_open_until = time.time() + self.COOLDOWN
            self.failure_count = 0
```

This combines: local fallback, circuit breaker, null caching, TTL jitter, and lock-free single-key loads.

---

## Use It

### When to suspect each failure mode

| Production symptom | Likely cause |
|---|---|
| Periodic DB CPU spikes every N minutes | Thundering herd (cache TTL boundary) |
| Constant high DB load despite caching | Cache penetration (lookups for non-existent data) |
| Specific query hammering the DB | Cache breakdown (hot key expired) |
| DB connection pool exhausted; Redis unreachable | Cache crash |
| Slow first request after deploy | Cold cache; not technically a "failure" but related |

### Order of application

When adding mitigations, apply them in this order:

```
   1. TTL jitter (cheapest; fixes most thundering herd)
   2. Null caching (cheap; fixes most cache penetration)
   3. Circuit breaker (essential for cache crash)
   4. Locking on miss (prevents breakdown for moderate hot keys)
   5. Background refresh for true hot keys (last resort; complex)
```

Each step is independent. Apply the first three for most systems; only add 4 and 5 if you measure the need.

---

## Common Pitfalls

- **Treating all four failure modes as "the cache is slow."** They have different causes and different fixes. Diagnose before fixing.

- **Adding a circuit breaker that never resets.** A circuit breaker that opens but never closes is just a permanent cache bypass.

- **Null caching forever.** Null values should have a *short* TTL. Otherwise new data is invisible until the null expires.

- **Bloom filter false positives.** Bloom filters can say "might contain" when the key does not. Tune the false positive rate; never use a bloom filter as the only check.

- **Ignoring the failure mode that does not match.** If you only fix thundering herd and your actual problem is cache breakdown, you have wasted effort.

- **Over-relying on cache.** The cache is an optimization. The system must work (slowly) without it. Test that.

- **No observability.** Without metrics on cache hit rate, miss rate, error rate, and per-key traffic, you cannot tell which failure mode is hitting you.

---

## Exercises

1. **Easy** — For each of the four failure modes, give a concrete scenario where it would occur and one mitigation.

2. **Medium** — A production cache has a hit rate of 95% but the database CPU spikes to 100% every 5 minutes for 30 seconds. Diagnose which failure mode this is and propose the fix.

3. **Hard** — Design a cache layer for a high-traffic e-commerce site that mitigates all four failure modes. Specify the cache client, TTL strategy, circuit breaker thresholds, and observability metrics. Justify each choice.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Thundering herd | A stampede | Many cache keys expiring simultaneously, causing a coordinated flood of DB queries |
| Cache stampede | A herd | Same as thundering herd; the term used interchangeably |
| Cache penetration | Hackers | Repeated queries for keys that do not exist in cache or DB; the DB is queried uselessly |
| Cache breakdown | Hot data | A single hot key expiring and causing a focused DB overload |
| Cache crash | Redis is down | The cache server is unreachable; all requests fall through to the DB |
| TTL jitter | Random delay | Adding a random offset to TTLs so keys expire at different times; prevents thundering herd |
| Stale-while-revalidate | A pattern | Returning the expired-but-still-cached value while refreshing in the background |
| Circuit breaker | An emergency stop | A pattern that detects repeated failures and stops calling the failing service for a cooldown period |
| Null caching | Caching nothing | Caching a "null" or "not found" sentinel for keys that do not exist; prevents repeated DB queries for missing data |
| Bloom filter | A hash | A probabilistic data structure that answers "might contain this key?" with possible false positives but no false negatives; used to short-circuit lookups for non-existent keys |

---

## Further Reading

- **"Caching at Reddit"** — real-world case study of multi-layer caching: https://www.reddit.com/r/RedditEng/
- **AWS ElastiCache Best Practices** — Redis and Memcached patterns: https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/BestPractices.html
- **Redis Documentation on Caching Patterns** — official patterns for cache invalidation and stampede prevention: https://redis.io/docs/manual/client-side-caching/
- **"Caching is the most important optimization"** — the canonical System Design Primer section: https://github.com/donnemartin/system-design-primer#cache