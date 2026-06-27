# 10 Essential Components of a Production Web Application

> A web app is not a single process — it is an orchestra of specialized systems, each responsible for exactly one concern.

**Type:** Learn
**Prerequisites:** Load Balancing Fundamentals, Database Scaling Patterns, Introduction to Distributed Systems
**Time:** ~35 minutes

---

## The Problem

Developers who have built apps on a laptop hit a wall when they move to production for the first time. A single server handles traffic fine at 100 requests per second. At 10,000 RPS it collapses — not because the code is wrong, but because the architecture assumes the wrong model: one process doing everything. When the server restarts for a deploy, every user gets a 502. When a slow database query blocks the thread pool, all other requests queue up and time out. When a background email job runs inline with the HTTP handler, checkout latency spikes to 8 seconds.

The root cause is conflating *concerns*. A production web application separates every concern into a dedicated subsystem: request routing, computation, data storage, background work, search, observability, and delivery. Each subsystem can scale, fail, and be replaced independently. When one component is slow, it does not drag the others down.

This lesson maps the ten canonical components every production web application needs — what each one does, how it interacts with the others, and where teams get the trade-offs wrong.

---

## The Concept

The ten components fall into five functional layers. Understanding which layer a component belongs to clarifies both its responsibility and its failure mode.

```
┌─────────────────────────────────────────────────────────────────┐
│                        DELIVERY LAYER                           │
│              DNS → CDN → Load Balancer / Reverse Proxy         │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                     COMPUTE LAYER                               │
│                   Web Application Servers                       │
│                  (API / business logic)                         │
└────────┬────────────────────────┬───────────────────────────────┘
         │                        │
┌────────▼────────┐   ┌───────────▼──────────────────────────────┐
│   DATA LAYER    │   │            ASYNC LAYER                    │
│  Database +     │   │  Job Queue → Job Workers                  │
│  Cache          │   │  Full-text Search                         │
└─────────────────┘   └──────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                   OBSERVABILITY LAYER                           │
│                Monitoring + Alerting                            │
└─────────────────────────────────────────────────────────────────┘
                             ▲
┌────────────────────────────┴────────────────────────────────────┐
│                    DELIVERY PIPELINE                            │
│                    CI/CD (feeds all layers)                     │
└─────────────────────────────────────────────────────────────────┘
```

### Component-by-Component Breakdown

#### 1. CI/CD Pipeline

The pipeline is the only way code reaches any server. It enforces a gate: code that does not pass automated tests, linting, or security scans never gets deployed. A broken manual deploy process is the fastest way to accumulate downtime debt.

Key stages: **source commit → build → test → artifact → deploy → smoke test → rollback on failure.**

Tools: GitHub Actions, GitLab CI, Jenkins, CircleCI, ArgoCD (for GitOps).

#### 2. DNS Resolution

Before a single byte reaches your servers, the browser resolves the domain name to an IP address via DNS. DNS TTL controls how long clients cache the old IP — a misconfigured short TTL causes millions of resolver queries per second; a too-long TTL means a failover takes hours to propagate.

DNS is also the integration point for health-check-based failover (Route 53 health checks, Cloudflare DNS failover).

#### 3. CDN (Content Delivery Network)

A CDN caches responses at edge nodes geographically close to the user. It handles two distinct workloads:

| Workload | What is cached | Benefit |
|---|---|---|
| Static assets | JS, CSS, images, fonts | Reduced origin load, fast first paint |
| Dynamic / API responses | JSON with short TTLs | Absorbs traffic spikes, DDoS mitigation |

The CDN short-circuits the request before it ever reaches your load balancer. For a global app, a CDN can cut median latency by 60–80 ms on static assets.

#### 4. Load Balancer / Reverse Proxy

The load balancer distributes requests across a pool of identical application server instances. It also performs TLS termination, health checking, and connection draining during deploys. The reverse proxy hides the internal topology: clients always talk to one address.

