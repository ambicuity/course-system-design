# Latency vs. Throughput

> Two different stories of performance — one is what each user feels, the other is what the system delivers. Confusing them produces wrong optimizations.

**Type:** Learn
**Prerequisites:** Basic performance awareness
**Time:** ~15 minutes

---

## The Problem

"Make it faster" is a common engineering request. It is also ambiguous. Does it mean each request takes less time, or does it mean the system handles more requests? Those are two different things — called **latency** and **throughput** — and optimizing for one does not automatically improve the other.

A system can have:
- Low latency *and* low throughput (a tiny system that responds quickly but to few users)
- Low latency *and* high throughput (a well-designed system at scale — hard to achieve)
- High latency *and* high throughput (a system that batches requests, doing many at once but each slowly)
- High latency *and* low throughput (a struggling system — usually broken)

Most performance conversations go wrong because the participants are optimizing for different things. This lesson draws the distinction clearly, shows the relationship, and gives you the metrics and patterns for each.

---

## The Concept

### Latency: time for one request

**Latency** is the time delay for a single operation. It is what users feel when they click a button and wait.

```
   User clicks "Buy"
        │
        │─── Client processing ─── 5 ms
        │
        │─── Network to server ──── 50 ms
        │
        │─── Server processing ─── 80 ms
        │
        │─── Database query ────── 30 ms
        │
        │─── Network back ──────── 50 ms
        │
        │─── Client render ─────── 10 ms
        │
        ▼
   User sees confirmation
   Total latency: ~225 ms
```

**What latency includes:**

- Client-side processing (parsing, rendering)
- Network round-trip time (RTT)
- Server processing (CPU time)
- Queue wait time (waiting for resources)
- Database query time
- Network return

**Latency metrics:**

- **Average** — what most users experience
- **p50 (median)** — half of users experience this or less
- **p95** — 95% of users experience this or less (the "long tail" begins here)
- **p99** — 99% of users experience this or less (the worst case for almost everyone)
- **p99.9** — the experience of the unluckiest users

**Latency targets:**

- < 100 ms: feels instantaneous (web interaction)
- < 300 ms: feels responsive (most UI)
- < 1 second: feels like the user is in control
- > 1 second: the user starts to lose focus
- > 10 seconds: the user is gone

---

### Throughput: work done per unit of time

**Throughput** is how much work the system completes per second. It is capacity — how many requests can be handled at once.

```
   Throughput examples:
     - Requests per second (RPS)
     - Queries per second (QPS)
     - Transactions per second (TPS)
     - Bytes per second (bandwidth)
     - Messages per second (queue throughput)
     - Records processed per second (ETL jobs)
```

**Throughput metrics:**

- **Requests per second** — most common for web services
- **Concurrent users** — how many users can be active at once
- **Bytes per second** — for streaming or data systems
- **Peak vs sustained** — peak is the burst; sustained is what the system can hold indefinitely

**Throughput targets:**

- "Support 10,000 concurrent users"
- "Process 1 million events per second"
- "Stream 10 GB/s of log data"

---

### The relationship

```
   ┌─────────────────────────────────────────────────────────────┐
   │                                                             │
   │   Throughput  =  Concurrency  /  Latency                    │
   │                                                             │
   │   (Little's Law)                                            │
   │                                                             │
   │   Example:                                                 │
   │     Latency: 100 ms                                         │
   │     Concurrent users: 1000                                  │
   │     Throughput: 1000 / 0.1 = 10,000 requests/sec          │
   │                                                             │
   └─────────────────────────────────────────────────────────────┘
```

**Little's Law** says: throughput = concurrency / latency. This is one of the most useful formulas in performance engineering.

```
   To increase throughput, you can:
     1. Increase concurrency (more users, more parallel requests)
     2. Decrease latency (each request finishes faster)
     3. Both
```

**The trade-off:**

