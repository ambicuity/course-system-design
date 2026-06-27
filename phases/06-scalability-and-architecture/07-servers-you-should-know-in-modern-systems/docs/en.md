# Servers You Should Know in Modern Systems

> Every server has one job — pick the right one and your architecture becomes obvious.

**Type:** Learn
**Prerequisites:** Load Balancing Fundamentals, Caching Strategies, Database Scaling
**Time:** ~35 minutes

---

## The Problem

A startup begins with a single machine running everything: the web framework, the database, the file uploads, the background jobs. It works until it doesn't. Traffic spikes, the database disk fills up, a slow query blocks HTTP requests, and the deployment causes 30-second outages. The team scrambles, adds more RAM, and calls it done.

The actual problem is architectural coupling. When every concern lives on one process or one host, scaling one thing forces you to scale everything. You cannot add read replicas without understanding database server semantics, cannot accelerate page loads without a caching server, cannot decouple slow jobs from request paths without a message broker. Engineers who do not know which server type does what end up bolt-on the wrong layer repeatedly — throwing compute at problems that need different infrastructure.

Modern production systems compose a handful of server categories, each owning a specific responsibility. The good news is there are fewer categories than you might think. Knowing the six to eight core types, their internal mechanics, and their failure modes gets you through the vast majority of real system design decisions.

---

## The Concept

### The Server Taxonomy

Modern distributed systems can be decomposed into these server categories:

| Category | Primary Responsibility | State? | Examples |
|---|---|---|---|
| **Web / Reverse Proxy** | Terminate TLS, route HTTP, serve static files | Stateless | nginx, Caddy, HAProxy |
| **Application** | Execute business logic | Stateless (preferred) | Gunicorn, uWSGI, Node.js, Tomcat |
| **Database** | Durable, queryable storage | Stateful | PostgreSQL, MySQL, MongoDB, Cassandra |
| **Cache** | Low-latency in-memory reads | Volatile stateful | Redis, Memcached |
| **Message Broker** | Durable async message delivery | Stateful | Kafka, RabbitMQ, SQS |
| **Search** | Full-text and ranked query | Stateful | Elasticsearch, OpenSearch |
| **Object / Blob Storage** | Unstructured file storage at scale | Stateful | S3, GCS, MinIO |
| **Service Discovery / Coordination** | Registry, leader election, distributed config | Stateful (consensus) | etcd, Consul, ZooKeeper |

### Mental Model: The Request Path

Trace an HTTP request through a typical e-commerce system:

```
Client
  │
  ▼
[CDN Edge]  ──────────── Static assets served here (HTML, CSS, JS, images)
  │
  ▼
[Load Balancer / Reverse Proxy]   nginx / HAProxy / AWS ALB
  │  TLS termination, health checks, connection pooling
  ▼
[Application Server]   Multiple instances, stateless
  │  Runs business logic, orchestrates downstream calls
  ├──► [Cache Server]   Redis — user session, product catalog, rate limit counters
  ├──► [Database Server]  PostgreSQL primary for writes, read replicas for reads
  ├──► [Search Server]  Elasticsearch — product search, full-text queries
  └──► [Message Broker]  Kafka — place order event → inventory, email, analytics workers
```

Each hop adds latency but also isolation: a crash in the search cluster should not take down checkout.

### Stateless vs Stateful Servers

This is the most important axis to understand.

**Stateless servers** (web, app) hold no customer data between requests. Scale them horizontally — add instances behind the load balancer. Replace them freely. They are cheap to operate and easy to reason about.

**Stateful servers** (databases, caches, brokers) hold data. You cannot blindly add or remove nodes without data movement, rebalancing, or replication lag. Scaling them requires understanding their specific consensus, sharding, or replication model.

The rule: **push statefulness as far right as possible** in your architecture. Keep request-handling servers stateless, let dedicated stateful services own their data.

### Web Server vs Application Server — The Distinction Most Engineers Blur

```
Request arrives
      │
      ▼
  [nginx]  ← Web / Reverse Proxy
  • Serves /static/* directly from disk (no Python, no JVM)
  • Terminates TLS
  • Forwards /api/* to upstream via proxy_pass
  • Connection-level load balancing
      │
      ▼
  [Gunicorn / uWSGI / Node.js]  ← Application Server
  • Forks worker processes / threads / event loop
  • Loads your Django / Flask / Express code
  • Connects to DB, Redis, etc.
  • Returns JSON or rendered HTML
```

