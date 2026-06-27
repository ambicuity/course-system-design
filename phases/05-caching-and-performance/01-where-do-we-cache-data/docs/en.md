# Where Do We Cache Data?

> Eight layers of caching between the browser and the database — and the right place for each kind of data.

**Type:** Learn
**Prerequisites:** Basic web architecture, HTTP basics
**Time:** ~20 minutes

---

## The Problem

Caching is one of the most effective performance optimizations — and one of the most misunderstood. Teams add a Redis cluster and expect everything to be faster. They are sometimes disappointed when the cache hit rate is low, when stale data causes bugs, or when invalidation turns out to be the hardest problem in computer science.

The reason is usually that the cache is in the wrong place. There are at least eight distinct layers where data can be cached, each with different characteristics, lifetimes, and use cases. Knowing the layers — and which kinds of data belong where — is what separates effective caching from cargo-culted caching.

This lesson walks through all eight layers, from the browser down to the database's own internal caches, and shows what each is good for.

---

## The Concept

### The eight cache layers

```
   User request
       │
       ▼
   1. Browser cache             ← per-client, ephemeral
       │
       ▼
   2. CDN                       ← per-region, public content
       │
       ▼
   3. Load balancer             ← per-LB, limited
       │
       ▼
   4. Service (in-process)      ← per-server, fast
       │
       ▼
   5. Distributed cache (Redis) ← shared across servers
       │
       ▼
   6. Search index (Elastic)    ← full-text, faceted queries
       │
       ▼
   7. Read replicas             ← database-scale, eventually consistent
       │
       ▼
   8. Database internal         ← WAL, buffer pool, materialized views
```

Every layer sits between the user and the data. Each caches a different thing for a different lifetime.

---

### Layer 1: Browser cache

The browser stores HTTP responses locally, governed by `Cache-Control` headers. Subsequent requests for the same resource hit the local cache before the network.

```http
Cache-Control: max-age=3600, public
ETag: "abc123"
```

**Properties:**

- Per-client (each user has their own cache)
- Free (no server compute)
- Fastest possible (no network)
- Limited control (depends on browser, user actions)

**Best for:** static assets (CSS, JS, images, fonts), versioned resources with content-hash filenames, `ETag` or `Last-Modified` headers for revalidation.

**Watch out for:** sensitive data (must not be cached publicly), versioned files (use content-hash in filename so updates are atomic).

---

### Layer 2: CDN

A geographically distributed network of edge servers that cache and serve content close to users.

```
   User in Tokyo                User in London
        │                              │
        ▼                              ▼
   ┌──────────┐                  ┌──────────┐
   │ CDN Edge │                  │ CDN Edge │
   │  Tokyo   │                  │  London  │
   └────┬─────┘                  └────┬─────┘
        │                              │
        └────────────┬─────────────────┘
                     ▼
              ┌──────────┐
              │  Origin  │
              └──────────┘
```

**Properties:**

- Per-region (edges cache for users near them)
- Reduces latency dramatically (5–50 ms instead of 100–300 ms)
- Good for static and semi-static content
- Cache invalidation is a per-edge challenge

**Best for:** static websites, public APIs with low personalization, video streaming, downloadable files, JavaScript bundles.

**Watch out for:** personalized content (varies per user; harder to cache), authenticated content (signed URLs or per-user caching).

---

### Layer 3: Load balancer

Some load balancers cache responses for very short periods. AWS ALB, for example, supports response caching.

**Properties:**

- Per-load-balancer (all servers behind it share the cache)
- Very short TTL (seconds)
- Useful for reducing backend load for highly cacheable responses

**Best for:** responses that are expensive to compute and identical for short windows (e.g., `/api/status` for 1 second).

**Watch out for:** this is rarely the right place for application-level caching. The LB cache is too coarse to be useful for most application data.

---

### Layer 4: Service in-process cache

The service keeps data in its own memory (a Python dict, a Caffeine cache, a Guava cache). The fastest cache possible after the browser.

**Properties:**

- Per-server instance (each instance has its own cache)
- Microsecond access time
- Lost on restart or instance replacement
- Not shared across instances

**Best for:** lookups that happen on every request, configuration that rarely changes, reference data with low cardinality (e.g., list of countries, enum values).

**Implementation in Python:**

```python
from functools import lru_cache
import time

@lru_cache(maxsize=1000)
def get_feature_flags(user_id: int):
    # Expensive computation
    return db.query("SELECT * FROM flags WHERE user_id = ?", user_id)
```

**Watch out for:** memory pressure (the cache can grow); stale data (no automatic invalidation across instances); thundering herd (when the cache expires, all instances miss at once).

---

### Layer 5: Distributed cache (Redis, Memcached)

A shared cache across all service instances. The standard caching layer for application data.

**Properties:**

- Shared across instances (one cache for the whole service)
- Fast (sub-millisecond typical)
- Supports rich data structures (Redis: lists, hashes, sets, sorted sets)
- Scales horizontally (cluster mode)
- Volatile (data can be lost; configurable persistence)