- You can increase throughput without affecting latency by adding more servers (scale horizontally). Each server handles its share; total throughput goes up; individual latency stays the same.
- You can decrease latency without affecting throughput by making the code faster (optimize hot paths). Each request finishes faster; throughput stays the same; individual latency drops.
- Sometimes decreasing latency *increases* throughput (faster responses free up server resources for more requests).
- Sometimes increasing throughput *increases* latency (adding load to a saturated system slows everyone down).

---

### The latency profile

Most systems do not have a single latency. They have a distribution. The distribution is what you optimize.

```
   Latency distribution (1000 requests):

   0-50ms   ████████████████████ 200
   50-100ms ████████████████████████ 350
   100-200ms ███████████████ 200
   200-500ms ████████ 120
   500ms-1s ████ 60
   1-2s     ████ 50
   2-5s     ██ 20

   p50:  ~80 ms
   p95:  ~600 ms
   p99:  ~1.5 s
```

**Why p99 matters more than average:**

The average masks the long tail. A system with 100 ms average and 5 s p99 means most users are fine, but 1% of users wait 5 seconds. That 1% are your most engaged users (heavy use) and your paying customers (B2B). Optimizing p99 is often more impactful than optimizing the average.

---

### Tail latency amplification

In a distributed system, every request fans out to multiple services. The latency is the *sum* of the call latencies, and percentiles compose in surprising ways.

```
   A request that calls 5 services, each with p99 = 100ms:
   p99 of the combined request = ?

   It's NOT 500ms.

   p99 of 5 independent services (each p99 = 100ms) ≈ 410ms
   p99 of 10 independent services (each p99 = 100ms) ≈ 500ms

   To keep p99 of the combined request at 100ms,
   each service must have p99 ≈ 10-20ms.
```

**This is why microservice p99 targets are so aggressive.** A single request that fans out to 10 services, each with p99 = 50 ms, will have a combined p99 of ~200 ms. To hit a 100 ms p99 target at the API level, every service must be much faster than that.

---

### The batching trade-off

Some optimizations trade latency for throughput, or vice versa. Batching is the classic example.

```
   Without batching:
     1000 individual requests
     Each takes 10 ms
     Total: 10,000 ms (10 seconds)
     Throughput: 100 requests/sec per server

   With batching (batch size = 100):
     10 batched requests
     Each takes 50 ms
     Total: 500 ms
     Throughput: 2000 requests/sec per server (20x higher)
     But individual request latency: 50 ms (5x slower)
```

**When batching helps:**

- Database writes (group inserts)
- Network requests (combine packets)
- ML inference (batch multiple inputs)
- Bulk operations (re-index, batch email)

**When batching hurts:**

- User-facing requests where latency matters (typing, scrolling)
- Operations that block on a single item (single user lookup)

---

### Optimizing latency

Techniques to reduce latency:

| Technique | What it does | Cost |
|---|---|---|
| **Caching** | Serve from memory | Memory, staleness |
| **CDN** | Serve from edge | Money, cache invalidation |
| **Compression** | Less data over the wire | CPU time |
| **Connection pooling** | Reuse TCP connections | Memory |
| **Async / non-blocking I/O** | Don't wait for slow operations | Code complexity |
| **Database indexing** | Faster lookups | Write speed, disk |
| **Query optimization** | Less work in the DB | Time |
| **Caching queries** | Skip the DB entirely | Memory, staleness |
| **Code profiling** | Find the actual hot path | Engineering time |
| **Algorithm improvement** | Faster algorithm | Engineering time |
| **Hardware** | Faster CPU, faster disk | Money |

---

### Optimizing throughput

Techniques to increase throughput:

| Technique | What it does | Cost |
|---|---|---|
| **Horizontal scaling** | Add more servers | Money, operational complexity |
| **Vertical scaling** | Bigger servers | Money (eventually hits limits) |
| **Connection pooling** | Reuse connections | Memory |
| **Async / non-blocking I/O** | Handle more concurrent requests | Code complexity |
| **Batching** | Process many at once | Latency |
| **Caching** | Skip work entirely | Memory, staleness |
| **Database read replicas** | Spread read load | Replication lag |
| **Sharding** | Spread write load | Cross-shard complexity |
| **Queue-based architecture** | Decouple producers and consumers | Eventual consistency |
| **CDN** | Serve static content from edge | Money, invalidation |

