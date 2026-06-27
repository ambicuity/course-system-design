# Design A Rate Limiter

## Overview

A rate limiter controls traffic flow by restricting the number of client requests within specified time periods. This foundational system design component prevents service abuse and ensures equitable resource distribution.

Rate limiting is one of the highest-signal system design questions because it is small enough to be tractable in 45 minutes, yet exercises the full stack: algorithms, distributed state, edge deployment, and policy semantics. Treat it as a forcing function for "what does your trade-off reasoning actually look like?"

## Key Benefits

- **DoS Prevention**: Blocks excessive requests from intentional or unintentional attacks
- **Cost Reduction**: Limits expensive third-party API calls and reduces infrastructure expenses
- **Server Protection**: Filters bot traffic and prevents overload from misbehaving clients

### The Three Categories of Rate Limit

In production, rate limits usually split into three flavors, each with different goals:
- **Hard limits** — "no more than N requests per minute, period." Used for abuse prevention, payment endpoints, signup. Strict.
- **Soft limits** — "we prefer to throttle at N, but allow bursts if the system has capacity." Used for read traffic, search, analytics. Friendly.
- **Quota limits** — "you have N requests per day, then pay for more." Used for public APIs with billing. Customer-facing.

Knowing which type the question targets changes the algorithm choice and the response semantics.

## Step 1: Problem Understanding & Design Scope

### Requirements Clarification

The design focuses on server-side API rate limiting in distributed environments with these capabilities:

- Accurately limit excessive requests
- Maintain low latency without degrading HTTP response times
- Minimize memory consumption
- Support multiple servers/processes (distributed rate limiting)
- Provide clear exception handling with HTTP 429 responses
- Maintain high fault tolerance despite component failures

### Use Case Examples

- Maximum 2 posts per second per user
- Up to 10 accounts per day from single IP address
- 5 reward claims per week per device

### Scoping Questions You Should Always Ask

Before settling on a design, clarify:
- **Granularity**: per-IP, per-user, per-API-key, per-endpoint?
- **Window**: per-second, per-minute, per-day?
- **Quota type**: hard, soft, or quota?
- **Scale**: 1 K QPS or 1 M QPS?
- **Distribution**: single region or multi-region edge?
- **Strictness**: is exceeding the limit by 1% acceptable?
- **Failure mode**: open (allow when uncertain) or closed (deny when uncertain)?
- **Quota reset**: rolling window or fixed window?

The answers to these determine everything that follows.

## Step 2: High-Level Design

### Implementation Location

**Server-side placement** is preferred over client-side because clients cannot be trusted—requests can be forged by malicious actors.

**Rate limiter middleware** acts as a gatekeeper between clients and API servers, intercepting requests before they reach backend services.

### Request Flow

1. Client sends HTTP request through rate limiter middleware
2. Middleware evaluates if request count exceeds threshold
3. Under threshold → request routed to API servers
4. Over threshold → HTTP 429 response returned to client

**Deployment options include**:
- Embedded in application code
- Standalone middleware layer
- API Gateway component (increasingly common in microservices architecture)

### Decision: Middleware vs In-Process vs Edge

| Location | Pros | Cons | Best for |
|---|---|---|---|
| In-process (library) | Zero network hop, easy to start | Each service reimplements; inconsistent limits | Single-team monoliths |
| Middleware (sidecar or service mesh) | Centralized policy, language-agnostic | Adds a hop, deploys alongside every service | Kubernetes / service-mesh environments |
| API gateway (Kong, Envoy, AWS API Gateway) | Shared across all services, managed | Vendor coupling, harder to customize limits | Public APIs, B2B SaaS |
| Edge (Cloudflare, Fastly, Akamai) | Lowest latency, DDoS resilience | Eventually consistent counters, higher cost | Public web/mobile APIs at scale |

---

## Rate Limiting Algorithms

### 1. Token Bucket Algorithm

**Mechanism**: Tokens accumulate in a container at fixed rates; each request consumes one token.

**Parameters**:
- Bucket capacity (maximum tokens)
- Refill rate (tokens added per second)

**Operation**:
- Tokens refill at preset intervals until capacity reached
- Excess tokens overflow and are discarded
- Request proceeds if tokens available; otherwise rejected
- Each request consumes exactly one token

**Use case example**: Capacity of 4 tokens, 2 added per second. Three requests arrive within one second; first two pass (2 tokens consumed), third rejected (insufficient tokens).

**Advantages**:
- Simple implementation
- Memory efficient
- Allows controlled traffic bursts when tokens available

**Disadvantages**:
- Two parameters require careful tuning
- Finding optimal bucket size and refill rate can be challenging