**Best for:** session storage, computed results shared across requests, rate limit counters, leaderboards, distributed locks, anything multiple servers need to read.

**Implementation pattern:**

```python
def get_user_profile(user_id: int):
    # Try cache first
    cached = redis.get(f"user:{user_id}:profile")
    if cached:
        return json.loads(cached)

    # Cache miss: query DB and populate cache
    profile = db.query("SELECT * FROM users WHERE id = %s", user_id)
    redis.setex(f"user:{user_id}:profile", 3600, json.dumps(profile))
    return profile
```

**Watch out for:** thundering herd (use locking or stale-while-revalidate), cache stampede (expire keys at different times), serialization overhead.

---

### Layer 6: Search index (Elasticsearch, OpenSearch)

A specialized index optimized for full-text search, faceted queries, and relevance ranking. It is its own kind of cache for query patterns SQL databases are bad at.

**Properties:**

- Eventually consistent with the source of truth (writes go to the DB; the index is updated async)
- Excellent for text search, fuzzy matching, aggregations
- Not a replacement for the database (no ACID)

**Best for:** product search, log search, autocomplete, faceted filtering, anything where SQL `LIKE` is too slow or limited.

**Watch out for:** index drift (when the index falls behind the DB), complex sync pipelines.

---

### Layer 7: Database read replicas

A copy of the database that serves reads. Faster than the primary for read-heavy workloads.

**Properties:**

- Eventually consistent (lag from primary, typically <1 second)
- Scales reads horizontally
- Subject to replication lag

**Best for:** analytics queries, reporting queries, anything read-heavy that would slow down the primary.

**Watch out for:** read-your-writes consistency (after a write, the read might still see the old value), replication lag spikes.

---

### Layer 8: Database internal caches

The database itself caches data internally in several ways:

```
   Inside the database:
   ┌────────────────────┐
   │  Buffer pool       │  ← query result cache
   │  (in-memory)       │
   ├────────────────────┤
   │  WAL (write-ahead) │  ← durability log
   ├────────────────────┤
   │  Materialized view │  ← pre-computed aggregations
   ├────────────────────┤
   │  Transaction log   │  ← changes for replication
   ├────────────────────┤
   │  Replication log   │  ← sync state with replicas
   └────────────────────┘
```

**Properties:**

- Managed by the database itself
- Tightly coupled to the storage engine
- Critical for performance; often the difference between fast and slow queries

**Best for:** everything. These caches exist for all database workloads. The job is to make sure they are sized correctly (`shared_buffers`, `buffer_pool_size`).

**Watch out for:** cache invalidation on writes (the database handles this), cold caches (after restart, performance is slower until warmed up).

---

### Mapping data to the right layer

Different data has different caching requirements. Here is a cheat sheet:

| Data type | Best layer(s) |
|---|---|
| Static assets (CSS, JS, images) | Browser cache + CDN |
| API responses (per-user) | Distributed cache (Redis) with short TTL |
| User profiles | Distributed cache + service in-process |
| Computed aggregations | Distributed cache + materialized view |
| Full-text search | Search index (Elastic) |
| Reference data (countries, enums) | Service in-process + distributed cache |
| Static HTML pages | CDN |
| Session data | Distributed cache (Redis) |
| Rate limit counters | Distributed cache (Redis with INCR) |
| Database query results | Database buffer pool |
| Real-time counters | Distributed cache with eventual rollup |
| ML features | Service in-process + distributed cache |

---

## Build It / In Depth

### A real request, through every layer

```
   User visits https://example.com/article/42

   1. Browser cache:  Is the HTML cached locally?
       HIT → return instantly (no network)
       MISS ↓

   2. CDN:           Is the HTML cached at the edge?
       HIT → return from edge (~30 ms)
       MISS ↓

   3. Load balancer: pass to a backend server
       ↓

   4. Service:       Is the article in-process?
       HIT → return (~1 ms)
       MISS ↓

   5. Distributed cache (Redis): is the article there?
       HIT → return from Redis (~5 ms)
       MISS ↓

   6. Search index: any matching articles?
       (probably not relevant for direct ID lookup)
       ↓

   7. Read replica: query the database
       HIT (in buffer pool) → return from memory (~10 ms)
       MISS (cold) → disk read → return (~50 ms)
       ↓

   8. Database internal: store result in buffer pool for next time

   Total: anywhere from 5 ms (browser cache) to 200 ms (cold cache miss)
```

Most production requests hit at least three of these layers. Optimizing each layer compounds.

---

### Common anti-patterns

| Anti-pattern | Why it hurts |
|---|---|
| Cache everything in Redis | Memory cost; invalidation complexity; cache poisoning risk |
| Cache nothing | Missed performance opportunity |
| Same TTL for all keys | Thundering herd at expiry |
| No cache key strategy | Bug-prone; inconsistent invalidation |
| Cache invalidation by event only | Drift; cache becomes stale over time |
| Caching without TTL | Stale data forever |
| Caching at the wrong layer | Wrong granularity; wrong invalidation |
| Skipping observability | Cannot tell if the cache is helping or hurting |