---

### The "long-tail latency" problem

In real systems, the latency distribution has a long tail. The p99 is often 10× higher than the median. Optimizing for the average hides this.

**Causes of tail latency:**

- GC pauses in managed runtimes
- Network packet retransmissions
- Disk seeks (HDD); less on SSD
- Cold cache misses (after eviction or restart)
- Background jobs running concurrently
- CPU contention with other processes
- TCP retransmit timeouts (often 200ms-1s)

**Tail-tolerant techniques:**

- Hedged requests: send the same request to two servers, use whichever returns first
- Request budgets: enforce a deadline; cancel slow requests
- Load shedding: reject requests when overloaded to keep tail latency low
- Pre-warm caches and connections to avoid cold starts

---

## Build It / In Depth

### Measuring latency and throughput correctly

**Latency measurement:**

```python
# BAD: measuring average only
total_time = 0
for request in requests:
    total_time += measure(request)
print(f"Average: {total_time / len(requests)}ms")

# GOOD: measuring percentiles
latencies = [measure(r) for r in requests]
latencies.sort()
p50 = latencies[len(latencies) // 2]
p95 = latencies[int(len(latencies) * 0.95)]
p99 = latencies[int(len(latencies) * 0.99)]
print(f"p50: {p50}ms, p95: {p95}ms, p99: {p99}ms")
```

**Throughput measurement:**

```
   Sustained throughput:
     - Run a load test for at least 5 minutes
     - Measure requests per second averaged over the run
     - Confirm the system is not in a transient state

   Peak throughput:
     - Ramp up load until error rate exceeds threshold
     - The RPS at that threshold is peak throughput
     - This is what capacity planning needs
```

**Combined measurement:**

For a real system, report both:

```
   System: search-api
   Sustained throughput: 10,000 RPS
   Latency at 10k RPS: p50=20ms, p95=80ms, p99=300ms
   Peak throughput: 18,000 RPS (errors start above 16k)
   Latency at peak: p50=50ms, p95=500ms, p99=2s
```

A complete performance picture requires both numbers.

---

### Common mistakes

**Mistake 1: optimizing the average**

```
   Average latency: 100 ms (looks great)
   p99 latency: 5 seconds (terrible for the worst 1%)

   Optimizing the average by 10% saves 10 ms.
   Optimizing p99 by 10% saves 500 ms.
```

The long tail is where most user pain lives. Always look at p95 and p99.

**Mistake 2: optimizing for throughput when latency is the problem**

```
   "We added a batch job that increased throughput by 3x."
   "But each request now takes 5 seconds."

   Users will notice latency first. Throughput that exceeds demand is wasted.
```

**Mistake 3: optimizing for latency when throughput is the problem**

```
   "We optimized the hot path from 10 ms to 1 ms."
   "But we can only handle 1000 concurrent users before saturating."

   The bottleneck was never per-request speed; it was system capacity.
```

**Mistake 4: testing at low load**

```
   Latency at 100 RPS: 10 ms
   Latency at 10,000 RPS: 800 ms

   Test at production load. Low-load benchmarks are misleading.
```

**Mistake 5: ignoring cold starts**

```
   First request after deploy: 5 seconds (cold caches, JIT not warmed)
   Steady state: 20 ms

   Users hitting a cold server experience terrible latency.
   Pre-warm caches; use readiness probes; gradual rollouts.
```

---

### The capacity-planning formula

Use Little's Law to plan capacity:

```
   Required throughput (RPS) = (peak concurrent users × requests per user per second)
   Latency budget per request = SLA target
   Required concurrency = RPS × latency (in seconds)
   Required servers = ceiling(required concurrency / max concurrent requests per server)
```

**Example:**

- 100,000 concurrent users
- Each user makes 1 request per minute = 0.0167 RPS per user
- Total RPS = 100,000 × 0.0167 = 1,667 RPS
- Latency budget: 200 ms
- Required concurrency = 1,667 × 0.2 = 334 concurrent requests
- Each server handles 100 concurrent requests before saturation
- Required servers = ceiling(334 / 100) = 4 servers