**Real-world adoption**: Amazon and Stripe use this algorithm.

### 2. Leaking Bucket Algorithm

**Mechanism**: Requests queue in FIFO structure and process at fixed rates.

**Parameters**:
- Queue size (bucket size)
- Outflow rate (fixed request processing rate)

**Operation**:
- New request arrives → system checks queue fullness
- Queue not full → request added to queue
- Queue full → request discarded
- Requests drain from queue at consistent intervals

**Advantages**:
- Memory efficient with bounded queue
- Ensures stable, predictable outflow rate
- Suits systems requiring consistent throughput

**Disadvantages**:
- Burst traffic fills queue with older requests, potentially blocking newer ones
- Two parameters require tuning
- Less responsive to sudden traffic spikes

**Real-world adoption**: Shopify employs this approach.

### 3. Fixed Window Counter

**Mechanism**: Timeline divided into equal-sized windows; counter increments per request within window.

**Operation**:
- Each time window has associated counter
- Requests increment counter by one
- Counter exceeds threshold → new requests rejected
- Counter resets when new time window begins

**Example**: 1-second windows allow 3 requests maximum. Window at 1:00:00-1:00:01 permits 3 requests; window at 1:00:01-1:00:02 starts a new counter.

**Critical limitation**: "Requests at window boundaries can cause twice the allowed traffic to pass through during edge transitions."

**Example of edge case problem**: System allows 5 requests per minute. At 2:00:30-2:01:30 boundary, 10 total requests pass (5 from previous window + 5 from current), doubling the intended limit.

**Advantages**:
- Very simple to implement
- Minimal memory requirements
- Easy to understand logic

**Disadvantages**:
- Spike vulnerability at window boundaries
- Can permit double the quota during edge transitions

### 4. Sliding Window Log

**Mechanism**: Maintains timestamps of all requests; removes outdated entries when evaluating new requests.

**Implementation detail**: "Timestamp data is usually kept in cache, such as sorted sets of Redis."

**Operation**:
- Request arrives → remove timestamps older than current window start
- Add new request timestamp to log
- If log size ≤ allowed count → request accepted
- If log size > allowed count → request rejected

**Example scenario** (2 requests per minute allowed):
- 1:00:01 → log empty, request allowed (log size: 1)
- 1:00:30 → timestamp added, request allowed (log size: 2)
- 1:00:50 → timestamp added, request rejected (log size: 3 exceeds limit)
- 1:01:40 → remove timestamps before 1:00:40, request allowed (log size: 2 after cleanup)

**Advantages**:
- Highly accurate rate limiting
- Requests never exceed limit within any rolling window
- Prevents edge case problems of fixed window

**Disadvantages**:
- High memory consumption
- Stores timestamps even for rejected requests
- Expensive for systems with very high request volumes

### 5. Sliding Window Counter

**Mechanism**: Hybrid approach combining fixed window simplicity with sliding window accuracy.

**Implementation**: Calculates current window requests plus weighted previous window requests.

**Formula**: Current requests + (Previous window requests × Overlap percentage)

**Example**: 7 requests per minute limit. Current minute has 3 requests, previous minute had 5 requests. New request arrives at 30% into current minute:
- Calculation: 3 + (5 × 0.7) = 6.5 requests
- Rounded to 6 → request allowed (under 7-limit)

**Advantages**:
- Smooths traffic spikes using average rates
- Memory efficient compared to sliding window log
- Good balance of accuracy and performance

**Disadvantages**:
- Approximation method assuming even request distribution
- Not suitable for very strict lookback windows
- Minor inaccuracy (0.003% wrong per Cloudflare testing on 400M requests)

### Algorithm Deep Dive: Token Bucket Pseudocode

A reference implementation in Python that any candidate should be able to sketch in an interview:

```python
import time

class TokenBucket:
    """Refills `rate` tokens per second up to a max of `capacity`."""
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.rate = refill_rate           # tokens per second
        self.tokens = capacity
        self.last = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        delta = now - self.last
        self.tokens = min(self.capacity, self.tokens + delta * self.rate)
        self.last = now

    def allow(self) -> bool:
        self._refill()
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

# Usage: per-user bucket with 4 tokens capacity, 2 tokens/sec refill
bucket = TokenBucket(capacity=4, refill_rate=2.0)
if bucket.allow():
    handle_request()
else:
    return http_response(429)
```

This is single-process. Distributed versions need atomic Redis operations (see "Race Condition" section below).

---

## Step 3: Detailed Design

### Rate Limiting Rules Architecture