| Algorithm | When to use |
|---|---|
| Round-robin | Homogeneous requests, stateless servers |
| Least connections | Long-lived connections (WebSockets) |
| IP hash | Session affinity required (legacy apps) |
| Weighted round-robin | Canary deploys, heterogeneous hardware |

Tools: Nginx, HAProxy, AWS ALB/NLB, Envoy, Traefik.

#### 5. Web Application Servers

This is where business logic runs. Application servers are stateless: they read from databases and caches, call downstream services, and return responses. Stateless servers are interchangeable — any server can handle any request — which is what makes horizontal scaling possible.

The application layer exposes APIs (REST, GraphQL, gRPC) consumed by browser clients and by internal services.

#### 6. Database + Distributed Cache

The database is the source of truth. The cache sits in front of it and absorbs repeated reads. The two serve different access patterns:

| Layer | Latency | Durability | Eviction |
|---|---|---|---|
| Relational DB (Postgres, MySQL) | 1–10 ms | Durable (WAL, fsync) | None |
| In-memory cache (Redis, Memcached) | < 1 ms | Volatile (configurable) | LRU / TTL-based |

The most common cache pattern is **cache-aside**: the app checks the cache first; on a miss, it reads from the DB and populates the cache. Never write application data only to the cache — it is not your source of truth.

#### 7. Job Queue + Job Workers

Any operation that is slow, retryable, or side-effectful belongs in a job queue rather than in the HTTP request path. Email delivery, PDF generation, video transcoding, payment processing, and notification fanout are canonical examples.

```
HTTP Request → Enqueue job → Return 202 Accepted
                   ↓
            Job Queue (Redis, SQS, RabbitMQ)
                   ↓
            Job Worker (polls or subscribes)
                   ↓
            Executes task (retries on failure)
```

Decoupling work from the request path means your API stays fast even when a downstream service is slow. Workers can scale independently of web servers.

#### 8. Full-Text Search Service

Relational databases use B-tree indexes optimized for exact and range queries. Full-text search — tokenization, stemming, ranking by relevance, fuzzy matching — requires an inverted index. Adding `LIKE '%query%'` to a SQL query performs a full table scan and destroys performance at scale.

Elasticsearch and Apache Solr maintain a separate, purpose-built index synchronized from the primary database (via change-data-capture or event streaming). This is an intentional denormalization: you trade extra storage and sync complexity for sub-10-ms search over hundreds of millions of documents.

#### 9. Monitoring

Monitoring answers: *is the system healthy right now, and was it healthy in the past?*

Three signals cover most production systems:

- **Metrics** — numeric time-series (request rate, error rate, latency percentiles, CPU). Tools: Prometheus, Datadog, CloudWatch.
- **Logs** — structured event records from every component. Tools: Loki, Elasticsearch, CloudWatch Logs.
- **Traces** — end-to-end request flow across services. Tools: Jaeger, Zipkin, Honeycomb, AWS X-Ray.

Grafana is a dashboarding layer that unifies all three signal types into a single pane of glass. Sentry is specialized for error tracking and stack-trace aggregation.

#### 10. Alerting

Monitoring without alerting is a dashboard nobody watches. Alerting closes the loop: when a metric crosses a threshold (error rate > 1%, p99 latency > 2 s, queue depth > 10 000), an alert fires and reaches an engineer through PagerDuty, Opsgenie, or Slack.

Good alerts are actionable and rare. Alert on symptoms (users are affected), not causes (CPU is high). Too many alerts cause alert fatigue and on-call engineers start ignoring them.

---

## Build It / In Depth

### Walking a Request End-to-End

Consider a user searching for a product on an e-commerce site. Here is every hop the request makes:

