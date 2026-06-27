# How to Debug a Slow API?

> Measure first, fix second — guessing where the bottleneck lives is almost always wrong.

**Type:** Learn
**Prerequisites:** REST API Design, Database Indexing Basics, Caching Strategies
**Time:** ~25 minutes

---

## The Problem

Your API endpoint that returned data in 120 ms last month now takes 2.4 seconds. Users are dropping requests and opening support tickets. The engineering team starts throwing solutions at the wall — "maybe we need Redis?", "let's add a CDN", "we should rewrite it in Go" — none of them based on actual evidence.

This is the classic slow-API situation: high perceived urgency plus low actual data. Every hour spent optimizing the wrong layer is an hour the real culprit stays hidden. A team that adds a cache in front of a query that runs 200 times per request will see a warm-cache speedup of nearly zero because the bottleneck was never the network.

The fix is a systematic layered investigation. APIs are pipelines: a request enters through the network, reaches backend code, touches a database or external service, and travels back. Latency always lives in one or more of those layers. Your job is to isolate which layer is responsible before you write a single line of remediation code.

---

## The Concept

### The API Request Pipeline

Every HTTP request passes through a predictable sequence of stages. Measuring the time spent in each stage tells you where to look next.

```
Client
  │
  ▼
[1] DNS + TCP + TLS handshake       ← Network / CDN layer
  │
  ▼
[2] Load Balancer / Reverse Proxy   ← Infrastructure layer
  │
  ▼
[3] Web Server / Framework routing  ← Application layer
  │
  ▼
[4] Business Logic Execution        ← Code layer
  │         │
  ▼         ▼
[5] DB    [6] External APIs         ← I/O layer
  │
  ▼
[3] Serialization + Response send   ← Application layer
  │
  ▼
Client
```

Latency added at each stage accumulates. A 10 ms database query repeated 80 times (N+1) contributes 800 ms before any other stage is counted.

### The Five Root-Cause Categories

| Category | Typical Symptoms | Key Signals |
|---|---|---|
| **Network / CDN** | High TTFB from certain regions, large transfer sizes | `Content-Length`, `Transfer-Encoding`, no cache headers |
| **Backend Code** | High CPU, long spans in traces, thread pool exhaustion | Profiler flame graphs, blocking I/O in hot paths |
| **Database** | Slow query logs, spiky latency correlated with writes | `EXPLAIN ANALYZE`, missing indexes, lock waits |
| **External APIs** | Latency matches third-party SLA variance, timeouts | Trace spans for outbound calls, dependency error rates |
| **Infrastructure** | Latency rises with load, not with data size | CPU/memory saturation, connection pool exhaustion |

### Measurement Before Action

The diagnostic tools you reach for depend on what you already know:

- **You know the slow endpoint** → attach distributed tracing and look at the waterfall of spans.
- **You don't know which endpoint** → aggregate p95/p99 latency per endpoint in your observability platform and sort descending.
- **It's intermittent** → correlate the spikes against traffic volume, background jobs, and dependency health dashboards.

Never rely on `average` response time alone. An endpoint averaging 200 ms but with a p99 of 4 s has a hidden tail-latency problem that averages hide.

---

## Build It / In Depth

Follow this layered process in order. Stop and fix at the first layer where you find a genuine bottleneck, verify the fix, then continue checking lower layers.

### Step 1 — Capture a Baseline with Real Numbers

Before touching anything, record the current behavior.

```bash
# Measure raw HTTP latency with curl (skips DNS cache)
curl -o /dev/null -s -w "
DNS lookup:   %{time_namelookup}s
TCP connect:  %{time_connect}s
TLS handshake:%{time_appconnect}s
TTFB:         %{time_starttransfer}s
Total:        %{time_total}s
" https://api.example.com/v1/orders/42

# Run 50 concurrent requests and summarize with hey
hey -n 500 -c 50 https://api.example.com/v1/orders/42
```

Record p50, p95, p99. This is your control group. Every change you make gets compared against it.

### Step 2 — Check the Network Layer

```
Client ──→ [DNS + TCP + TLS] ──→ Server

High time_connect → routing or firewall issue
High time_appconnect → TLS config (cipher mismatch, large cert chains)
Large transfer → missing compression
```

**Quick wins:**

```nginx
# Enable gzip in Nginx
gzip on;
gzip_types application/json text/plain;
gzip_min_length 1024;

# Add cache headers for static/semi-static endpoints
add_header Cache-Control "public, max-age=60, stale-while-revalidate=30";
```