**Rule definition example** (Lyft open-source component):
```
domain: messaging
descriptors:
  - key: message_type
    value: marketing
    rate_limit:
      unit: day
      requests_per_unit: 5
```

This allows maximum 5 marketing messages daily.

**Storage approach**: Rules stored on disk, pulled into cache by worker processes.

### Handling Rate-Limited Requests

**HTTP 429 Response**: Standard status code indicating "too many requests" violation.

**Request disposition options**:
- Drop request immediately
- Enqueue for later processing (useful for critical operations like orders)

### Rate Limiter Headers

Clients receive three key HTTP headers:

- **X-Ratelimit-Limit**: Maximum calls allowed per time window
- **X-Ratelimit-Remaining**: Remaining allowed requests within window
- **X-Ratelimit-Retry-After**: Seconds to wait before retrying without throttling

### Detailed System Architecture

**Component responsibilities**:

1. **Rules Layer**: Persisted rate limiting configurations
2. **Worker Processes**: Periodically fetch rules from disk into cache
3. **Rate Limiter Middleware**: Intercepts requests, checks cache rules
4. **Redis Cache**: Stores counters and request tracking data
5. **Decision Point**: Routes based on limit status
   - Within limit → forward to API Servers
   - Exceeded → return 429 or queue for later processing

**Data flow**:
- Middleware loads rules from cache
- Fetches current counters from Redis
- Evaluates against limit threshold
- Updates Redis counter if request allowed
- Returns 429 if limit exceeded

### Redis Implementation Commands

**INCR**: Increments stored counter by one

**EXPIRE**: Sets automatic timeout for counter deletion after specified duration

These commands enable stateless, distributed rate limiting without database bottlenecks.

### Atomic Counter with Lua Script

The classic Redis "INCR + EXPIRE" pattern, plus a Lua-scripted atomic check-and-increment that avoids the read-modify-write race:

```python
# Atomic check-and-increment using a Lua script.
# KEYS[1] = counter key (e.g., "rl:user:42:1750000000")
# ARGV[1] = limit
# ARGV[2] = window seconds
LUA_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
end
if current > tonumber(ARGV[1]) then
    return 0   -- denied
end
return 1       -- allowed
"""

def is_allowed(redis_client, key: str, limit: int, window_sec: int) -> bool:
    result = redis_client.eval(LUA_SCRIPT, 1, key, limit, window_sec)
    return result == 1
```

Two properties matter: the increment and the expiry must happen atomically (otherwise a crash between INCR and EXPIRE can leak counters); and the limit check must happen in the same atomic step (otherwise concurrent requests can both see `current < limit` and both succeed past the threshold).

---

## Distributed Environment Challenges

### Race Condition Problem

**Scenario**: Multiple concurrent requests access same counter simultaneously.

**Problem sequence**:
1. Request 1 reads counter value (3)
2. Request 2 reads counter value (3) - simultaneously
3. Request 1 increments and writes back (4)
4. Request 2 increments and writes back (4)
5. Final value is 4, but should be 5 after two increments

This non-atomic operation causes counter inaccuracy.

**Solutions**:
- **Lua scripts**: Atomic operations at Redis level
- **Sorted sets**: Redis data structure enabling atomic increment-and-check operations

### Synchronization Across Multiple Rate Limiters

**Problem**: Stateless web tier routes clients to different rate limiter servers; each server unaware of other server's tracking data.

**Example**: Client 1 connects to Rate Limiter 1, Client 2 to Rate Limiter 2. If Client 1 later connects to Rate Limiter 2, no data exists about Client 1's prior requests.

**Solution - Centralized Redis**: All rate limiters query same Redis instance for counter state, enabling consistency regardless of which server handles request.

**Anti-pattern**: Sticky sessions (routing client to same server) are not recommended—lacks scalability and flexibility.

### Distributed Rate Limiting Architectures

| Pattern | Description | Pros | Cons |
|---|---|---|---|
| Centralized Redis (single instance) | All limiters read/write one Redis | Simple, consistent | Redis is SPOF unless replicated; latency to Redis limits throughput |
| Centralized Redis Cluster | Sharded Redis, one logical keyspace | Scales horizontally | Cross-shard operations (e.g., for composite limits) are awkward |
| Per-region Redis | Each region has its own counter store | Low latency, regional fault isolation | Quota becomes per-region (a user can use N in US and N in EU) |
| Gossiped local counters | Each node keeps local counters; gossip periodically | No central dependency | Eventually consistent; can over- or under-limit |
| Sliding window approximation | Each node computes local rate; periodically reconciles | Cheap, robust | Approximate; needs careful reconciliation logic |

---

## Performance Optimization

### Multi-Data Center Strategy

