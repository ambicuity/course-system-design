# Top 5 common ways to improve API performance

> Fast APIs aren't luck — they're the result of applying five well-understood techniques at the right layer.

**Type:** Learn
**Prerequisites:** REST API design basics, HTTP fundamentals, Database indexing
**Time:** ~25 minutes

---

## The Problem

You shipped an API that works fine in staging with synthetic data. Two months after launch, p99 latency has ballooned to 4 seconds, the database is CPU-bound, and your on-call engineers are seeing connection exhaustion alerts at 3 AM. The feature code is fine — the problem is that you never addressed the five structural performance drains that every API hits under real load.

Consider a product catalogue endpoint that returns 50,000 items to every caller, writes a structured log line to disk on every request, queries the database without reuse, sends full JSON payloads uncompressed, and opens a fresh database connection for each request. Each of these is independently manageable, but together they multiply latency and resource consumption in ways that don't show up until traffic is real.

These five techniques — **result pagination**, **asynchronous logging**, **data caching**, **payload compression**, and **connection pooling** — are not micro-optimizations. They are the difference between an API that survives production and one that collapses under its own weight. Each addresses a different resource: network bandwidth, disk I/O, memory hit rate, CPU, and TCP connection overhead.

---

## The Concept

The five techniques map to five distinct bottlenecks:

```
CLIENT
  │
  │ ①  Too much data per response  →  Pagination
  │ ④  Large uncompressed payload  →  Compression
  ▼
 API SERVER
  │
  │ ②  Synchronous log writes      →  Async Logging
  │ ③  Repeated expensive reads    →  Caching
  ▼
DATABASE / STORAGE
  │
  │ ⑤  New conn per request        →  Connection Pooling
  ▼
 DATABASE
```

### ① Result Pagination

Fetching unbounded result sets is the most common source of "fast in dev, slow in prod" failures. A table with 1 000 rows in staging has 10 million rows in production.

Pagination forces the caller to consume data in slices. Two dominant strategies:

| Strategy | Mechanism | Pros | Cons |
|---|---|---|---|
| Offset / Limit | `LIMIT 20 OFFSET 100` | Simple, random-access | Slow at high offsets, page drift on writes |
| Cursor / Keyset | `WHERE id > last_seen_id LIMIT 20` | O(log n) at any depth, stable under writes | No random page jump |

For most APIs with large data sets, **cursor pagination is the correct default**. Offset pagination is fine when result sets are small or random access is genuinely needed.

### ② Asynchronous Logging

Writing a structured log line to disk is a synchronous I/O operation — it blocks the request goroutine/thread until the kernel flushes the write. Under 5 000 req/s, this single operation can saturate disk throughput.

The fix is a **lock-free ring buffer** in front of the disk writer:

```
Request thread          Logging thread
     │                       │
write to ring buffer ──→  reads batch
     │ (returns immediately)  │
     ▼                    flush to disk
  continue                    │
                          (async, periodic)
```

The tradeoff: if the process crashes, log lines in the buffer are lost. For audit logs (financial, security), use synchronous writes or a durable message queue (Kafka) rather than a bare ring buffer.

### ③ Data Caching

The principle: **compute expensive things once, serve from memory thereafter.**

Cache placement options (inner to outer):

```
Client  →  CDN / Edge Cache  →  API Server (in-process)  →  Distributed Cache (Redis)  →  DB
```

Each layer saves a round-trip. In-process caches (e.g., Caffeine in Java, `functools.lru_cache` in Python) are zero-latency but not shared across instances. Redis adds a network hop (~0.5 ms) but is shared and survives instance restarts.

Cache invalidation is the hard part. Three strategies:

| Strategy | How | When to use |
|---|---|---|
| TTL | Expire after fixed duration | Tolerates eventual consistency |
| Write-through | Invalidate on write | Strong consistency, write-heavy APIs |
| Event-driven | Invalidate on domain event | Complex data relationships |

### ④ Payload Compression

HTTP/1.1 and HTTP/2 both support content negotiation for compression. The client sends `Accept-Encoding: gzip, br` and the server compresses the response body.

Typical compression ratios on JSON:

| Algorithm | Compression ratio | CPU cost | Best for |
|---|---|---|---|
| gzip (level 6) | ~70-80% smaller | Low | General API responses |
| Brotli (level 6) | ~75-85% smaller | Medium | Static assets, CDN |
| zstd | ~75-80% smaller | Very low | Internal microservice calls |

Compression trades **CPU for bandwidth**. At high request rates, compression at the API tier can become a CPU bottleneck — offload it to a reverse proxy (nginx, Envoy) or CDN edge node instead of doing it in application code.