```
1. Browser issues DNS query for shop.example.com
   → Resolver returns CDN edge IP (e.g. 104.21.x.x)

2. Browser connects to CDN edge (TLS termination at edge)
   → CDN checks: is /api/search?q=shoes in cache? No (dynamic query).
   → CDN forwards to origin load balancer.

3. Load balancer receives request
   → Health check: app-server-1 healthy, app-server-2 healthy, app-server-3 draining.
   → Routes to app-server-1 (round-robin).

4. app-server-1 processes request
   → Authenticates JWT (no DB hit — stateless).
   → Calls Search Service: GET /search?q=shoes

5. Search Service (Elasticsearch)
   → Returns top 20 results with relevance scores in ~8 ms.

6. app-server-1 assembles response
   → Checks Redis for cached inventory counts (hit).
   → Returns JSON to load balancer → CDN → browser.

7. User clicks "Buy"
   → POST /orders hits app-server-2 (next round-robin).
   → App writes order to Postgres (source of truth).
   → Enqueues "send_confirmation_email" job to Redis queue.
   → Returns 201 Created immediately.

8. Job worker (separate process)
   → Picks up email job, sends via SendGrid.
   → Marks job complete.

9. Prometheus scrapes /metrics on all servers every 15 s.
   → Grafana dashboard shows order rate spike.
   → No alerts fire — all within thresholds.
```

### CI/CD Pipeline: Minimal GitHub Actions Config

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: pytest --cov=app tests/

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t app:${{ github.sha }} .
      - name: Push to registry
        run: docker push registry.example.com/app:${{ github.sha }}
      - name: Rolling deploy
        run: |
          kubectl set image deployment/app \
            app=registry.example.com/app:${{ github.sha }}
          kubectl rollout status deployment/app
```

### Cache-Aside Pattern

```python
def get_product(product_id: str) -> dict:
    cache_key = f"product:{product_id}"

    # 1. Check cache
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # 2. Cache miss — read from DB
    product = db.query("SELECT * FROM products WHERE id = %s", product_id)
    if product is None:
        raise NotFoundError(product_id)

    # 3. Populate cache with 5-minute TTL
    redis.setex(cache_key, 300, json.dumps(product))
    return product
```

### Prometheus Alert Rule

```yaml
# alerts.yml
groups:
  - name: api
    rules:
      - alert: HighErrorRate
        expr: |
          rate(http_requests_total{status=~"5.."}[5m])
          / rate(http_requests_total[5m]) > 0.01
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "Error rate above 1% for 2 minutes"
          runbook: "https://wiki.internal/runbooks/high-error-rate"