"Most cloud service providers build many edge server locations around the world" to reduce latency.

**Implementation**: Geographically distributed edge servers automatically route traffic to nearest location.

**Example**: Cloudflare operates 194 edge servers globally as of 2020, minimizing user latency.

### Eventual Consistency Model

Data synchronization across distributed rate limiters uses eventual consistency—acceptable temporary inconsistencies resolve over time rather than requiring immediate synchronization.

---

## Monitoring & Analytics

**Key metrics to track**:
- Algorithm effectiveness
- Rule effectiveness

**Monitoring purpose**: Identify whether rate limiting rules are appropriately tuned.

**Example interventions**:
- Overly strict rules → many false positives → relax thresholds
- Ineffectiveness during traffic spikes (flash sales) → consider token bucket for burst handling
- Rules not preventing actual abuse → strengthen thresholds

### Rate-Limiter-Specific Metrics Worth Tracking

| Metric | What it tells you |
|---|---|
| 429 rate per rule | Whether a rule is too aggressive |
| Cache hit rate on counter lookups | Whether your key strategy is correct |
| Latency p99 of the rate limiter middleware | Whether rate limiting itself is becoming a bottleneck |
| Allowed-after-deny ratio | Whether clients are honoring 429s |
| Counter eviction rate (Redis TTL) | Whether your window sizing matches traffic shape |
| Cross-region counter divergence | Health of multi-region consistency |

---

## Advanced Considerations

### Hard vs Soft Rate Limiting

- **Hard**: Requests strictly cannot exceed threshold
- **Soft**: Requests may exceed threshold briefly before enforcement

### Multi-Layer Rate Limiting

Rate limiting applicable at multiple OSI model layers:

- **Layer 3 (Network)**: IP address-based using Iptables
- **Layer 4 (Transport)**: TCP/UDP connection limiting
- **Layer 7 (Application)**: HTTP-level limiting (focus of this design)

### Client Best Practices for Avoiding Rate Limiting

- Implement client-side caching to reduce API calls
- Understand published limits before sending requests
- Catch exceptions and implement graceful error handling
- Use exponential backoff in retry logic with adequate delays
- Monitor remaining quota using response headers

---

## Bucket Selection Strategy

**Number of buckets depends on rule granularity**:

- Different API endpoints require separate buckets
- IP-based limiting requires bucket per IP address
- User-based limiting requires bucket per user ID
- Global limits may share single bucket across system

**Example**: User with three rate limit rules (1 post/sec, 150 friends/day, 5 likes/sec) requires 3 buckets.

### Composite / Hierarchical Limits

Real systems often apply multiple limits simultaneously:
- Per-user (e.g., 100 req/min)
- Per-endpoint (e.g., 10 searches/sec)
- Per-IP (e.g., 1000 req/min — catches unauthenticated abuse)
- Global (e.g., 100 K req/sec system-wide)

The right interpretation: the **most restrictive** applicable limit wins. The implementation: evaluate all matching rules, take the minimum remaining quota. This is what the Lyft rate-limit DSL is designed to express.

---

## Summary of Algorithm Comparison

| Algorithm | Accuracy | Memory | Burst Support | Complexity |
|-----------|----------|--------|---------------|------------|
| Token Bucket | Good | Low | Excellent | Low |
| Leaking Bucket | Good | Low | Poor | Low |
| Fixed Window | Poor | Low | Terrible | Very Low |
| Sliding Window Log | Excellent | High | Good | Medium |
| Sliding Window Counter | Good | Low | Good | Medium |

---

## Back-of-the-Envelope Math

A concrete workload to anchor the design:

**Assumptions:**
- 10 M DAU
- Each user makes 50 API calls per day on average
- Per-user limit: 100 req/minute
- Burst multiplier: 2x peak vs average

**QPS:**

```
Avg QPS = 10e6 * 50 / 86_400 ≈ 5,800
Peak QPS (2x) ≈ 11,600
```

**Per-user rate check (hot path):**

```
10,000 requests/sec / 10 M DAU = ~1 request/sec/user at peak
Each request needs:
  1 Redis GET (counter)
  1 Redis INCR + EXPIRE (atomic via Lua)
  ≈ 2 Redis ops per request
Total Redis ops: ~23 K ops/sec
```

A single Redis node handles ~100 K ops/sec for simple commands, so one Redis primary is enough — but you want a replica for read scaling and a Sentinel/Cluster setup for failover.

**Storage in Redis:**

```
Per user: counter key + expiry ≈ 100 bytes
10 M users active in last minute ≈ 10 M keys × 100 bytes ≈ 1 GB
TTL of 60 seconds means keys churn; Redis maxmemory-policy allkeys-lru
handles the case where memory is exhausted.
```