nginx can serve 50,000+ static requests/second on cheap hardware because it never touches Python. Gunicorn workers block on I/O. Using nginx in front saves application workers for real computation.

---

## Build It / In Depth

### Walking Through a Real Architecture Decision

**Scenario**: You are building a job board. 100k daily active users. Posts expire after 30 days.

**Step 1 — The Application Server**

Start with a Python/FastAPI app running on Gunicorn with four Uvicorn workers per instance.

```bash
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

Four workers × 2 vCPUs handles roughly 200-400 concurrent requests. Fine for day one.

**Step 2 — The Database Server**

PostgreSQL for job listings and applications. You need ACID for writes.

```sql
-- PostgreSQL handles this transactionally
BEGIN;
  INSERT INTO jobs (title, company_id, expires_at)
  VALUES ($1, $2, NOW() + INTERVAL '30 days')
  RETURNING id;
  INSERT INTO audit_log (table_name, action, row_id)
  VALUES ('jobs', 'INSERT', lastval());
COMMIT;
```

Add a **read replica** the moment read traffic exceeds 60% of total DB load. Route SELECT queries to the replica, writes to the primary.

**Step 3 — The Cache Server**

Redis dramatically reduces database load for hot read paths.

```python
import redis

r = redis.Redis(host='cache.internal', port=6379, decode_responses=True)

def get_job(job_id: int):
    cache_key = f"job:{job_id}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)          # Cache hit — DB not touched
    
    job = db.query("SELECT * FROM jobs WHERE id = %s", [job_id])
    r.setex(cache_key, 3600, json.dumps(job))  # TTL: 1 hour
    return job
```

Use Redis also for rate limiting (token bucket with INCR + EXPIRE) and session storage.

**Step 4 — The Reverse Proxy**

Put nginx in front of all Gunicorn instances.

```nginx
upstream app_servers {
    least_conn;
    server app1.internal:8000;
    server app2.internal:8000;
    server app3.internal:8000;
    keepalive 64;
}