```

---

## Use It

### Choosing the Right Tool Per Layer

| Layer | Open-Source | Managed / Cloud |
|---|---|---|
| CI/CD | GitHub Actions, GitLab CI, Jenkins | AWS CodePipeline, CircleCI |
| CDN | Varnish | Cloudflare, AWS CloudFront, Fastly |
| Load Balancer | Nginx, HAProxy, Envoy | AWS ALB, GCP Cloud Load Balancing |
| Database | PostgreSQL, MySQL | AWS RDS, PlanetScale, Neon |
| Cache | Redis, Memcached | AWS ElastiCache, Upstash |
| Job Queue | Celery + Redis, Sidekiq | AWS SQS + Lambda, Temporal |
| Search | Elasticsearch, OpenSearch, Solr | Elastic Cloud, AWS OpenSearch |
| Metrics | Prometheus + Grafana | Datadog, Grafana Cloud, New Relic |
| Logs | Loki, ELK stack | Datadog Logs, Papertrail |
| Alerting | Alertmanager | PagerDuty, Opsgenie, Better Uptime |

**When to go managed vs. self-hosted:** Managed services eliminate operational burden (patching, backup, HA) at the cost of reduced control and higher dollar cost. Self-host when you have strict data-residency requirements, extreme cost sensitivity at scale, or need fine-grained tuning that hosted services do not expose.

---

## Common Pitfalls

- **Putting slow work in the HTTP path.** Sending email, generating reports, or calling flaky third-party APIs synchronously in an HTTP handler couples your API latency to the slowest downstream call. Move anything that can tolerate eventual execution to a job queue. The API returns 202, the worker does the work.

- **Caching the wrong things (or not caching at all).** Teams either skip the cache entirely (overloading the DB) or cache mutable data with no invalidation strategy (users see stale prices, stale inventory). Design cache invalidation before you cache — not as an afterthought.

- **Missing connection pool limits.** Every application server opens N database connections. With 10 app servers and a pool size of 20, you need a DB that can handle 200 connections. Postgres max_connections defaults to 100. Use PgBouncer or RDS Proxy to multiplex connections. Ignoring this causes cascading failures during traffic spikes.

- **Treating the job queue as fire-and-forget.** Workers fail. Networks drop. Third-party APIs return 503. Every job needs idempotency (re-running the job produces the same result) and a dead-letter queue for jobs that exhaust retries. Without this, failed jobs silently disappear and users never get their emails.

- **Alert fatigue from noisy, non-actionable alerts.** Teams alert on every metric they collect. Hundreds of alerts fire per week. On-call engineers mute their phones. The real outage goes unnoticed. Keep your alert set small: alert on SLO breach indicators only (error budget burn rate, latency SLO) and write runbooks for every alert that fires.

---

## Exercises

1. **Easy — Component identification.** Draw the ten-component architecture for a ride-sharing app (like Uber). Label each component and describe one concrete example of the data or request it handles (e.g., "Job Queue: dispatch driver-matching computation").

2. **Medium — Failure mode analysis.** For each of the ten components, answer: *What happens to the user experience if this component goes down?* Which components are single points of failure? What redundancy strategy eliminates each one?

3. **Hard — Capacity planning.** A new e-commerce site expects 50 000 daily active users, 1 000 peak concurrent users, and 10 000 product listings. Design the component sizing: how many app server instances, what size Redis cache, what Postgres instance class, what CDN cache-hit ratio target? Justify each number with back-of-envelope math, and identify which component becomes the bottleneck first as traffic grows 10×.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Load balancer | Splits traffic evenly across servers | Distributes requests based on a configurable algorithm; also performs health checking, TLS termination, and connection draining |
| CDN | Only caches static files (images, JS) | Can also cache dynamic API responses with short TTLs; provides DDoS mitigation and TLS offload at the edge |
| Cache | A magic layer that makes everything fast | A read-optimized store with no durability guarantees; only as useful as your invalidation strategy |
| Job queue | A background task scheduler | A durable message buffer that decouples producers (web servers) from consumers (workers), enabling retries, back-pressure, and independent scaling |
| Monitoring | Watching a dashboard for problems | Collecting metrics, logs, and traces so you can answer "what happened?" both in real time and retrospectively |
| Reverse proxy | The same thing as a load balancer | A proxy that sits in front of one or more servers; a load balancer is a type of reverse proxy, but reverse proxies also handle SSL termination, caching, compression, and request routing without distributing load |
| Full-text search index | A faster version of SQL LIKE | An inverted index optimized for relevance ranking, tokenization, and fuzzy matching — a fundamentally different data structure from a B-tree |

---

## Further Reading

- **Martin Kleppmann — *Designing Data-Intensive Applications*, Chapter 11 (Stream Processing):** Covers the data pipeline patterns that connect most of these components. O'Reilly, 2017. https://dataintensive.net/
- **AWS Well-Architected Framework — Reliability Pillar:** https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html — The canonical checklist for production-grade resilience across exactly these component boundaries.
- **Prometheus documentation — Alerting best practices:** https://prometheus.io/docs/practices/alerting/ — Rob Ewaschuk's rules for writing alerts that are useful rather than noisy.
- **Cloudflare Learning Center — How CDNs work:** https://www.cloudflare.com/learning/cdn/what-is-a-cdn/ — Accurate, vendor-neutral explanation of edge caching and CDN architecture.
- **Celery documentation — Task routing and best practices:** https://docs.celeryq.dev/en/stable/userguide/tasks.html — The authoritative guide for designing idempotent, retry-safe background jobs.