**Latency budget:**

```
Rate limiter check target: <5 ms p99
Redis round trip within region: ~0.5 ms
Lua script execution: ~0.1 ms
Total: ~1 ms p50, ~3 ms p99
```

**Bandwidth:**

```
Counter key + value payload: ~100 bytes
23 K ops/sec × 100 bytes ≈ 2.3 MB/s — trivial.
```

The math shows the design is feasible on commodity Redis with no exotic tuning. The interview lesson: most rate limiters are not bottlenecked by storage or bandwidth — they are bottlenecked by Redis tail latency under spikes.

---

## ASCII Architecture Diagrams

### 1. The Standard Request Path

```
         Client
           │
           ▼
       ┌─────────────────────────────────────────────┐
       │              Edge / CDN / WAF               │
       │   (TLS, geo-routing, L7 firewall)            │
       └────────────────────┬────────────────────────┘
                            │
                            ▼
                  ┌────────────────────┐
                  │   L7 Load Balancer │
                  └─────────┬──────────┘
                            │
                            ▼
              ┌──────────────────────────────┐
              │  Rate Limiter Middleware     │
              │  1. Read counter from Redis  │ ──miss──► increment + check
              │  2. Check against rule        │            │
              │  3. Decide allow/deny         │ ◄─────────┘
              └──┬──────────────────────────┘
                 │ allow (200/2xx)
                 ▼
              ┌──────────────────────────────┐
              │   Application API Servers    │
              │   (stateless, autoscaled)    │
              └──────────────────────────────┘

   On deny: HTTP 429 + Retry-After + X-RateLimit-Remaining: 0
```

### 2. Multi-Layer Rate Limiting (Edge + Gateway + Service)

```
            ┌────────────────────────────────────────────────────┐
            │  Layer 1: Edge (Cloudflare / Fastly)              │
            │  Rule: per-IP 10 K req/min, sliding window        │
            │  Purpose: DDoS shield                             │
            └─────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
            ┌────────────────────────────────────────────────────┐
            │  Layer 2: API Gateway (Kong / Envoy)              │
            │  Rule: per-user 100 req/min, token bucket         │
            │  Purpose: tenant quota                            │
            └─────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
            ┌────────────────────────────────────────────────────┐
            │  Layer 3: Service (in-process)                    │
            │  Rule: per-endpoint 10 req/sec, sliding window log│
            │  Purpose: protect expensive operations            │
            └────────────────────────────────────────────────────┘
```

A 429 may come from any of these layers. The client must respect the Retry-After header regardless.

### 3. Token Bucket State Transition

```
       tokens
         ▲
       4 │■■■■■■■■■■■■■■■■■■ (capacity = 4)
         │
       3 │                  ← refill at 2 tokens/sec
         │
       2 │       ╔════╗    request consumes 1 token
         │       ║    ║
       1 │       ║    ║  → if tokens == 0, reject
         │       ║    ║
       0 │───────╨────╨─────────► time (seconds)
         t=0   t=1   t=2

       Scenario: capacity=4, refill=2/s, 5 requests arrive at t=0:
         t=0.0 → tokens=4 → allow (tokens=3)
         t=0.0 → tokens=3 → allow (tokens=2)
         t=0.0 → tokens=2 → allow (tokens=1)
         t=0.0 → tokens=1 → allow (tokens=0)
         t=0.0 → tokens=0 → DENY (HTTP 429)
         t=0.5 → tokens=1 (refilled at 2/sec) → allow next request
```

### 4. Sliding Window Approximation

```
       Window: 1 minute, limit = 7 req/min
       Current time: 00:00:30 (30% into current minute)

       Previous minute (00:00:00–00:01:00):
       5 requests landed
                 ┌──────┐
                 │  5   │ ← 70% of the previous window is "still in view"
                 └──────┘
       ══════════════════════════════════════  ← window boundary
       Current minute (00:00:30 into 00:01:00):
       3 requests so far
                 ┌──────┐
                 │  3   │ ← 30% of the current window is "in view"
                 └──────┘

       Weighted count = 3 + (5 × 0.7) = 6.5
       New request: count would be 7.5 → DENY (over 7)
```

---

## Trade-off Tables

### Where to Compute the Rate Limit