If your users are geographically spread, add a CDN (Cloudflare, CloudFront) in front of responses that are cacheable. A 300 ms RTT from Singapore to us-east-1 becomes 15 ms from the nearest edge PoP.

### Step 3 — Profile Backend Code

Network looks fine but the endpoint is still slow? Attach a profiler.

```python
# Python — use cProfile for a quick flame graph
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

result = process_order(order_id)   # the slow function

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats("cumulative")
stats.print_stats(20)              # top 20 hotspots
```

Look for:

- **CPU-bound hot paths** — heavy JSON serialization, regex, crypto. Move to a background worker or cache the result.
- **Blocking synchronous I/O** inside an async framework (e.g., calling `requests.get()` inside a FastAPI async handler). Swap for `httpx` with `await`.
- **Unnecessary recomputation** — computing the same value on every request when it changes once a minute.

```python
# BAD — synchronous call in async path blocks the event loop
@app.get("/orders/{id}")
async def get_order(id: int):
    data = requests.get(f"http://inventory/items/{id}").json()  # BLOCKS
    return data

# GOOD
@app.get("/orders/{id}")
async def get_order(id: int):
    async with httpx.AsyncClient() as client:
        data = (await client.get(f"http://inventory/items/{id}")).json()
    return data
```

### Step 4 — Diagnose the Database

The database is the most common source of severe latency. Run `EXPLAIN ANALYZE` on every query the slow endpoint executes.

```sql
-- Find slow queries in PostgreSQL (last 24 h)
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 20;

-- Inspect the query plan
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT o.*, u.email
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE o.status = 'pending'
ORDER BY o.created_at DESC
LIMIT 50;
```

**Red flags in the plan output:**

| Plan node | What it means | Fix |
|---|---|---|
| `Seq Scan` on a large table | No usable index | Add a composite index on filter + sort columns |
| `Nested Loop` with large outer row count | N+1 in disguise | Rewrite as a single JOIN or batch with `IN (...)` |
| `Sort` + `Limit` without index | Filesort on every call | Create an index that matches `ORDER BY` clause |
| High `Buffers: shared hit` ratio low | Cache miss, cold data | `CLUSTER` the table or increase `shared_buffers` |

**Detecting N+1 in application code:**

```python
# BAD — N+1: 1 query for orders, then 1 per order for user
orders = db.query(Order).filter_by(status="pending").all()
for order in orders:
    print(order.user.email)  # lazy-loads user every iteration

# GOOD — 2 queries total (or 1 with JOIN)
orders = (
    db.query(Order)
    .filter_by(status="pending")
    .options(joinedload(Order.user))   # eager load
    .all()
)
```

### Step 5 — Audit External API Calls

Outbound HTTP calls are black boxes with unbounded latency. Apply three rules:

**Rule 1 — Make parallel calls when possible.**

```python
import asyncio, httpx

async def enrich_order(order_id: int):
    async with httpx.AsyncClient() as client:
        # Fire both calls at once, wait for both to finish
        inventory_task = client.get(f"http://inventory/items/{order_id}")
        shipping_task  = client.get(f"http://shipping/rates/{order_id}")
        inventory, shipping = await asyncio.gather(inventory_task, shipping_task)
    return {**inventory.json(), **shipping.json()}
```

**Rule 2 — Set aggressive timeouts and circuit-break failing dependencies.**

```python
# Never let one slow dependency hang your entire thread pool
async with httpx.AsyncClient(timeout=httpx.Timeout(connect=0.5, read=2.0)) as client:
    try:
        resp = await client.get("https://api.stripe.com/v1/charges/ch_xxx")
    except httpx.TimeoutException:
        return fallback_response()
```

**Rule 3 — Cache idempotent external responses.**

Exchange rates, product catalog lookups, and geocoding results rarely change second-to-second. Cache them at the application layer (Redis) with a short TTL.

### Step 6 — Check Infrastructure Limits

If the slowness is load-correlated (fast at 10 RPS, slow at 200 RPS), look at resource ceilings:

```bash
# Check connection pool exhaustion — PostgreSQL
SELECT count(*), state FROM pg_stat_activity GROUP BY state;

# Check open file descriptors on the app server
lsof -p $(pgrep -f gunicorn) | wc -l

# Check thread pool queue depth (Gunicorn)
# Too many workers: context switching. Too few: requests queue.
# Rule of thumb: workers = (2 * CPU cores) + 1
```

**Common infrastructure misconfigurations:**

```ini
# gunicorn.conf.py
workers = 5           # 2 * 2 cores + 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 30
keepalive = 5

# SQLAlchemy connection pool
pool_size = 10        # should match DB max_connections / num_app_instances
max_overflow = 5
pool_timeout = 10
pool_pre_ping = True  # detect stale connections
```