Do not compress already-compressed content (JPEG, PNG, encrypted payloads). The overhead exceeds the benefit.

### ⑤ Connection Pooling

Opening a TCP connection to a database involves a three-way handshake, TLS negotiation, and protocol authentication — typically 10–50 ms of overhead. At 1 000 req/s, creating a new connection per request means 1 000 connection setups per second and rapid exhaustion of the database's `max_connections` limit.

A connection pool solves this by maintaining a set of **pre-warmed, authenticated connections** that requests borrow and return:

```
Request A ──┐
Request B ──┤──→  Pool [conn1, conn2, conn3, conn4, conn5]  ──→  DB
Request C ──┘         ↑               ↑
                  "borrow"        "return"
```

Key pool settings to tune:

| Parameter | What it controls | Rule of thumb |
|---|---|---|
| `min_pool_size` | Connections kept alive when idle | 5–10 |
| `max_pool_size` | Hard ceiling on open connections | db_max_conn / num_instances |
| `connection_timeout` | How long to wait for a free conn | 2–5 s |
| `idle_timeout` | When to close unused connections | 5–10 min |

---

## Build It / In Depth

### Cursor pagination — Python / FastAPI

```python
from fastapi import FastAPI, Query
from typing import Optional

app = FastAPI()

@app.get("/products")
def list_products(
    cursor: Optional[int] = None,
    limit: int = Query(default=20, le=100),
    db=Depends(get_db),
):
    query = db.query(Product).order_by(Product.id)
    if cursor:
        query = query.filter(Product.id > cursor)
    items = query.limit(limit + 1).all()

    has_more = len(items) > limit
    items = items[:limit]

    return {
        "data": items,
        "next_cursor": items[-1].id if has_more else None,
    }
```

Fetching `limit + 1` rows is the standard "has next page" trick — no COUNT query needed.

### Async logging — Go ring buffer pattern

```go
var logCh = make(chan []byte, 65536) // lock-free channel as ring buffer

func init() {
    go func() {
        buf := bufio.NewWriterSize(os.Stderr, 256*1024)
        ticker := time.NewTicker(100 * time.Millisecond)
        for {
            select {
            case line := <-logCh:
                buf.Write(line)
            case <-ticker.C:
                buf.Flush()
            }
        }
    }()
}

func log(msg string) {
    select {
    case logCh <- []byte(msg + "\n"):
    default: // drop on buffer full; never block the request
    }
}
```

The request thread never touches disk. The background goroutine flushes every 100 ms.

### Redis caching — cache-aside pattern

```python
import redis, json, hashlib

r = redis.Redis(host="localhost", decode_responses=True)

def get_product(product_id: int):
    key = f"product:{product_id}"
    cached = r.get(key)
    if cached:
        return json.loads(cached)            # cache hit

    product = db.query(Product).get(product_id)  # cache miss
    r.setex(key, 300, json.dumps(product.dict()))  # TTL = 5 min
    return product
```

### nginx gzip compression — offload from app tier

```nginx
# nginx.conf
gzip on;
gzip_types application/json text/plain text/xml;
gzip_min_length 1024;         # don't compress tiny responses
gzip_comp_level 6;            # balance between CPU and ratio
gzip_vary on;                 # tell proxies the response varies by encoding
```

No application code change required. nginx handles `Accept-Encoding` negotiation automatically.

### PostgreSQL connection pooling — PgBouncer

```ini
# pgbouncer.ini
[databases]
mydb = host=127.0.0.1 port=5432 dbname=mydb

[pgbouncer]
pool_mode = transaction        # best for stateless API workloads
max_client_conn = 1000
default_pool_size = 20         # 20 real DB connections serve 1000 clients
server_idle_timeout = 600
```

With `transaction` pool mode, a real database connection is only held for the duration of a single transaction, not the entire client session. This multiplies effective capacity dramatically.

---

## Use It

| Technique | OSS Tools | Cloud / Managed |
|---|---|---|
| Pagination | FastAPI, Spring Data (pageable), DRF PageNumberPagination | API Gateway response streaming |
| Async logging | Zap (Go), Logback async appender (Java), structlog (Python) | CloudWatch, Datadog log agents (buffer locally) |
| Caching | Redis, Memcached, Caffeine (JVM), Guava Cache | ElastiCache, Azure Cache for Redis, Upstash |
| Compression | nginx, Envoy, Caddy (all handle gzip/Brotli transparently) | CloudFront, Fastly, Cloudflare (edge compression) |
| Connection pooling | PgBouncer (Postgres), ProxySQL (MySQL), HikariCP (JVM), psycopg3 pool | RDS Proxy, Azure SQL connection pooling |