| Location | Latency added | Operational burden | Accuracy | Notes |
|---|---|---|---|---|
| Client SDK | 0 (local) | High (every client must implement) | Approximate (clock skew, replay) | Game SDKs, mobile apps |
| Edge / CDN | <1 ms typical | Low (vendor-managed) | Eventual consistency | Best for global products |
| API Gateway | 1-5 ms typical | Medium (you run it) | Strong | Most production systems |
| Service-mesh sidecar | 1-3 ms typical | Medium | Strong | Kubernetes-native |
| In-process (library) | <0.5 ms | Low (one codebase) | Strong | Monoliths |
| Database row lock | 5-50 ms | Low | Strong but slow | Last resort; do not do this |

### Algorithm Choice by Use Case

| Use case | Recommended algorithm | Why |
|---|---|---|
| API rate limit per user (most common) | Token bucket | Burst-friendly, simple, widely understood |
| Search endpoint (expensive operation) | Sliding window counter | Smooth, no edge spike |
| Sign-up or signup-like abuse prevention | Fixed window with strict per-IP | Simple, cheap |
| Stripe-style "request idempotency" | Idempotency key, not rate limit | Different problem |
| Billing/Quota (per-customer monthly) | Fixed window (calendar month) | Aligns with billing cycle |
| DDoS mitigation (L3/L4) | Token bucket at edge | Burst absorption, low cost per packet |
| Internal microservice (per-call limits) | Leaking bucket | Smooth downstream load |

### Storage Choice for Counters

| Store | Latency | Consistency | Cost | Operational burden |
|---|---|---|---|---|
| Redis (single) | ~0.5 ms | Strong | $$ | Low |
| Redis Cluster | ~1-2 ms | Strong (per-key) | $$$ | Medium |
| Memcached | ~0.5 ms | Eventual (no replication) | $ | Low |
| DynamoDB | ~5-10 ms | Strong | $$$$ | Very low (managed) |
| In-process (per-node) | ~0 ms | Per-node only | Free | High |
| FoundationDB | ~5 ms | Strong + global | $$ | Medium |

---

## Real-World Case Studies

### 1. Cloudflare's Global Rate Limiter

Cloudflare runs rate limiting at the edge in front of millions of customer sites. Their algorithm is a sliding-window counter, with counters stored in their globally distributed key-value store (referenced in talks as "Quicksilver"). The decision is made at the closest edge location, with eventual consistency across regions. The cost: a user can briefly exceed their limit when counters have not yet propagated. The benefit: decisions are made in <1 ms at the closest of 300+ PoPs. Cloudflare publicly disclosed that this approach showed only ~0.003% inaccuracy across 400 M tested requests — good enough for almost every real workload. Lesson for interviews: name Cloudflare's algorithm explicitly when discussing sliding window counter; the ~0.003% number is interview gold.

### 2. Stripe's Idempotency Keys (Often Confused with Rate Limiting)

Stripe's idempotency-key design is technically not a rate limiter but is often discussed in the same conversation because it solves the related "what happens when a client retries?" problem. Every state-changing Stripe API accepts an `Idempotency-Key` header. The server stores the request hash and response for 24 hours; a retry with the same key returns the cached response without re-executing. This is the canonical answer to "what do you do when a client retries a payment?" The interview lesson: distinguish "rate limiting" (control rate of incoming requests) from "idempotency" (safe retry of identical requests). Stripe does both, and both are essential to a robust payment API.

### 3. Twitter's Per-User Tweet Rate Limiter

Twitter enforces (and has historically enforced) per-user tweet rate limits — at various points 2,400 tweets/day, 50 retweets/hour, etc. The implementation lives at the edge of the API gateway, before the request hits any expensive service (search indexing, timeline fanout). When a user exceeds their limit, they get an HTTP 429 with a Retry-After header indicating when they can resume. The interview lesson: rate limiting is most useful when it is placed before the expensive operation. Putting it in the same service as the expensive operation defeats much of its value.

### 4. GitHub's Abuse Rate Limiter

GitHub operates a public-facing API and an abuse-detection layer that watches for unusual patterns (rapid repo creation, automated scraping, mass star/fork activity). Their rate limiter combines per-user limits, per-IP limits, and an anomaly-detection layer that triggers stricter limits when behavior deviates from a user's historical baseline. The interview lesson: simple token-bucket limits are the floor; sophisticated systems layer behavior-based limits on top.

### 5. Shopify's Leaky Bucket for Storefront API

Shopify publicly described using a leaky bucket for their Storefront API: requests queue in a FIFO at the edge, and a worker drains them at a fixed rate. The benefit: a stable downstream rate regardless of inbound burst pattern. The cost: extra latency under burst. The interview lesson: leaky bucket is the right answer when downstream services are sensitive to bursty load — for example, a database with limited connection pool.

---

## Common Pitfalls & Failure Modes

### Pitfall 1: Race Conditions Without Atomic Operations