---

## Use It

| Scenario | Tool / Technique |
|---|---|
| Identify which endpoint is slow at scale | Datadog APM, New Relic, Grafana + Prometheus |
| Trace request across microservices | OpenTelemetry + Jaeger or Tempo |
| Find slow DB queries in production | `pg_stat_statements` (Postgres), `slow_query_log` (MySQL) |
| Detect N+1 queries in Django/Rails | `django-silk`, `bullet` gem |
| Load test to reproduce latency | `hey`, `k6`, `wrk` |
| Profile Python in production safely | `py-spy` (zero-overhead, attaches to running process) |
| Detect blocking calls in async Python | `asyncio` debug mode (`PYTHONASYNCIODEBUG=1`) |
| Circuit-break flaky external deps | Resilience4j (Java), `tenacity` (Python), Hystrix |

---

## Common Pitfalls

- **Optimizing the wrong layer.** Teams add Redis caching before checking whether the query itself is the problem. A cached bad query is still a bad query on a cache miss. Always profile first.

- **Measuring average latency instead of p99.** A 200 ms average hides a 4 s tail that affects 1 in 100 users — exactly the users most likely to complain. Always track percentile latency.

- **Ignoring connection pool exhaustion under load.** An endpoint that is fast for 10 concurrent users but slow for 100 is often waiting for a database connection, not executing a query. Adding a second server without fixing the pool does nothing.

- **Setting no timeouts on outbound calls.** A third-party API that starts returning in 60 s will hold your thread (or coroutine) open for 60 s, exhausting your worker pool even though your own code is instant.

- **Fixing N+1 with a cache instead of a proper JOIN.** Caching individual row lookups reduces database hits but adds per-request serialization overhead and cache-invalidation complexity. A single JOIN query that returns all needed data is almost always faster and simpler.

---

## Exercises

1. **Easy** — Take any endpoint in a project you have access to. Add a `curl -w` timing wrapper and record the DNS, TCP, TLS, TTFB, and total time. Identify which phase accounts for the majority of the time.

2. **Medium** — Given this Python SQLAlchemy code that fetches 100 blog posts and prints each author's name, rewrite it to eliminate the N+1 query. Verify by counting queries before and after using `echo=True` on the engine.

3. **Hard** — Set up a local FastAPI service that makes three sequential external HTTP calls (simulate them with `asyncio.sleep`). Measure the total response time. Now refactor the endpoint to make all three calls in parallel using `asyncio.gather`. Calculate the theoretical speedup and verify it against actual measurements. Then add a circuit-breaker pattern so that if any one call takes more than 500 ms, the endpoint returns a partial result rather than waiting.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **TTFB** (Time to First Byte) | "How fast the server responds" | Time from sending the request until the first byte of the response body arrives — includes DNS, TCP, TLS, and server processing |
| **p99 latency** | "The worst case" | The latency threshold below which 99% of requests complete — 1 in 100 requests is *slower* than this number |
| **N+1 query** | "A query that runs N+1 times" | A code pattern where 1 query fetches N parent rows, then N additional queries fetch related data — effectively hidden inside ORM lazy-loading |
| **Connection pool** | "A cache of connections" | A fixed set of pre-established database connections shared across threads/workers — exhausting it causes requests to queue waiting for a free connection |
| **Flame graph** | "A graph of function calls" | A stacked visualization where each box width is proportional to CPU time spent — the widest boxes at the top are the hottest code paths |
| **Circuit breaker** | "Something that stops all traffic" | A state machine that detects a failing dependency and short-circuits calls to it (returning a fallback) for a cooldown period, then probes for recovery |
| **Distributed trace** | "A log entry for a request" | A correlated chain of spans across services that reconstructs the full lifecycle of a single request, including time spent in each service and I/O call |

---

## Further Reading

- [Google SRE Book — Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/) — authoritative coverage of latency percentiles, alerting philosophy, and the four golden signals.
- [PostgreSQL Documentation — Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — official guide to reading query plans, including BUFFERS and ANALYZE output.
- [OpenTelemetry — Getting Started](https://opentelemetry.io/docs/getting-started/) — vendor-neutral instrumentation standard for traces, metrics, and logs across polyglot services.
- [High Performance Browser Networking — HTTP](https://hpbn.co/http2/) — Ilya Grigorik's deep dive into what happens at the network layer, including TLS handshake costs and HTTP/2 multiplexing.
- [Brendan Gregg — Flame Graphs](https://www.brendangregg.com/flamegraphs.html) — original author's guide to reading and generating flame graphs for any profiled workload.