server {
    listen 443 ssl;
    ssl_certificate /etc/nginx/certs/cert.pem;
    ssl_certificate_key /etc/nginx/certs/key.pem;

    location /static/ {
        root /var/www;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /api/ {
        proxy_pass http://app_servers;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }
}
```

**Step 5 — The Message Broker**

When an employer posts a job, you need to: send a confirmation email, index it in search, and notify subscribed users. Doing all this synchronously in the HTTP handler makes the endpoint slow and fragile.

```
POST /jobs  →  App Server
                    │
                    ├── INSERT into PostgreSQL  (synchronous — required)
                    │
                    └── Publish to Kafka topic: job.created
                            │
                            ├── Consumer A: email service  (async)
                            ├── Consumer B: search indexer (async)
                            └── Consumer C: notification fanout (async)
```

The HTTP response returns in ~20ms (just the DB write). Consumers catch up in the background.

**Step 6 — The Search Server**

Full-text search over job titles and descriptions with ranking is hard to do in PostgreSQL at scale. Elasticsearch handles it natively.

```bash
# Index a document
curl -X POST http://search.internal:9200/jobs/_doc/42 \
  -H 'Content-Type: application/json' \
  -d '{"title": "Senior Golang Engineer", "description": "...", "location": "Remote"}'

# Query with relevance ranking
curl http://search.internal:9200/jobs/_search \
  -d '{"query": {"multi_match": {"query": "golang remote", "fields": ["title^2", "description"]}}}'
```

---

## Use It

### Choosing the Right Server for Each Problem

| Problem | Reach For | Avoid |
|---|---|---|
| Serve a React SPA globally | CDN (Cloudflare, CloudFront) | Application server for static files |
| Authentication / session state | Redis (fast, TTL built-in) | PostgreSQL for hot session reads |
| Durable financial records | PostgreSQL / MySQL (ACID) | Redis (volatile by default) |
| High-write time-series events | Cassandra, InfluxDB | Single PostgreSQL primary |
| Full-text product search | Elasticsearch / OpenSearch | LIKE queries in SQL at scale |
| Fan-out notifications | Kafka, RabbitMQ | Synchronous HTTP calls in handler |
| User-uploaded photos / videos | S3 / GCS / MinIO | Database BLOBs or local disk |
| Service addresses in Kubernetes | etcd (built into k8s) / Consul | Hardcoded IPs in config |

### Managed vs Self-Hosted

| Server Type | Self-Hosted | Managed |
|---|---|---|
| Database | PostgreSQL on EC2 | AWS RDS, PlanetScale, Neon |
| Cache | Redis on VM | AWS ElastiCache, Upstash |
| Broker | Kafka on bare metal | Confluent Cloud, AWS MSK |
| Search | Elasticsearch cluster | AWS OpenSearch, Elastic Cloud |
| Object Storage | MinIO | AWS S3, GCS |

**Rule of thumb**: Prefer managed unless you have deep operational expertise and the cost delta justifies it. At $1M ARR, paying for RDS vs running your own Postgres is almost always worth it.

---

## Common Pitfalls

- **Storing sessions in application memory.** If you run multiple app server instances, a request routed to a different instance loses the session. Always store sessions in Redis or a database, never in-process.

- **Using the database as a message queue.** Polling a `jobs` table every second for pending tasks burns DB IOPS, misses fan-out patterns, and creates lock contention. Use a real broker (Redis Streams for lightweight, Kafka for high throughput).

- **Forgetting cache invalidation on writes.** A cache hit that returns stale data after an update causes subtle bugs. Either use write-through caching (update cache and DB together) or set short TTLs with aggressive expiry on the write path.

- **Over-indexing on Elasticsearch for simple filters.** ES has operational overhead: index management, shard sizing, JVM heap tuning. For basic keyword search on small datasets, PostgreSQL's `tsvector` full-text search is sufficient and avoids the extra service.

- **Treating every stateful server as equivalent to a database.** Redis with default config loses data on crash. Kafka retains data for a configurable period then deletes it. S3 stores data forever (until you delete it). Know the durability guarantees of each server before committing to it as a source of truth.

---

## Exercises

1. **Easy** — Draw the request path for a read-heavy news website (think: /articles/123). Label which server type handles each hop, starting from the client DNS lookup to the final JSON response. Identify where a cache server would have the highest impact.

2. **Medium** — A social app allows users to "like" posts. Currently, every like increments a counter in PostgreSQL directly. At 10k likes/second, the single row becomes a hotspot. Redesign the write path using a cache server and a message broker to handle this load without rewriting the read path.

3. **Hard** — You are given a system where a search server (Elasticsearch) is fed by a CDC (Change Data Capture) pipeline from PostgreSQL via Kafka. A deployment bug causes 2 hours of Kafka consumer lag — Elasticsearch falls behind. Design a recovery procedure. What do you do about requests that hit Elasticsearch during the lag window and got stale results? How do you detect the lag automatically?

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Web Server** | Any server on the web | A server that speaks HTTP at the edge — typically serves static files and reverse-proxies to app servers (nginx, Caddy) |
| **Application Server** | Where your app runs | A process manager and runtime that loads your code and handles concurrent requests (Gunicorn, uWSGI, Tomcat) |
| **Cache Server** | A speed-up layer | An in-memory key-value store with optional persistence and TTL; primary purpose is reducing read latency and DB load (Redis, Memcached) |
| **Message Broker** | A fancy queue | A server that decouples producers from consumers with durable, ordered, at-least-once (or exactly-once) message delivery (Kafka, RabbitMQ) |
| **Reverse Proxy** | Same as a load balancer | A server that sits in front of backends and forwards requests; load balancing is one feature, not the whole identity |
| **Search Server** | A database with LIKE | An inverted-index engine that scores and ranks documents by relevance; fundamentally different storage model from relational DBs |
| **Object Storage** | A file system in the cloud | A flat key-value store for blobs with HTTP access, eventual consistency, and massive scale; no directory hierarchy (S3, GCS) |

---

## Further Reading

- [nginx Documentation — Reverse Proxy Guide](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) — canonical reference for proxy_pass, upstream blocks, and connection tuning.
- [Redis Architecture and Persistence](https://redis.io/docs/management/persistence/) — explains RDB snapshots, AOF logging, and when Redis loses data.
- [Kafka Design Documentation](https://kafka.apache.org/documentation/#design) — covers log-structured storage, consumer groups, and delivery guarantees from the Apache maintainers.
- [Designing Data-Intensive Applications — Martin Kleppmann (O'Reilly)](https://dataintensive.net/) — Chapter 1 (Reliability, Scalability, Maintainability) and Chapter 11 (Stream Processing) are directly relevant to this lesson.
- [The Architecture of Open Source Applications: nginx](https://aosabook.org/en/v2/nginx.html) — deep dive into how nginx's event-driven model achieves high concurrency with low memory.