The classic mistake: read counter, check, increment — across three Redis commands. Two concurrent requests can both read the same value, both see "under limit," both increment, and both pass. Fix: use a Lua script that does check-and-increment atomically. In Redis, Lua scripts run single-threaded and the check-and-increment happens in one atomic step. For other stores (Memcached, DynamoDB), use the equivalent conditional update primitive (`ADD` with expiry in Memcached; conditional write in DynamoDB).

### Pitfall 2: Choosing Fixed Window for Anything User-Facing

Fixed window is the algorithm everyone reaches for first because it is the simplest to implement. It is also the algorithm that lets users double their quota at window boundaries. If your product has any user-facing limit that matters (e.g., "free tier gets 100 messages per hour"), fixed window will be exploited by sophisticated users who time their bursts to align with the boundary. Fix: use sliding window counter, sliding window log, or token bucket. Fixed window is only acceptable for very coarse-grained limits (per-day quotas where 2x at the boundary is acceptable).

### Pitfall 3: Counting Rejected Requests

A subtle but common bug: counting requests that were rejected by the rate limiter toward the user's quota. This means a user who is rate-limited and keeps retrying will burn additional quota. In token bucket: a request that is denied should not consume a token. In sliding window log: the timestamp should not be added. In sliding window counter: the increment should not happen. Most libraries get this right, but if you implement from scratch, verify the behavior.

### Pitfall 4: Synchronous Dependencies on Rate-Limit State

The rate limiter middleware sits in front of the application. If Redis is slow, the entire request path is slow. If Redis is down, requests either fail (closed mode — most secure) or pass through (open mode — most available). The choice between open and closed mode is a policy decision, not a technical one. Banks usually close; ad-tech usually opens. Make the choice explicit and configurable.

### Pitfall 5: Treating Limits as Static Configuration

A limit set at launch and never re-evaluated is a limit that is either too restrictive (users complain) or too permissive (abuse continues). Real systems monitor the 429 rate per rule, identify misbehaving clients or rules, and adjust. The interview lesson: limits are policy, and policy needs review. A team that ships rate limiting without monitoring is shipping a config file, not a system.

### Pitfall 6: Per-User Limits Without Per-IP Limits

A "no authenticated users" attack: an attacker creates thousands of accounts and makes 100 req/sec per account. The per-user rate limit is fine; the per-IP limit is breached. The fix: always layer per-IP limits on top of per-user limits. The per-IP limit catches the bulk attack; the per-user limit catches the individual abuser.

---

## Interview Q&A

### Q1: "How do you choose between token bucket, sliding window, and fixed window?"

**Answer sketch:** Token bucket when bursts are acceptable and you want a simple, well-understood algorithm. Sliding window counter when bursts are not acceptable and you want a smooth limit. Sliding window log when accuracy matters more than memory cost and the limit is small. Fixed window only when the limit is coarse-grained (per day) and doubling at the boundary is acceptable. Name the use case ("API rate limit per user") and the answer follows.

### Q2: "How does the rate limiter handle a Redis outage?"

**Answer sketch:** Two modes. Closed mode: when Redis is unreachable, fail closed (deny all requests). Safer, but takes the system down with Redis. Open mode: when Redis is unreachable, fail open (allow all requests). Available, but lets attackers exploit the outage. The right answer for most products is configurable — closed mode by default for sensitive endpoints (payments, signup), open mode for tolerant ones (analytics, search). Document the choice and surface it in monitoring.

### Q3: "How do you avoid the thundering herd when a popular user's quota resets?"

**Answer sketch:** Jittered TTLs — instead of all counters expiring at the exact same instant, give each counter a small random additional TTL so they expire at slightly different times. Alternatively, refresh-ahead: a background job pre-increments and decrements counters so the post-reset stampede is smoothed. For sliding window, the issue is less acute because the window slides continuously.

### Q4: "How would you 10x the rate of incoming requests without 10x the Redis load?"

**Answer sketch:** Three techniques. First, edge rate limiting at CDN/PoP — most requests are denied before they hit your origin Redis. Second, local approximation — each node keeps a local counter that is correct within some tolerance, only reaching Redis periodically. Third, sharded Redis with the limiter middleware pinning to the shard that owns the user's counter. Combined, the Redis load grows much slower than linear.

### Q5: "How do you handle rate limiting for a global product with users in 100+ countries?"