---

### How to choose a TTL

| Data type | TTL strategy |
|---|---|
| User profiles | 1–24 hours; explicit invalidation on update |
| API responses | 30 seconds – 5 minutes; respect Cache-Control header |
| Session data | 30 minutes – 24 hours; sliding expiration |
| Aggregations | Match the data freshness requirement (1 minute, 1 hour, 1 day) |
| Reference data | Hours to days; invalidate on update |
| Rate limit counters | Window length (1 second, 1 minute, 1 hour) |
| Real-time data | Seconds; consider streaming instead of caching |

---

## Use It

### When to add each layer

| Symptom | Add |
|---|---|
| Slow first page load | CDN |
| Repeated identical requests hitting the DB | Service in-process cache |
| Multiple instances, each duplicating the same query | Distributed cache (Redis) |
| Search is too slow or limited | Search index |
| Read-heavy primary is the bottleneck | Read replicas |
| Database queries are slow even when individually fast | Buffer pool / shared_buffers tuning |
| Session management is hard | Redis sessions |
| User-specific data shared across services | Distributed cache |

---

### Cache invalidation patterns

| Pattern | How it works | Trade-off |
|---|---|---|
| **TTL-based** | Set an expiry; data is re-fetched after | Simple; may serve stale |
| **Write-through** | Cache updated on every write | Always fresh; more write cost |
| **Write-behind** | Cache updated async after write | Fast writes; brief staleness |
| **Explicit invalidation** | Code calls `cache.delete(key)` on update | Always correct when applied; bugs when missed |
| **Pub/sub invalidation** | Subscribers notified of changes | Scales; needs careful delivery semantics |
| **Versioning** | Cache key includes a version number | Always fresh; cache churn on version bump |

The right pattern depends on the data's staleness tolerance and the system's complexity.

---

## Common Pitfalls

- **Caching sensitive data.** PII, payment info, secrets must never be cached without encryption and access control.

- **Caching with no invalidation strategy.** TTL alone is rarely enough. Pair with explicit invalidation on updates.

- **Same TTL on all keys.** Coordinated expiry causes thundering herd. Add random jitter to TTLs.

- **Caching before measuring.** Without baseline metrics, you cannot tell if the cache is helping. Add it with observability.

- **Assuming the cache will fix performance.** A cache miss path that is slower than the original (e.g., because of serialization overhead) makes things worse, not better.

- **Inconsistent serialization.** JSON vs pickle vs protobuf across cache layers leads to subtle bugs.

- **Forgetting to invalidate on delete.** The cache may serve data that no longer exists in the source of truth.

- **No monitoring of cache hit rate.** A cache with a 20% hit rate is mostly overhead. Measure; improve; iterate.

---

## Exercises

1. **Easy** — Pick three of the eight cache layers. For each, give one example of data that belongs there and one example that does not.

2. **Medium** — Take a real API request in a product you use. Trace it through all eight cache layers. Identify which layers are actually in use and which would help if added.

3. **Hard** — You are designing the caching strategy for a high-traffic e-commerce site. Pick appropriate layers and TTLs for: (a) the product listing page, (b) the user cart, (c) the search autocomplete, (d) the order confirmation page. Justify each choice.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Cache | A Redis instance | Any layer that stores data for faster subsequent access; eight distinct layers exist between browser and database |
| Browser cache | Local storage | Per-client storage of HTTP responses, governed by Cache-Control headers |
| CDN | A web accelerator | A geographically distributed network of edge servers that cache content close to users |
| Distributed cache | Redis | A shared cache across multiple service instances, accessed over the network |
| Service in-process cache | A local variable | Cache that lives in the memory of a single service instance; fastest but not shared |
| Cache hit rate | A percentage | The fraction of cache lookups that find the data; a low hit rate means the cache is mostly overhead |
| Cache stampede | A traffic spike | Many requests missing the cache simultaneously and overloading the source; mitigated by jittered TTLs, locking, or stale-while-revalidate |
| Cache invalidation | Clearing the cache | The act of removing or updating cached data when the source of truth changes; the hardest problem in computer science |

---

## Further Reading

- **"Caching at Reddit"** — a real-world case study of multi-layer caching: https://www.reddit.com/r/RedditEng/comments/
- **"Designing Data-Intensive Applications"** — chapters on caching and consistency: https://dataintensive.net/
- **Redis Documentation** — the canonical reference for the most-used distributed cache: https://redis.io/docs/
- **Cloudflare Learning Center** — practical CDN and caching patterns: https://www.cloudflare.com/learning/
- **HTTP Caching (MDN)** — the definitive reference on browser caching: https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching
- **"Caching is the most important optimization"** — a focused guide: https://github.com/donnemartin/system-design-primer#cache