Add 2–3x for headroom and burst traffic. So 12–16 servers in this example.

---

## Use It

### When to optimize for which

| Situation | Optimize for | Why |
|---|---|---|
| User-facing interactive UI | Latency | Users feel every millisecond |
| Background data processing | Throughput | Nobody waits for it directly |
| API serving web requests | Both | p99 latency + sustained throughput |
| Batch analytics job | Throughput | Latency measured in hours |
| Real-time trading system | Latency (p99) | Microseconds matter |
| File upload service | Throughput | Need to handle large payloads |
| Search engine | Both | Fast results + many queries |

---

### Cheat sheet for performance review

When someone says "make it faster":

```
   1. Ask: latency, throughput, or both?
   2. Ask: which percentiles? (p50, p95, p99)
   3. Ask: under what load?
   4. Measure the current state (don't guess)
   5. Identify the bottleneck (profile, don't guess)
   6. Apply the smallest change that addresses the bottleneck
   7. Measure again
   8. Repeat until target is met
```

---

## Common Pitfalls

- **Conflating latency with throughput.** A system with low latency can still have low throughput (if it has few resources), and vice versa.

- **Optimizing the average.** p95 and p99 are where user pain lives.

- **Testing at low load.** Real production load reveals bottlenecks that benchmarks miss.

- **Ignoring cold starts.** The first request after deploy is always slow; users see this.

- **Batching without thinking about latency.** Batching helps throughput but hurts latency. Match the strategy to the workload.

- **Over-provisioning for latency.** A 10 ms improvement that costs 10x more compute is rarely worth it.

- **Measuring the wrong percentile.** "p99 = 100 ms" sounds great until you realize 1% of users experience 100 ms; the rest experience less. The 1% you should worry about is the 1% of *slow* requests, which often dominate the experience of your heaviest users.

- **Believing benchmark claims.** Benchmarks usually measure different scenarios than your workload. Run your own.

---

## Exercises

1. **Easy** — Define latency and throughput in one sentence each. Give an example of a system where you would optimize for each.

2. **Medium** — Take a real API you have built or used. Estimate its p50, p95, and p99 latency. Identify which operations contribute most to p99. Propose one optimization that would improve p99 specifically.

3. **Hard** — A system needs to serve 1 million concurrent users with p99 latency under 200 ms. Each user makes 5 requests per minute on average. Use Little's Law to calculate the required number of servers, the required RPS, and the average concurrency. Justify each assumption.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Latency | Response time | The time delay for a single operation; what users feel |
| Throughput | Speed | The amount of work completed per unit of time; how much the system can do |
| p99 | The worst case | The 99th-percentile latency — the experience of the slowest 1% of requests; the long tail |
| Little's Law | A formula | Throughput = concurrency / latency; the fundamental relationship between the two |
| Tail latency | A p99 issue | High latency at the high percentiles (p95, p99, p99.9); often dominates user experience |
| Batching | An optimization | Processing multiple requests together; increases throughput but adds latency per request |
| Cold start | A one-time slowdown | The latency penalty for the first request after a server starts; cache misses, JIT not warmed |
| Tail-tolerant | Resilient design | Architecture that handles long-tail latencies (hedged requests, deadlines, load shedding) |

---

## Further Reading

- **"Designing Data-Intensive Applications"** — Martin Kleppmann's chapters on latency and consistency: https://dataintensive.net/
- **Google SRE Book — Chapter on Latency** — the source of "the long tail" framing: https://sre.google/sre-book/availability-table/
- **Brendan Gregg's Performance Page** — deep technical resources on performance analysis: https://www.brendangregg.com/
- **"Systems Performance"** — Brendan Gregg's book, the definitive guide: https://www.brendangregg.com/systems-performance-2nd-edition-book.html
- **HdrHistogram** — the canonical tool for measuring percentiles: https://github.com/HdrHistogram/HdrHistogram