**Answer sketch:** Deploy rate limiters at edge locations (Cloudflare, Akamai, Fastly, your own PoPs). Each edge makes decisions locally. Counters eventually propagate across regions via a distributed key-value store with eventual consistency. Accept that users may briefly exceed their limit by ~0.003% (Cloudflare's published number) for the cross-region window. The alternative — global strong consistency — costs tens of milliseconds and is not worth it for rate limiting.

### Q6: "How do you distinguish a legitimate burst from an attack?"

**Answer sketch:** Three signals. First, request rate history per user — a 10x jump for a user with stable history is suspicious. Second, IP reputation — known-bad IPs are stricter. Third, request pattern shape — many endpoints with similar timing is bot-shaped; varied endpoints with human-shaped timing is not. A simple threshold check on rate is the first layer; anomaly detection on shape is the second.

### Q7: "What about rate limiting for WebSocket connections vs HTTP requests?"

**Answer sketch:** Different shape entirely. HTTP is short-lived: you count requests. WebSocket is long-lived: you count connection time, messages per second within the connection, and concurrent connections per user. The algorithm is similar (token bucket), but the "thing being counted" is different. Some systems use connection-rate limits (e.g., max 5 new connections per minute per IP) plus message-rate limits within the connection.

### Q8: "How do you test rate limiting without disrupting production?"

**Answer sketch:** Three test layers. Unit tests: each algorithm with synthetic inputs. Integration tests: a staging environment with a real Redis and synthetic load (k6, vegeta, locust). Shadow tests: in production, run the rate limiter in "log only" mode for a week — let it decide what to allow or deny, but always allow the request. Compare its decisions to your manually-tuned rules to find drift. Then flip to enforcement.

---

## Key Terms / Glossary

| Term | What people say | What it actually means |
|---|---|---|
| Token bucket | "Bucket of tokens." | A counter that refills at a fixed rate, capped at a max capacity; each request consumes one token. Allows bursts up to capacity, smooths over longer intervals. |
| Leaky bucket | "Drip the requests." | A FIFO queue with a fixed outflow rate; absorbs bursts into the queue. Trades latency for stability. |
| Fixed window | "Count per minute." | A counter that resets at fixed intervals (every minute on the minute). Simple but allows 2x bursts at boundaries. |
| Sliding window log | "All timestamps." | A sorted set of recent request timestamps; new requests check the set size. Perfectly accurate, memory-heavy. |
| Sliding window counter | "Weighted average." | Hybrid that weights the previous window by overlap with the current window. Cheap and ~99.997% accurate. |
| 429 Too Many Requests | "You exceeded the limit." | The standard HTTP response code for rate-limited requests. Should include Retry-After and rate-limit headers. |
| Retry-After | "Wait this long." | HTTP header indicating seconds (or HTTP date) the client should wait before retrying. Critical for cooperative clients. |
| Idempotency key | "Same request twice = same effect." | A client-generated token that lets the server recognize retries and return the cached response. Distinct from but related to rate limiting. |
| Open vs closed mode | "What happens when Redis dies." | Closed: deny requests when rate-limit state is unavailable (safer). Open: allow requests (more available). Always make this a policy decision, not an accident. |
| Quota | "How much you get per period." | A rate limit with a billing implication (e.g., 10 K requests/month on the free tier). Usually fixed-window aligned to the billing cycle. |
| Burst | "Spike of requests." | A short interval where request rate exceeds the steady-state limit. Token buckets absorb bursts up to capacity; leaky buckets absorb them into a queue; fixed windows let them through at boundaries. |
| Stricter-than | "One limit can override another." | When multiple limits apply (per-IP, per-user, per-endpoint), the most restrictive one wins. This is the default semantic in production rate limiters. |
| Edge rate limiting | "Limit at the CDN." | Making rate-limit decisions at the closest edge PoP instead of at the origin. Lowest latency, but counters may eventually-consistently diverge across regions. |

---

## Key Takeaways

1. Server-side implementation provides security; client-side cannot be trusted
2. Token bucket offers best best balance of simplicity and practical effectiveness for most use cases
3. Centralized Redis enables distributed consistency without sticky sessions
4. Atomic operations critical for race condition prevention
5. Multi-data center edge deployment minimizes global latency
6. Monitoring and tuning ensure rules match business requirements
7. HTTP headers provide client feedback on limit status and retry timing

### Final Note for Interviews

The strongest rate-limiter interview answers do three things in 45 minutes:
1. Pick an algorithm (token bucket is the safe default) and defend it briefly.
2. Describe the distributed-state layer (Redis + Lua for atomicity, with eventual consistency at the edge).
3. Discuss what happens when it fails (open vs closed mode, monitoring, alerting).

Everything else — the exact headers, the policy DSL, the layered design — is supporting detail. Practice the three core moves until you can deliver them in under 10 minutes; the rest is conversation.