**Recommended layering for a typical REST API stack:**

1. CDN edge (Cloudflare / CloudFront) handles compression for cacheable responses.
2. nginx/Envoy handles compression for dynamic responses and terminates TLS.
3. Application tier uses an in-process cache for hot reference data (< 1 ms access) and Redis for shared state.
4. PgBouncer or RDS Proxy sits between app tier and database for connection pooling.
5. All logging goes through a buffered async appender; logs are shipped to a central collector.

---

## Common Pitfalls

- **Offset pagination at scale.** `LIMIT 100 OFFSET 100000` causes a full-scan of 100 100 rows. Switch to keyset/cursor pagination before the table grows large, not after.

- **Caching mutable data without invalidation.** Setting a long TTL on user-specific or write-heavy data causes stale reads. Design invalidation strategy at the same time as caching strategy — they are inseparable.

- **Compressing at the application layer under high load.** Doing `gzip` compression in Python/Node at 5 000 req/s will peg a CPU core. Push compression to nginx, Envoy, or a CDN — they use native C implementations and can share work across cores.

- **Pool size set to database `max_connections`.** If you have 10 application instances each with a pool of 100, you've asked for 1 000 connections and the database limit is 100. Always compute `max_pool_size = floor(db_max_connections / num_app_instances) - headroom`.

- **Async logging with no backpressure handling.** A ring buffer that silently drops on overflow is acceptable for debug logs. Dropping security audit or financial transaction logs is a compliance and debugging disaster. Use a durable sink (Kafka, file with fsync) for critical log categories.

---

## Exercises

1. **Easy — Pagination audit.** Take any public API you use (GitHub, Stripe, Twitter) and inspect its pagination mechanism. Is it offset-based or cursor-based? What happens when you request page 500? Document the trade-offs you observe.

2. **Medium — Redis cache layer.** Add a Redis cache-aside layer to an existing GET endpoint that queries a database. Implement a `Cache-Control: max-age` header in the response that reflects the TTL set in Redis. Measure latency before and after with `wrk` or `k6`.

3. **Hard — End-to-end pipeline.** Design and implement a high-throughput logging pipeline for an API handling 10 000 req/s. Requirements: (a) request thread must not block on log write, (b) logs must survive a graceful shutdown, (c) logs must be searchable within 5 seconds of generation. Sketch the architecture and implement the buffer-to-sink handoff.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Pagination | Just splitting a list into pages | A contract that constrains result set size per call; cursor pagination is structurally different from offset pagination and far more scalable |
| Cache hit ratio | A vanity metric | The fraction of requests served from cache without touching the DB; going from 90% to 99% hit ratio reduces DB load by 90%, not 9% |
| Connection pool | A convenience feature | A hard requirement at scale; without it, connection setup overhead and `max_connections` exhaustion will crash your database |
| gzip compression level | Higher = always better | A CPU-bandwidth trade-off; level 6 is the standard sweet spot; level 9 uses 3× more CPU for ~2% extra compression |
| Async logging | Fire-and-forget | A ring buffer with a background flusher; "async" does not mean "reliable" — dropped-on-overflow is the default failure mode |
| TTL (Time To Live) | Cache expiry | The maximum staleness window you accept for a given data class; choosing TTL requires understanding acceptable consistency lag, not just performance |
| PgBouncer transaction mode | Connection pooler | A session multiplexer that routes different client sessions over the same underlying DB connections, but only during active transactions |

---

## Further Reading

- [PostgreSQL Connection Pooling with PgBouncer](https://www.pgbouncer.org/config.html) — official PgBouncer configuration reference covering pool modes, sizing, and tuning parameters.
- [Redis Caching Patterns](https://redis.io/docs/manual/patterns/) — Redis documentation covering cache-aside, write-through, and pub/sub invalidation patterns with worked examples.
- [HTTP Compression — MDN Web Docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Compression) — covers content negotiation, `Accept-Encoding`, `Content-Encoding`, and per-algorithm trade-offs.
- [High Performance Browser Networking — Chapter 1: Latency and Bandwidth](https://hpbn.co/) — Ilya Grigorik's free book; the foundational mental model for why bytes-on-the-wire optimizations (compression, pagination) matter at the network layer.
- [Use the index, Luke — Pagination](https://use-the-index-luke.com/no-offset) — detailed explanation of why `OFFSET` is O(n) at the database level and how keyset pagination avoids it, with SQL examples for Postgres, MySQL, and Oracle.
